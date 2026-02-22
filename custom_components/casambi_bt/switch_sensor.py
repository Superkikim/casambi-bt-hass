"""Sensor entities for displaying Casambi switch last event data."""

from __future__ import annotations

import logging
from typing import Any, Final

from CasambiBt import Unit

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Known switch model keywords to identify switch units
SWITCH_MODELS: Final[set[str]] = {
    "switch",
    "xpress",
    "button",
    "pushbutton",
    "batteryswitch",
    "wall switch",
    "remote",
}


def _is_switch_unit(unit: Unit) -> bool:
    """Check if a unit is a switch based on its mode, model or manufacturer."""
    # Mode-based detection takes priority (most reliable)
    mode = unit.unitType.mode
    if "Kinetic" in mode:
        return True  # EnOcean kinetic switch (e.g. PTM215B)
    if mode == "Sensor":
        return False  # BT repeater, not a switch

    # Check model name
    model_lower = unit.unitType.model.lower()
    if any(keyword in model_lower for keyword in SWITCH_MODELS):
        return True

    # Check manufacturer
    manufacturer_lower = unit.unitType.manufacturer.lower()
    if "switch" in manufacturer_lower:
        return True

    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    # Get all units and filter for switches
    switch_units = [unit for unit in casa_api.casa.units if _is_switch_unit(unit)]

    _LOGGER.info("Creating %d switch sensor entities", len(switch_units))

    # Create sensor entities for each switch unit
    sensor_entities = []
    for unit in switch_units:
        # Add last event sensor
        sensor_entities.append(CasambiSwitchSensor(casa_api, unit))
        # Add unit ID diagnostic sensor
        sensor_entities.append(CasambiSwitchUnitIdSensor(casa_api, unit))

    async_add_entities(sensor_entities)


class CasambiSwitchSensor(SensorEntity):
    """Sensor entity showing last event for a Casambi switch unit."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize the switch sensor entity."""
        # Store references
        self._api = api
        self._unit = unit

        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = "Last Event"
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-last-event"
        self._attr_icon = "mdi:button-pointer"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Store last event data
        self._last_event_data: dict[str, Any] = {}

        # Register for switch events
        self._api.register_switch_event_callback(self._handle_switch_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister handlers when entity is removed."""
        self._api.unregister_switch_event_callback(self._handle_switch_event)
        await super().async_will_remove_from_hass()

    def _is_kinetic_switch(self) -> bool:
        """Return True for EnOcean kinetic switches (e.g. PTM215B)."""
        return "Kinetic" in self._unit.unitType.mode

    @callback
    def _handle_switch_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming switch events."""
        # Check if this event is for our unit
        if event_data.get("unit_id") != self._unit.deviceId:
            return

        raw_index = event_data.get("button_event_index")
        if raw_index is None:
            raw_index = event_data.get("input_index")
        button_raw = (raw_index + 1) if raw_index is not None else None
        button_app = event_data.get("button")
        event_type = event_data.get("event")

        if event_type in ("button_press", "button_hold"):
            _LOGGER.debug(
                "[CASAMBI_BTN] %s | event=%-28s | button_raw=%s (index+1) | button_app=%s (lib guess) | kinetic=%s",
                self._unit.name,
                event_type,
                button_raw,
                button_app,
                self._is_kinetic_switch(),
            )

        # Store the event data
        self._last_event_data = event_data

        # Update the entity state
        self.async_write_ha_state()

    @property
    def device_info(self):
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

    @property
    def native_value(self) -> str:
        """Return the state showing last event info."""
        if not self._last_event_data:
            return "No events"

        raw_index = self._last_event_data.get("button_event_index")
        if raw_index is None:
            raw_index = self._last_event_data.get("input_index")
        button_raw = (raw_index + 1) if raw_index is not None else None
        button_app = self._last_event_data.get("button")
        # EnOcean kinetic switches (PTM215B): raw index is correct.
        # Other switches: use lib's guess (untested with other devices).
        button_display = button_raw if self._is_kinetic_switch() else (button_app or button_raw or "?")
        event_type = self._last_event_data.get("event", "unknown")

        event_map = {
            "button_press": "pressed",
            "button_hold": "held",
            "button_release": "released",
            "button_release_after_hold": "released (held)",
        }

        event_text = event_map.get(event_type, event_type)
        return f"Button {button_display} {event_text}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}

        # Add all event data if available
        if self._last_event_data:
            raw_index = self._last_event_data.get("button_event_index")
            if raw_index is None:
                raw_index = self._last_event_data.get("input_index")
            attrs.update({
                "event_type": self._last_event_data.get("event"),
                "action": self._last_event_data.get("event"),
                "button_raw": (raw_index + 1) if raw_index is not None else None,
                "button_app": self._last_event_data.get("button"),
                "unit_id": self._last_event_data.get("unit_id"),
                "message_type": self._last_event_data.get("message_type"),
                "flags": self._last_event_data.get("flags"),
            })

        # Add unit information
        attrs.update({
            "device_id": self._unit.deviceId,
            "online": self._unit.online,
        })

        return attrs


class CasambiSwitchUnitIdSensor(SensorEntity):
    """Diagnostic sensor showing the unit ID for a Casambi switch."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize the unit ID sensor."""
        # Store references
        self._api = api
        self._unit = unit

        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = "Unit ID"
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-unit-id"
        self._attr_icon = "mdi:identifier"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = str(unit.deviceId)

    @property
    def device_info(self):
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
