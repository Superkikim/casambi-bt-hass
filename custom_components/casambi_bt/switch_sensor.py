"""Sensor entities for displaying Casambi switch last event data."""

from __future__ import annotations

import logging
from typing import Any, Final

from CasambiBt import Unit

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    """Check if a unit is a switch based on its model or manufacturer."""
    # Check model name
    model_lower = unit.unitType.model.lower()
    if any(keyword in model_lower for keyword in SWITCH_MODELS):
        return True
    
    # Check manufacturer
    manufacturer_lower = unit.unitType.manufacturer.lower()
    if "switch" in manufacturer_lower:
        return True
    
    # Check if unit has no light controls (dimmer, rgb, etc)
    # but still has controls (indicating it might be a switch)
    light_controls = {
        "DIMMER", "RGB", "WHITE", "TEMPERATURE", "XY", "COLORSOURCE"
    }
    unit_controls = {c.type.name for c in unit.unitType.controls}
    
    # If it has controls but none are light controls, it might be a switch
    if unit_controls and not unit_controls.intersection(light_controls):
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
    
    _LOGGER.info(f"Creating {len(switch_units)} switch sensor entities")
    
    # Create sensor entities for each switch unit
    sensor_entities = [CasambiSwitchSensor(casa_api, unit) for unit in switch_units]
    
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
        self._attr_name = f"Last Event (Unit {unit.deviceId})"
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
    
    @callback
    def _handle_switch_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming switch events."""
        # Check if this event is for our unit
        if event_data.get("unit_id") != self._unit.deviceId:
            return
        
        _LOGGER.debug(
            f"Switch sensor event for {self.name}: button={event_data.get('button')}, "
            f"event={event_data.get('event')}"
        )
        
        # Store the event data
        self._last_event_data = event_data
        
        # Update the entity state
        self.async_write_ha_state()
    
    @property
    def device_info(self):
        """Return device info."""
        from homeassistant.helpers.device_registry import DeviceInfo
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
        
        button = self._last_event_data.get("button", "?")
        event_type = self._last_event_data.get("event", "unknown")
        
        # Create a readable state string
        event_map = {
            "button_press": "pressed",
            "button_hold": "held",
            "button_release": "released",
            "button_release_after_hold": "released (held)",
        }
        
        event_text = event_map.get(event_type, event_type)
        return f"Button {button} {event_text}"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Add all event data if available
        if self._last_event_data:
            attrs.update({
                "event_type": self._last_event_data.get("event"),
                "action": self._last_event_data.get("event"),  # Match HA event format
                "button": self._last_event_data.get("button"),
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