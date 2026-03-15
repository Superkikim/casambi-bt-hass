"""Network configuration sensor entities for Casambi."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi network sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    # Create network configuration sensor
    async_add_entities([CasambiNetworkConfigSensor(casa_api)])


class CasambiNetworkConfigSensor(SensorEntity):
    """Sensor entity showing raw network configuration."""

    def __init__(self, api: CasambiApi) -> None:
        """Initialize the network config sensor."""
        self._api = api

        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = "Network Configuration"
        self._attr_unique_id = f"{api.casa.networkId}-network-config"
        self._attr_icon = "mdi:network"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info for the network."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._api.casa.networkId)},
            name=self._api.casa.networkName,
            manufacturer="Casambi",
            model="Network",
            connections={(device_registry.CONNECTION_BLUETOOTH, self._api.address)},
        )

    @property
    def native_value(self) -> str:
        """Return the state showing network info summary."""
        raw_data = getattr(self._api.casa, "rawNetworkData", None)
        if not raw_data:
            return "No network data available"

        network = raw_data.get("network", {})
        return f"Rev {network.get('revision', 'unknown')} - {len(network.get('units', []))} units"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw network configuration as attributes."""
        raw_data = getattr(self._api.casa, "rawNetworkData", None)
        if not raw_data:
            return {"error": "No network data available"}

        # Return the complete raw network data
        # Note: Home Assistant will automatically handle JSON serialization
        return {
            "raw_network_data": raw_data,
            "network_name": self._api.casa.networkName,
            "network_id": self._api.casa.networkId,
            "revision": raw_data.get("network", {}).get("revision"),
            "protocol_version": raw_data.get("network", {}).get("protocolVersion"),
            "unit_count": len(raw_data.get("network", {}).get("units", [])),
            "scene_count": len(raw_data.get("network", {}).get("scenes", [])),
            "group_count": len(
                raw_data.get("network", {}).get("grid", {}).get("cells", [])
            ),
        }
