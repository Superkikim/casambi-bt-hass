"""Event entities for Casambi switch units.

Creates HA EventEntity instances for each switch unit, allowing button presses
to appear as device triggers in the Home Assistant automation UI.

Event types exposed: button_press, button_hold, button_release, button_release_after_hold.
"""

from __future__ import annotations

import logging
from typing import Any

from CasambiBt import Unit

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .switch_sensor import _is_switch_unit

_LOGGER = logging.getLogger(__name__)

_BUTTON_EVENT_TYPES = [
    "button_press",
    "button_hold",
    "button_release",
    "button_release_after_hold",
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch event entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    switch_units = [unit for unit in casa_api.casa.units if _is_switch_unit(unit)]

    _LOGGER.info("Creating %d switch event entities", len(switch_units))

    if switch_units:
        async_add_entities(
            CasambiSwitchEventEntity(casa_api, unit) for unit in switch_units
        )


class CasambiSwitchEventEntity(EventEntity):
    """HA EventEntity for a Casambi switch unit.

    Fires button_press / button_hold / button_release / button_release_after_hold
    events that appear as device triggers in the automation UI.
    """

    _attr_has_entity_name = True
    _attr_name = "Button"
    _attr_icon = "mdi:gesture-tap-button"
    _attr_event_types = _BUTTON_EVENT_TYPES

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize the switch event entity."""
        self._api = api
        self._unit = unit
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-event"

    async def async_added_to_hass(self) -> None:
        """Register switch event callback."""
        await super().async_added_to_hass()
        self._api.register_switch_event_callback(self._handle_switch_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister switch event callback."""
        self._api.unregister_switch_event_callback(self._handle_switch_event)
        await super().async_will_remove_from_hass()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._unit.uuid)},
            name=self._unit.name,
            manufacturer=self._unit.unitType.manufacturer,
            model=self._unit.unitType.model,
            model_id=f"Unit ID: {self._unit.deviceId}",
            sw_version=self._unit.firmwareVersion,
            via_device=(DOMAIN, self._api.casa.networkId),
        )

    @callback
    def _handle_switch_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming switch event dict from CasambiApi."""
        if event_data.get("unit_id") != self._unit.deviceId:
            return

        event_type = event_data.get("event", "unknown")
        if event_type not in _BUTTON_EVENT_TYPES:
            return

        self._trigger_event(
            event_type,
            {
                "button": event_data.get("button"),
                "unit_id": event_data.get("unit_id"),
                "flags": event_data.get("flags"),
            },
        )
        self.async_write_ha_state()
