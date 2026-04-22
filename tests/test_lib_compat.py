"""Verify that the installed lib API matches what the integration expects.

These tests must pass before any release of the integration.
They catch field name mismatches between casambi-bt-skk and this integration
before deployment to Home Assistant.
"""

import dataclasses


def test_switch_event_has_required_fields():
    """SwitchEvent must expose the fields accessed in __init__.py / switch_sensor.py / event.py."""
    from CasambiBt._casambi import SwitchEvent

    fields = {f.name for f in dataclasses.fields(SwitchEvent)}
    required = {
        "button_event_index",
        "button",
        "unit_id",
        "target_type",
        "event",
        "flags",
        "extra_data",
    }
    missing = required - fields
    assert not missing, f"SwitchEvent is missing fields used by the integration: {missing}"


def test_unit_state_has_required_properties():
    """UnitState must expose the properties accessed by entity platforms."""
    from CasambiBt._unit import UnitState

    state = UnitState()
    required = [
        "dimmer",
        "onoff",
        "slider",
        "temperature",
        "white_balance",
        "presence",
        "lux",
        "sensors",
        "unknown_controls",
        "raw_state",
    ]
    missing = [attr for attr in required if not hasattr(state, attr)]
    assert not missing, f"UnitState is missing attributes used by the integration: {missing}"


def test_unit_control_types_exist():
    """UnitControlType must include all values referenced by the integration."""
    from CasambiBt._unit import UnitControlType

    required = [
        "DIMMER",
        "ONOFF",
        "SLIDER",
        "TEMPERATURE",
        "WHITECOLORBALANCE",
        "PRESENCE",
        "LUX",
        "UNKNOWN",
        "SENSOR",
    ]
    missing = [name for name in required if not hasattr(UnitControlType, name)]
    assert not missing, f"UnitControlType is missing members used by the integration: {missing}"


def test_unit_has_required_attributes():
    """Unit must expose the attributes accessed by entity platforms."""
    from CasambiBt._unit import Unit, UnitType, UnitControl, UnitControlType

    ut = UnitType(
        id=1,
        model="test",
        manufacturer="test",
        mode="test",
        stateLength=1,
        controls=[],
    )
    unit = Unit(
        _typeId=1,
        deviceId=1,
        uuid="test",
        address="test",
        name="test",
        firmwareVersion="1.0",
        unitType=ut,
    )
    required = ["state", "is_on", "online", "deviceId", "uuid", "name",
                "unitType", "firmwareVersion"]
    missing = [attr for attr in required if not hasattr(unit, attr)]
    assert not missing, f"Unit is missing attributes used by the integration: {missing}"
