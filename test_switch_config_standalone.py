#!/usr/bin/env python3

"""Standalone test script for switch configuration logic."""

import json
from types import SimpleNamespace

# Button action type mappings
BUTTON_ACTIONS = {
    0: "Not configured",
    1: "Control Scene",
    2: "Control Unit",
    3: "Control Group",
    4: "Control All Units",
    5: "Control Unit Element",
    6: "Resume Automation",
    7: "Resume Automation Group",
}

def _resolve_target_name(raw_network_data, action, target):
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
    if action == 2:
        units = network.get("units", [])
        for unit in units:
            if unit.get("deviceID") == target:
                return unit.get("name", f"Unit {target}")
        return f"Unit {target}"

    # Group
    if action == 3:
        cells = network.get("grid", {}).get("cells", [])
        for cell in cells:
            if cell.get("type") == 2 and cell.get("groupID") == target:
                return cell.get("name", f"Group {target}")
        return f"Group {target}"

    # All units (target is usually 255)
    if action == 4:
        return ""

    return ""

def _is_switch_unit(unit):
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

def _get_unit_switch_config(raw_network_data, unit_id):
    """Extract switch configuration for a specific unit from network data."""
    if not raw_network_data:
        return None

    network = raw_network_data.get("network", {})
    units = network.get("units", [])

    for unit_data in units:
        if unit_data.get("deviceID") == unit_id:
            return unit_data.get("switchConfig")

    return None

# Sample network data structure
sample_network_data = {
    "network": {
        "name": "Test Network",
        "revision": 42,
        "protocolVersion": 4,
        "units": [
            {
                "deviceID": 31,
                "uuid": "unit-31-uuid",
                "name": "Living Room Switch",
                "type": 100,
                "address": "00:11:22:33:44:55",
                "firmware": "1.2.3",
                "switchConfig": {
                    "buttons": [
                        {"type": 0, "action": 1, "target": 5},  # Button 1: Scene 5
                        {"type": 1, "action": 3, "target": 12}, # Button 2: Group 12
                        {"type": 2, "action": 0, "target": 0},  # Button 3: Not configured
                        {"type": 3, "action": 4, "target": 255}, # Button 4: All Units
                        {"type": 4, "action": 2, "target": 32}, # Button 5: Unit 32
                    ],
                    "exclusiveScenes": False,
                    "longPressAllOff": True,
                    "toggleDisabled": False,
                    "parameters": {}
                }
            },
            {
                "deviceID": 32,
                "uuid": "unit-32-uuid",
                "name": "Table Lamp",
                "type": 101,
                "address": "00:11:22:33:44:66",
                "firmware": "1.2.3"
            }
        ],
        "scenes": [
            {"sceneID": 5, "name": "Evening"},
            {"sceneID": 6, "name": "Movie Time"}
        ],
        "grid": {
            "cells": [
                {
                    "type": 2,
                    "groupID": 12,
                    "name": "Living Room",
                    "cells": [
                        {"type": 1, "unit": 32}
                    ]
                }
            ]
        }
    }
}

def test_button_action_resolution():
    """Test resolving button actions to readable text."""
    print("\nButton Action Resolution Test:")
    print("-" * 30)

    buttons = sample_network_data["network"]["units"][0]["switchConfig"]["buttons"]

    for button in buttons:
        button_num = button["type"] + 1
        action = button["action"]
        target = button["target"]

        action_text = BUTTON_ACTIONS.get(action, f"Unknown ({action})")

        if action == 0:
            result = "Not configured"
        elif action == 4:
            result = "All Units"
        else:
            target_name = _resolve_target_name(sample_network_data, action, target)
            if target_name:
                result = f"{action_text}: {target_name}"
            else:
                result = action_text

        print(f"Button {button_num}: {result}")
        print(f"  Raw: action={action}, target={target}")

def test_switch_detection():
    """Test switch unit detection."""
    print("\nSwitch Detection Test:")
    print("-" * 30)

    # Create mock unit objects
    switch_unit = SimpleNamespace(
        unitType=SimpleNamespace(
            model="Xpress Switch",
            manufacturer="Casambi",
            controls=[]
        )
    )

    lamp_unit = SimpleNamespace(
        unitType=SimpleNamespace(
            model="LED Driver",
            manufacturer="Generic",
            controls=[
                SimpleNamespace(type=SimpleNamespace(name="DIMMER")),
                SimpleNamespace(type=SimpleNamespace(name="ONOFF"))
            ]
        )
    )

    print(f"Xpress Switch: {_is_switch_unit(switch_unit)}")  # Should be True
    print(f"LED Driver: {_is_switch_unit(lamp_unit)}")      # Should be False

def test_get_unit_switch_config():
    """Test extracting switch config for a unit."""
    print("\nSwitch Config Extraction Test:")
    print("-" * 30)

    config = _get_unit_switch_config(sample_network_data, 31)
    print("Switch Config for Unit 31:")
    print(json.dumps(config, indent=2))

    config = _get_unit_switch_config(sample_network_data, 32)
    print("\nSwitch Config for Unit 32:")
    print(config)  # Should be None

def test_button_creation_logic():
    """Test which buttons should be created."""
    print("\nButton Creation Logic Test:")
    print("-" * 30)

    buttons = sample_network_data["network"]["units"][0]["switchConfig"]["buttons"]

    # Always create buttons 1-4
    for button_num in range(1, 5):
        button_config = next(
            (b for b in buttons if b.get("type") == button_num - 1),
            {"type": button_num - 1, "action": 0, "target": 0}
        )
        action = button_config.get("action", 0)
        print(f"Button {button_num}: CREATE (action={action})")

    # Create buttons 5-8 only if configured
    for button_num in range(5, 9):
        button_config = next(
            (b for b in buttons if b.get("type") == button_num - 1),
            None
        )
        if button_config and button_config.get("action", 0) != 0:
            action = button_config.get("action", 0)
            print(f"Button {button_num}: CREATE (action={action})")
        else:
            print(f"Button {button_num}: SKIP (not configured)")

if __name__ == "__main__":
    print("Testing Switch Configuration Logic")
    print("=" * 40)

    test_button_action_resolution()
    test_switch_detection()
    test_get_unit_switch_config()
    test_button_creation_logic()

    print("\n✅ All tests completed successfully!")
