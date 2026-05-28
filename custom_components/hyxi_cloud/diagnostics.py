"""Diagnostics support for HYXI Cloud integration."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_KEY, CONF_SECRET_KEY, DOMAIN, VERSION, mask_sn

TO_REDACT = {CONF_ACCESS_KEY, CONF_SECRET_KEY}


def _redact_serial_numbers(data: dict[str, Any]) -> dict[str, Any]:
    """Replace serial numbers in coordinator data keys with masked values."""
    return {mask_sn(k): v for k, v in data.items()}


def _engine_diagnostics(engine: Any) -> dict[str, Any]:
    """Collect engine state for diagnostics."""
    now = time.monotonic()
    return {
        "sn": mask_sn(engine._sn),
        "enabled": engine._enabled,
        "current_mode": engine._current_mode,
        "last_decision": engine._last_decision,
        "last_action": engine._last_action,
        "last_sent_power": dict(engine._last_sent_power),
        "charge_entry_export_count": engine._charge_entry_export_count,
        "charge_bottomout_count": engine._charge_bottomout_count,
        "pv_curtailed": engine._pv_curtailed,
        "p1_buffer_size": len(engine._p1_buffer),
        "timers": {
            "since_last_mode_switch": (
                round(now - engine._last_mode_switch, 1)
                if engine._last_mode_switch
                else None
            ),
            "since_last_power_adjust": (
                round(now - engine._last_power_adjust, 1)
                if engine._last_power_adjust
                else None
            ),
            "since_last_charge_exit": (
                round(now - engine._last_charge_exit, 1)
                if engine._last_charge_exit
                else None
            ),
            "since_last_bottomout_exit": (
                round(now - engine._last_bottomout_exit, 1)
                if engine._last_bottomout_exit
                else None
            ),
        },
        "config": {
            "p1_entity": engine._p1_entity,
            "forecast_entity": engine._forecast_entity,
            "forecast_power_entity": engine._forecast_power_entity,
        },
    }


def _coordinator_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Collect coordinator state for diagnostics."""
    diag: dict[str, Any] = {
        "update_interval_s": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        "device_count": len(coordinator.data) if coordinator.data else 0,
        "last_update_success": coordinator.last_update_success,
    }

    # Protection controllers
    if hasattr(coordinator, "protection_controllers"):
        controllers = {}
        for sn, ctrl in coordinator.protection_controllers.items():
            controllers[mask_sn(sn)] = {
                "monitoring": ctrl._monitoring,
                "tripped": getattr(ctrl, "_tripped", False),
            }
        diag["protection_controllers"] = controllers

    return diag


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diag: dict[str, Any] = {
        "integration_version": VERSION,
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
    }

    if coordinator is None:
        diag["error"] = "coordinator_not_found"
        return diag

    diag["coordinator"] = _coordinator_diagnostics(coordinator)

    # Device summary (redact serial numbers)
    if coordinator.data:
        devices: dict[str, Any] = {}
        for sn, dev_data in coordinator.data.items():
            devices[mask_sn(sn)] = {
                "model": dev_data.get("model"),
                "device_type": dev_data.get("deviceType"),
                "online": dev_data.get("online"),
                "phase_type": dev_data.get("phase_type"),
            }
        diag["devices"] = devices

    # Engine diagnostics
    engine = getattr(coordinator, "engine", None)
    if engine is not None:
        diag["energy_manager"] = _engine_diagnostics(engine)
    else:
        diag["energy_manager"] = None

    return diag
