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

        self._hold_seen: set[int] = set()
        self._last_button: int | None = None
        self._last_command: str | None = None

    async def async_added_to_hass(self) -> None:
        """Register handlers once hass is available."""
        await super().async_added_to_hass()
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

        # Determine button number to use
        button = button_raw if self._is_kinetic_switch() else (button_app or button_raw)

        # Determine command from event type
        command: str | None = None
        if event_type == "button_press" and button is not None:
            self._hold_seen.discard(button)
            command = "pressed"
        elif event_type == "button_hold" and button is not None:
            self._hold_seen.add(button)
            command = "held"
        elif event_type == "button_release" and button is not None:
            if button not in self._hold_seen:
                command = "released"
            # else: suppress — intermediate release during hold, not meaningful
        elif event_type == "button_release_after_hold" and button is not None:
            self._hold_seen.discard(button)
            command = "released_after_hold"

        if command is None:
            return

        _LOGGER.debug(
            "[CASAMBI_BTN] %s | button=%s | command=%s",
            self._unit.name,
            button,
            command,
        )

        self._last_button = button
        self._last_command = command

        # Fire HA event — always delivered, no state deduplication
        self.hass.bus.async_fire(
            "casambi_bt_button_event",
            {
                "unit_id": self._unit.deviceId,
                "unit_name": self._unit.name,
                "button": button,
                "command": command,
                "button_raw": button_raw,
                "button_app": button_app,
            },
        )

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
        """Return the state as '{button} {command}'."""
        if self._last_button is None or self._last_command is None:
            return "no_event"
        return f"{self._last_button} {self._last_command}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "button": self._last_button,
            "command": self._last_command,
            "device_id": self._unit.deviceId,
            "online": self._unit.online,
        }


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
