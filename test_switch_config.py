#!/usr/bin/env python3

"""Test script for switch configuration sensors."""

import json

# Sample network data structure based on Android app analysis
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
                        {"type": 1, "action": 3, "target": 12},  # Button 2: Group 12
                        {
                            "type": 2,
                            "action": 0,
                            "target": 0,
                        },  # Button 3: Not configured
                        {"type": 3, "action": 4, "target": 255},  # Button 4: All Units
                        {"type": 4, "action": 2, "target": 32},  # Button 5: Unit 32
                    ],
                    "exclusiveScenes": False,
                    "longPressAllOff": True,
                    "toggleDisabled": False,
                    "parameters": {},
                },
            },
            {
                "deviceID": 32,
                "uuid": "unit-32-uuid",
                "name": "Table Lamp",
                "type": 101,
                "address": "00:11:22:33:44:66",
                "firmware": "1.2.3",
            },
        ],
        "scenes": [
            {"sceneID": 5, "name": "Evening"},
            {"sceneID": 6, "name": "Movie Time"},
        ],
        "grid": {
            "cells": [
                {
                    "type": 2,
                    "groupID": 12,
                    "name": "Living Room",
                    "cells": [{"type": 1, "unit": 32}],
                }
            ]
        },
    }
}


def test_button_action_resolution():
    """Test resolving button actions to readable text."""
    from custom_components.casambi_bt.switch_config_sensor import (
        BUTTON_ACTIONS,
        _resolve_target_name,
    )

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
    from types import SimpleNamespace

    from custom_components.casambi_bt.switch_config_sensor import _is_switch_unit

    # Create mock unit objects
    switch_unit = SimpleNamespace(
        unitType=SimpleNamespace(
            model="Xpress Switch", manufacturer="Casambi", controls=[]
        )
    )

    lamp_unit = SimpleNamespace(
        unitType=SimpleNamespace(
            model="LED Driver",
            manufacturer="Generic",
            controls=[
                SimpleNamespace(type=SimpleNamespace(name="DIMMER")),
                SimpleNamespace(type=SimpleNamespace(name="ONOFF")),
            ],
        )
    )

    print("\nSwitch Detection Test:")
    print(f"Xpress Switch: {_is_switch_unit(switch_unit)}")  # Should be True
    print(f"LED Driver: {_is_switch_unit(lamp_unit)}")  # Should be False


def test_get_unit_switch_config():
    """Test extracting switch config for a unit."""
    from custom_components.casambi_bt.switch_config_sensor import (
        _get_unit_switch_config,
    )

    config = _get_unit_switch_config(sample_network_data, 31)
    print("\nSwitch Config for Unit 31:")
    print(json.dumps(config, indent=2))

    config = _get_unit_switch_config(sample_network_data, 32)
    print("\nSwitch Config for Unit 32:")
    print(config)  # Should be None


if __name__ == "__main__":
    print("Testing Switch Configuration Sensors")
    print("=" * 40)

    test_button_action_resolution()
    test_switch_detection()
    test_get_unit_switch_config()

    print("\n✅ Tests completed!")
