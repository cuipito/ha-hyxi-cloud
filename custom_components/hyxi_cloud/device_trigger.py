"""Device triggers for HYXI Cloud integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

TRIGGER_TYPES = {
    "em_charge_started",
    "em_charge_stopped",
    "em_discharge_started",
    "em_discharge_stopped",
    "em_night_mode_on",
    "em_night_mode_off",
    "em_high_load_on",
    "em_high_load_off",
}

TRIGGER_SCHEMA = {
    CONF_PLATFORM: "device",
    CONF_DOMAIN: DOMAIN,
    CONF_DEVICE_ID: str,
    CONF_TYPE: str,
}

# Map trigger types to event data patterns
_EVENT_TRIGGERS = {
    "em_charge_started": {"mode": "charge"},
    "em_charge_stopped": {"previous_mode": "charge"},
    "em_discharge_started": {"mode": "discharge"},
    "em_discharge_stopped": {"previous_mode": "discharge"},
}

# Map trigger types to binary_sensor translation_key + target state
_STATE_TRIGGERS = {
    "em_night_mode_on": {"tkey": "em_night_mode_active", "to": "on"},
    "em_night_mode_off": {"tkey": "em_night_mode_active", "to": "off"},
    "em_high_load_on": {"tkey": "em_high_load_detected", "to": "on"},
    "em_high_load_off": {"tkey": "em_high_load_detected", "to": "off"},
}


def _device_is_em(hass: HomeAssistant, device_id: str) -> bool:
    """Check if device is the Energy Manager device."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if not device:
        return False
    for domain, ident in device.identifiers:
        if domain == DOMAIN and str(ident).endswith("_energy_manager"):
            return True
    return False


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return triggers for the Energy Manager device."""
    if not _device_is_em(hass, device_id):
        return []

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    trigger_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]

    # Event-based triggers (charge/discharge started/stopped)
    if trigger_type in _EVENT_TRIGGERS:
        match_data = _EVENT_TRIGGERS[trigger_type]

        @callback
        def _event_listener(event: Event) -> None:
            data = event.data
            for key, value in match_data.items():
                if data.get(key) != value:
                    return
            hass.async_run_hass_job(
                action,
                {"trigger": {**config, "event": event}},
            )

        unsub = hass.bus.async_listen("hyxi_em_mode_changed", _event_listener)
        return unsub

    # State-based triggers (night mode, high load)
    if trigger_type in _STATE_TRIGGERS:
        meta = _STATE_TRIGGERS[trigger_type]
        ent_reg = er.async_get(hass)

        # Find the matching binary_sensor entity
        entity_id = None
        for ent in er.async_entries_for_device(ent_reg, device_id):
            if ent.domain == "binary_sensor" and ent.translation_key == meta["tkey"]:
                entity_id = ent.entity_id
                break

        if not entity_id:
            return lambda: None

        try:
            from homeassistant.components.homeassistant.triggers import (
                state as state_trigger,
            )
        except ImportError:
            from homeassistant.components.automation.triggers import (
                state as state_trigger,
            )

        state_cfg = {
            "platform": "state",
            "entity_id": entity_id,
            "to": meta["to"],
        }
        return await state_trigger.async_attach_trigger(
            hass, state_cfg, action, trigger_info, platform_type="device"
        )

    return lambda: None
