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

# Button action type mappings (based on real network data)
BUTTON_ACTIONS: Final[dict[int, str]] = {
    0: "Control Unit",
    1: "Control Group", 
    2: "Control Scene",
    3: "All Units Off",
    4: "All Units Dim",
    5: "Not Configured",
    6: "Block",
    7: "Group",
    8: "Scene List",
    9: "All Units",
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


def _get_unit_data(raw_network_data: dict | None, unit_id: int) -> dict | None:
    """Get the complete unit data from network data."""
    if not raw_network_data:
        return None
    
    network = raw_network_data.get("network", {})
    units = network.get("units", [])
    
    for unit_data in units:
        if unit_data.get("deviceID") == unit_id:
            return unit_data
    
    return None


def _get_button_configs(unit_data: dict | None) -> list[dict[str, Any]]:
    """Extract button configurations from unit data.
    
    Returns a list of button configs with index, type, and target.
    """
    if not unit_data:
        return []
    
    buttons = []
    
    # Check for pushButton fields (standard switch format)
    button_fields = [
        ("pushButton", 1),
        ("pushButton2", 2),
        ("pushButton3", 3),
        ("pushButton4", 4)
    ]
    for field_name, button_index in button_fields:
        if field_name in unit_data:
            button_config = unit_data[field_name]
            # Button config can be a dict or might be simplified
            if isinstance(button_config, dict):
                # Ensure index is set based on field name
                button_config = button_config.copy()
                button_config["index"] = button_index
                buttons.append(button_config)
    
    # Check for switchConfig.switches (Xpress switch format)
    switch_config = unit_data.get("switchConfig", {})
    if "switches" in switch_config:
        for switch in switch_config["switches"]:
            if isinstance(switch, dict):
                # Convert 0-based index to 1-based button number
                switch_copy = switch.copy()
                if "index" in switch_copy:
                    switch_copy["index"] = switch_copy["index"] + 1
                buttons.append(switch_copy)
    
    return buttons


def _resolve_target_name(
    raw_network_data: dict | None, 
    action: int, 
    target: int
) -> str:
    """Resolve target ID to a name based on action type."""
    if not raw_network_data:
        return ""
    
    network = raw_network_data.get("network", {})
    
    # Unit (type 0)
    if action == 0:
        units = network.get("units", [])
        for unit in units:
            if unit.get("deviceID") == target:
                return unit.get("name", f"Unit {target}")
        return f"Unit {target}"
    
    # Group (type 1 or 7)
    elif action in [1, 7]:
        cells = network.get("grid", {}).get("cells", [])
        for cell in cells:
            if cell.get("type") == 2 and cell.get("groupID") == target:
                return cell.get("name", f"Group {target}")
        return f"Group {target}"
    
    # Scene (type 2)
    elif action == 2:
        scenes = network.get("scenes", [])
        for scene in scenes:
            if scene.get("sceneID") == target:
                return scene.get("name", f"Scene {target}")
        return f"Scene {target}"
    
    # All units off/dim (type 3, 4, 9)
    elif action in [3, 4, 9]:
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
        # Get complete unit data
        unit_data = _get_unit_data(
            casa_api.casa.rawNetworkData, 
            unit.deviceId
        )
        
        if unit_data:
            # Get button configurations
            button_configs = _get_button_configs(unit_data)
            
            # Create button action sensors for buttons 1-4 (always)
            for button_num in range(1, 5):
                # Find config for this button index
                button_config = next(
                    (b for b in button_configs if b.get("index") == button_num), 
                    {"index": button_num, "type": 5, "unitID": 0}  # Default: Not configured
                )
                sensor_entities.append(
                    CasambiButtonActionSensor(
                        casa_api, unit, button_num, button_config
                    )
                )
            
            # Check if there are buttons 5-8 configured
            for button_num in range(5, 9):
                button_config = next(
                    (b for b in button_configs if b.get("index") == button_num), 
                    None
                )
                if button_config and button_config.get("type", 5) != 5:  # 5 = Not configured
                    sensor_entities.append(
                        CasambiButtonActionSensor(
                            casa_api, unit, button_num, button_config
                        )
                    )
            
            # Get switchConfig for settings
            switch_config = unit_data.get("switchConfig", {})
            
            # Create raw config sensor
            sensor_entities.append(
                CasambiSwitchRawConfigSensor(casa_api, unit, unit_data)
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
        action_type = self._button_config.get("type", 5)
        # Use unit for unit actions, group for group actions
        target = self._button_config.get("unit") or self._button_config.get("group", 0)
        
        action_text = BUTTON_ACTIONS.get(action_type, f"Unknown ({action_type})")
        
        if action_type == 5:  # Not configured
            return "Not configured"
        elif action_type in [3, 4, 9]:  # All units actions
            return action_text
        else:
            target_name = _resolve_target_name(
                self._api.casa.rawNetworkData, 
                action_type, 
                target
            )
            if target_name:
                return f"{action_text}: {target_name}"
            else:
                return action_text
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        action_type = self._button_config.get("type", 5)
        target = self._button_config.get("unit") or self._button_config.get("group", 0)
        
        return {
            "button_number": self._button_number,
            "button_index": self._button_config.get("index", self._button_number),
            "action_type": action_type,
            "action_name": BUTTON_ACTIONS.get(action_type),
            "target_id": target,
            "raw_config": self._button_config
        }


class CasambiSwitchRawConfigSensor(SensorEntity):
    """Sensor showing raw switch configuration for a unit."""
    
    def __init__(
        self, 
        api: CasambiApi, 
        unit: Unit,
        unit_data: dict[str, Any]
    ) -> None:
        """Initialize the raw config sensor."""
        self._api = api
        self._unit = unit
        self._unit_data = unit_data
        self._button_configs = _get_button_configs(unit_data)
        
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
        configured_count = sum(1 for b in self._button_configs if b.get("type", 5) != 5)
        return f"{configured_count} buttons configured"
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the raw switch configuration."""
        # Extract relevant switch-related fields
        switch_fields = {}
        
        # Include pushButton fields
        for field in ["pushButton", "pushButton2", "pushButton3", "pushButton4"]:
            if field in self._unit_data:
                switch_fields[field] = self._unit_data[field]
        
        # Include switchConfig if present
        if "switchConfig" in self._unit_data:
            switch_fields["switchConfig"] = self._unit_data["switchConfig"]
        
        return {
            "raw_switch_config": switch_fields,
            "button_configs": self._button_configs,
            "configured_buttons": sum(
                1 for b in self._button_configs
                if b.get("type", 5) != 5
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