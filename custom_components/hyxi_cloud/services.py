"""Service handlers for HYXI Cloud integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_FORCE_REFRESH = "force_refresh"
SERVICE_SET_EM_MODE = "set_em_mode"
SERVICE_EM_PAUSE = "em_pause"
SERVICE_EM_RESUME = "em_resume"

SET_EM_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("mode"): vol.In(["charge", "discharge", "self_consume"]),
        vol.Optional("power"): vol.All(
            vol.Coerce(int), vol.Range(min=100, max=9000)
        ),
    }
)


def _get_coordinators(hass: HomeAssistant) -> list:
    """Return all active coordinators."""
    return list((hass.data.get(DOMAIN) or {}).values())


def _get_engine(hass: HomeAssistant):
    """Return the first active EM engine, or raise."""
    for coordinator in _get_coordinators(hass):
        engine = getattr(coordinator, "engine", None)
        if engine is not None:
            return engine
    raise ServiceValidationError(
        "Energy Manager not configured or not running",
        translation_domain=DOMAIN,
        translation_key="em_not_running",
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register HYXI Cloud services."""

    async def handle_force_refresh(call: ServiceCall) -> None:
        """Force an immediate coordinator refresh."""
        for coordinator in _get_coordinators(hass):
            await coordinator.async_request_refresh()
        _LOGGER.info("HYXI: Force refresh triggered via service")

    async def handle_set_em_mode(call: ServiceCall) -> None:
        """Set the EM engine to a specific mode."""
        engine = _get_engine(hass)
        mode = call.data["mode"]
        power = call.data.get("power")

        if mode in ("charge", "discharge") and not power:
            raise ServiceValidationError(
                f"Power is required for {mode} mode",
                translation_domain=DOMAIN,
                translation_key="power_required",
            )

        success = await engine._set_mode(mode, power)
        if success:
            _LOGGER.info("HYXI: EM mode set to %s @ %sW via service", mode, power)
        else:
            raise ServiceValidationError(
                f"Failed to set mode {mode}",
                translation_domain=DOMAIN,
                translation_key="mode_set_failed",
            )

    async def handle_em_pause(call: ServiceCall) -> None:
        """Pause the EM engine."""
        engine = _get_engine(hass)
        engine._enabled = False
        await engine._set_mode("self_consume")
        engine._set_decision("paused")
        engine._notify_sensors()
        _LOGGER.info("HYXI: Energy Manager paused via service")

    async def handle_em_resume(call: ServiceCall) -> None:
        """Resume the EM engine."""
        engine = _get_engine(hass)
        engine._enabled = True
        engine._set_decision("")
        engine._notify_sensors()
        _LOGGER.info("HYXI: Energy Manager resumed via service")

    hass.services.async_register(DOMAIN, SERVICE_FORCE_REFRESH, handle_force_refresh)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_EM_MODE, handle_set_em_mode, schema=SET_EM_MODE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_EM_PAUSE, handle_em_pause)
    hass.services.async_register(DOMAIN, SERVICE_EM_RESUME, handle_em_resume)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload HYXI Cloud services."""
    # Only unload if no more entries remain
    if hass.data.get(DOMAIN):
        return
    for service in (
        SERVICE_FORCE_REFRESH,
        SERVICE_SET_EM_MODE,
        SERVICE_EM_PAUSE,
        SERVICE_EM_RESUME,
    ):
        hass.services.async_remove(DOMAIN, service)
