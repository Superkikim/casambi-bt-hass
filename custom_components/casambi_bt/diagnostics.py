"""Diagnostics support for Casambi BT."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import CasambiApi
from .const import DOMAIN

_REDACT_KEYS = {"password", "token", "api_key", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Casambi BT config entry."""
    api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    units_info = [
        {
            "name": unit.name,
            "device_id": unit.deviceId,
            "uuid": unit.uuid,
            "online": unit.online,
            "mode": unit.unitType.mode,
            "model": unit.unitType.model,
            "manufacturer": unit.unitType.manufacturer,
            "firmware": unit.firmwareVersion,
        }
        for unit in api.casa.units
    ]

    return {
        "config_entry": async_redact_data(config_entry.as_dict(), _REDACT_KEYS),
        "network_id": api.casa.networkId,
        "units_count": len(units_info),
        "units": units_info,
    }
