"""Sensor implementation for Casambi Switch Units."""

from datetime import datetime
import logging
from typing import Any, cast

from CasambiBt import Unit as CasambiUnit
from CasambiBt import UnitControlType

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, CasambiApi
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)

# Define switch unit control types
CASA_SWITCH_CTRL_TYPES = [
    UnitControlType.SWITCH,
    UnitControlType.PUSH_BUTTON,
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch unit sensors."""
    _LOGGER.debug("Setting up sensor entities for switch units")
    api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    
    # Find all switch units
    switch_units = []
    for unit in api.casa.units:
        # Check if this is a switch unit
        if unit.unitType and unit.unitType.controls:
            control_types = [uc.type for uc in unit.unitType.controls]
            if any(ct in CASA_SWITCH_CTRL_TYPES for ct in control_types):
                switch_units.append(unit)
                _LOGGER.info(
                    "Found switch unit: %s (ID: %s, UUID: %s)",
                    unit.name,
                    unit.deviceId,
                    unit.uuid
                )
    
    # Create sensor entities for switch units
    sensors = []
    
    # Create last event sensor for each switch unit
    for unit in switch_units:
        sensors.append(CasambiSwitchEventSensor(api, unit))
        # Add diagnostic sensors
        sensors.append(CasambiSwitchUnitIdSensor(api, unit))
        if unit.firmware:
            sensors.append(CasambiSwitchFirmwareSensor(api, unit))
    
    if sensors:
        async_add_entities(sensors)
        _LOGGER.info("Created %d sensor entities for %d switch units", 
                     len(sensors), len(switch_units))
    else:
        _LOGGER.debug("No switch units found in the network")


class CasambiSwitchEventSensor(CasambiUnitEntity, SensorEntity):
    """Sensor for tracking last switch event."""
    
    def __init__(self, api: CasambiApi, unit: CasambiUnit) -> None:
        """Initialize the switch event sensor."""
        description = TypedEntityDescription(
            key="last_event",
            name="Last Event",
            entity_type="last_event",
            icon="mdi:button-pointer",
        )
        super().__init__(api, description, unit)
        
        # Store last event data
        self._last_event_data: dict[str, Any] = {}
        self._attr_native_value = "No event"
        
        # Register for switch events
        if hasattr(api, 'register_switch_event_callback'):
            api.register_switch_event_callback(self._handle_switch_event)
            _LOGGER.debug("Registered switch event callback for unit %s", unit.deviceId)
    
    @callback
    def _handle_switch_event(self, event_data: dict) -> None:
        """Handle switch events from the Casambi network."""
        unit = cast(CasambiUnit, self._obj)
        
        # Check if this event is for our unit
        if event_data.get("unit_id") != unit.deviceId:
            return
        
        # Update the sensor with new event data
        button = event_data.get("button", 0)
        action = event_data.get("event", "unknown")
        timestamp = datetime.now().isoformat()
        
        # Create state value that includes timestamp to ensure it always changes
        self._attr_native_value = f"button_{button}_{action}_{timestamp}"
        
        # Store full event data as attributes
        self._last_event_data = {
            "button": button,
            "action": action,
            "timestamp": timestamp,
            "unit_id": event_data.get("unit_id"),
            "message_type": f"0x{event_data.get('message_type', 0):02x}",
            "flags": f"0x{event_data.get('flags', 0):02x}",
            "packet_sequence": event_data.get("packet_sequence"),
            "raw_packet": event_data.get("raw_packet"),
        }
        
        _LOGGER.debug(
            "Switch event for unit %s: button=%s, action=%s",
            unit.deviceId,
            button,
            action
        )
        
        # Trigger state update
        self.schedule_update_ha_state()
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return self._last_event_data
    
    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        unit = cast(CasambiUnit, self._obj)
        _LOGGER.debug("Switch event sensor added for unit %s", unit.name)
    
    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        # Unregister callback if needed
        if hasattr(self._api, 'unregister_switch_event_callback'):
            self._api.unregister_switch_event_callback(self._handle_switch_event)


class CasambiSwitchUnitIdSensor(CasambiUnitEntity, SensorEntity):
    """Diagnostic sensor showing unit ID."""
    
    def __init__(self, api: CasambiApi, unit: CasambiUnit) -> None:
        """Initialize the unit ID sensor."""
        description = TypedEntityDescription(
            key="unit_id",
            name="Unit ID",
            entity_type="unit_id",
            icon="mdi:identifier",
        )
        super().__init__(api, description, unit)
        
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = str(unit.deviceId)


class CasambiSwitchFirmwareSensor(CasambiUnitEntity, SensorEntity):
    """Diagnostic sensor showing firmware version."""
    
    def __init__(self, api: CasambiApi, unit: CasambiUnit) -> None:
        """Initialize the firmware sensor."""
        description = TypedEntityDescription(
            key="firmware",
            name="Firmware",
            entity_type="firmware",
            icon="mdi:chip",
        )
        super().__init__(api, description, unit)
        
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = unit.firmware or "Unknown"