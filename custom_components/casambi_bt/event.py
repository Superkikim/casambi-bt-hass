"""Event entities for Casambi switches.

This module creates event entities for Casambi switch units, allowing them to be
used in Home Assistant automations. This works alongside the existing 
casambi_bt_switch_event Home Assistant events for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Final

from CasambiBt import Unit

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

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
    """Set up Casambi switch event entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get all units and filter for switches
    switch_units = [unit for unit in casa_api.casa.units if _is_switch_unit(unit)]
    
    _LOGGER.info(f"Found {len(switch_units)} switch units to create event entities for")
    
    # Create event entities for each switch unit
    event_entities = [CasambiSwitchEvent(casa_api, unit) for unit in switch_units]
    
    async_add_entities(event_entities)


class CasambiSwitchEvent(CasambiUnitEntity, EventEntity):
    """Event entity for a Casambi switch unit."""
    
    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize the switch event entity."""
        # Create entity description
        entity_key = f"switch_{unit.deviceId}"
        
        # Add " Switch" to name if not already present
        unit_name = unit.name
        if "switch" not in unit_name.lower():
            unit_name = f"{unit_name} Switch"
        
        description = TypedEntityDescription(
            key=unit.uuid,  # Use uuid as key for uniqueness
            name=unit_name,
            entity_type="event",
        )
        
        super().__init__(api, description, unit)
        
        # Set icon
        self._attr_icon = "mdi:gesture-tap-button"
        
        # Event entity specific attributes
        self._attr_event_types = [
            "button_press",
            "button_hold", 
            "button_release",
            "button_release_after_hold",
        ]
        
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
            f"Switch event for {self.name}: button={event_data.get('button')}, "
            f"event={event_data.get('event')}"
        )
        
        # Store the event data
        self._last_event_data = event_data
        
        # Trigger the event with the event type
        event_type = event_data.get("event", "unknown")
        self._trigger_event(event_type, event_data)
        
        # Update the entity state
        self.async_write_ha_state()
    
    @property
    def state(self) -> str | None:
        """Return the state (timestamp of last event)."""
        if self._last_event_data:
            # Return ISO format timestamp
            return dt_util.now().isoformat()
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes or {}
        
        # Add switch-specific attributes from last event
        if self._last_event_data:
            attrs.update({
                "event_type": self._last_event_data.get("event"),
                "button": self._last_event_data.get("button"),
                "unit_id": self._last_event_data.get("unit_id"),
                "message_type": self._last_event_data.get("message_type"),
                "flags": self._last_event_data.get("flags"),
            })
        
        # Add unit information
        attrs.update({
            "device_id": self._unit.deviceId,
            "address": self._unit.address,
            "firmware_version": self._unit.firmwareVersion,
            "model": self._unit.unitType.model,
            "manufacturer": self._unit.unitType.manufacturer,
            "online": self._unit.online,
        })
        
        return attrs