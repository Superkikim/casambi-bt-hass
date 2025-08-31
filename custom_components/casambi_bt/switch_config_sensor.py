"""Switch configuration sensor entities for Casambi switches."""

from __future__ import annotations

import json
import logging
from typing import Any, Final

from CasambiBt import Unit

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Button action type mappings
BUTTON_ACTIONS: Final[dict[int, str]] = {
    0: "Not configured",
    1: "Control Scene",
    2: "Control Unit", 
    3: "Control Group",
    4: "Control All Units",
    5: "Control Unit Element",
    6: "Resume Automation",
    7: "Resume Automation Group",
}


def _is_switch_unit(unit: Unit) -> bool:
    """Check if a unit is a switch based on its model or manufacturer."""
    # Check model name
    model_lower = unit.unitType.model.lower()
    switch_keywords = {
        "switch", "xpress", "button", "pushbutton", 
        "batteryswitch", "wall switch", "remote"
    }
    if any(keyword in model_lower for keyword in switch_keywords):
        return True
    
    # Check manufacturer
    manufacturer_lower = unit.unitType.manufacturer.lower()
    if "switch" in manufacturer_lower:
        return True
    
    # Check if unit has no light controls but still has controls
    light_controls = {
        "DIMMER", "RGB", "WHITE", "TEMPERATURE", "XY", "COLORSOURCE", "ONOFF"
    }
    unit_controls = {c.type.name for c in unit.unitType.controls}
    
    # If it has controls but none are light controls, it might be a switch
    if unit_controls and not unit_controls.intersection(light_controls):
        return True
    
    return False


def _get_unit_switch_config(raw_network_data: dict | None, unit_id: int) -> dict | None:
    """Extract switch configuration for a specific unit from network data."""
    if not raw_network_data:
        return None
    
    network = raw_network_data.get("network", {})
    units = network.get("units", [])
    
    for unit_data in units:
        if unit_data.get("deviceID") == unit_id:
            return unit_data.get("switchConfig")
    
    return None


def _resolve_target_name(
    raw_network_data: dict | None, 
    action: int, 
    target: int
) -> str:
    """Resolve target ID to a name based on action type."""
    if not raw_network_data or target == 0:
        return ""
    
    network = raw_network_data.get("network", {})
    
    # Scene
    if action == 1:
        scenes = network.get("scenes", [])
        for scene in scenes:
            if scene.get("sceneID") == target:
                return scene.get("name", f"Scene {target}")
        return f"Scene {target}"
    
    # Unit
    elif action == 2:
        units = network.get("units", [])
        for unit in units:
            if unit.get("deviceID") == target:
                return unit.get("name", f"Unit {target}")
        return f"Unit {target}"
    
    # Group
    elif action == 3:
        cells = network.get("grid", {}).get("cells", [])
        for cell in cells:
            if cell.get("type") == 2 and cell.get("groupID") == target:
                return cell.get("name", f"Group {target}")
        return f"Group {target}"
    
    # All units (target is usually 255)
    elif action == 4:
        return ""
    
    return ""


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch configuration sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get all switch units
    switch_units = [unit for unit in casa_api.casa.units if _is_switch_unit(unit)]
    
    _LOGGER.info(f"Creating switch configuration sensors for {len(switch_units)} switch units")
    
    sensor_entities = []
    for unit in switch_units:
        # Get switch config for this unit
        switch_config = _get_unit_switch_config(
            casa_api.casa.rawNetworkData, 
            unit.deviceId
        )
        
        if switch_config:
            # Create button action sensors (always 1-4, 5-8 if configured)
            buttons = switch_config.get("buttons", [])
            
            # Always create sensors for buttons 1-4
            for button_num in range(1, 5):
                button_config = next(
                    (b for b in buttons if b.get("type") == button_num - 1), 
                    {"type": button_num - 1, "action": 0, "target": 0}
                )
                sensor_entities.append(
                    CasambiButtonActionSensor(
                        casa_api, unit, button_num, button_config
                    )
                )
            
            # Create sensors for buttons 5-8 only if configured
            for button_num in range(5, 9):
                button_config = next(
                    (b for b in buttons if b.get("type") == button_num - 1), 
                    None
                )
                if button_config and button_config.get("action", 0) != 0:
                    sensor_entities.append(
                        CasambiButtonActionSensor(
                            casa_api, unit, button_num, button_config
                        )
                    )
            
            # Create raw config sensor for the switch
            sensor_entities.append(
                CasambiSwitchRawConfigSensor(casa_api, unit, switch_config)
            )
            
            # Create settings sensor
            sensor_entities.append(
                CasambiSwitchSettingsSensor(casa_api, unit, switch_config)
            )
    
    async_add_entities(sensor_entities)


class CasambiButtonActionSensor(SensorEntity):
    """Sensor showing the action configured for a specific button."""
    
    def __init__(
        self, 
        api: CasambiApi, 
        unit: Unit, 
        button_number: int,
        button_config: dict[str, Any]
    ) -> None:
        """Initialize the button action sensor."""
        self._api = api
        self._unit = unit
        self._button_number = button_number
        self._button_config = button_config
        
        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = f"Button {button_number} Action"
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-button-{button_number}"
        self._attr_icon = "mdi:button-cursor"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
    
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
        """Return the button action as readable text."""
        action = self._button_config.get("action", 0)
        target = self._button_config.get("target", 0)
        
        action_text = BUTTON_ACTIONS.get(action, f"Unknown ({action})")
        
        if action == 0:
            return "Not configured"
        elif action == 4:
            return "All Units"
        else:
            target_name = _resolve_target_name(
                self._api.casa.rawNetworkData, 
                action, 
                target
            )
            if target_name:
                return f"{action_text}: {target_name}"
            else:
                return action_text
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "button_number": self._button_number,
            "action_type": self._button_config.get("action", 0),
            "action_name": BUTTON_ACTIONS.get(self._button_config.get("action", 0)),
            "target_id": self._button_config.get("target", 0),
            "raw_config": self._button_config
        }


class CasambiSwitchRawConfigSensor(SensorEntity):
    """Sensor showing raw switch configuration for a unit."""
    
    def __init__(
        self, 
        api: CasambiApi, 
        unit: Unit,
        switch_config: dict[str, Any]
    ) -> None:
        """Initialize the raw config sensor."""
        self._api = api
        self._unit = unit
        self._switch_config = switch_config
        
        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = "Switch Configuration"
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-switch-config"
        self._attr_icon = "mdi:cog"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
    
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
        """Return summary of switch configuration."""
        buttons = self._switch_config.get("buttons", [])
        configured_count = sum(1 for b in buttons if b.get("action", 0) != 0)
        return f"{configured_count} buttons configured"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw switch configuration."""
        return {
            "raw_switch_config": self._switch_config,
            "button_count": len(self._switch_config.get("buttons", [])),
            "configured_buttons": sum(
                1 for b in self._switch_config.get("buttons", []) 
                if b.get("action", 0) != 0
            )
        }


class CasambiSwitchSettingsSensor(SensorEntity):
    """Sensor showing switch settings in readable format."""
    
    def __init__(
        self, 
        api: CasambiApi, 
        unit: Unit,
        switch_config: dict[str, Any]
    ) -> None:
        """Initialize the settings sensor."""
        self._api = api
        self._unit = unit
        self._switch_config = switch_config
        
        # Set entity attributes
        self._attr_has_entity_name = True
        self._attr_name = "Switch Settings"
        self._attr_unique_id = f"{api.casa.networkId}-unit-{unit.uuid}-switch-settings"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
    
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
        """Return summary of settings."""
        settings = []
        if self._switch_config.get("longPressAllOff"):
            settings.append("Long Press All Off")
        if self._switch_config.get("toggleDisabled"):
            settings.append("Toggle Disabled")
        if self._switch_config.get("exclusiveScenes"):
            settings.append("Exclusive Scenes")
        
        return ", ".join(settings) if settings else "Default settings"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed switch settings."""
        return {
            "long_press_all_off": self._switch_config.get("longPressAllOff", False),
            "toggle_disabled": self._switch_config.get("toggleDisabled", False),
            "exclusive_scenes": self._switch_config.get("exclusiveScenes", False),
            "parameters": self._switch_config.get("parameters", {})
        }