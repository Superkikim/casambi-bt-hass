"""Event entities for Casambi switch units.

Creates one HA EventEntity per physical button per switch unit.
In the automation UI this appears as: "<Device> Button N: detected <action>"

Action types: press, hold, release, release_after_hold.
"""

from __future__ import annotations

import logging
from typing import Any

from CasambiBt import Unit

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .switch_sensor import _is_switch_unit

_LOGGER = logging.getLogger(__name__)

_BUTTON_ACTIONS = ["press", "hold", "release", "release_after_hold"]

# Map from the event dict strings (from __init__.py) to short action names
_EVENT_TO_ACTION: dict[str, str] = {
    "button_press": "press",
    "button_hold": "hold",
    "button_release": "release",
    "button_release_after_hold": "release_after_hold",
}

# Number of physical buttons to expose per switch unit.
# PTM215B has 4; unknown switch types default to 4 (unused buttons stay silent).
_BUTTONS_PER_SWITCH = 4


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch event entities (one per button per switch unit)."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    switch_units = [unit for unit in casa_api.casa.units if _is_switch_unit(unit)]

    _LOGGER.info(
        "Creating %d button event entities (%d switches × %d buttons)",
        len(switch_units) * _BUTTONS_PER_SWITCH,
        len(switch_units),
        _BUTTONS_PER_SWITCH,
    )

    entities = [
        CasambiButtonEventEntity(casa_api, unit, btn)
        for unit in switch_units
        for btn in range(1, _BUTTONS_PER_SWITCH + 1)
    ]
    if entities:
        async_add_entities(entities)


class CasambiButtonEventEntity(EventEntity):
    """HA EventEntity for one physical button of a Casambi switch unit.

    Automation UI shows: "<Device> Button N: detected <action>"
    where action is one of: press, hold, release, release_after_hold.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:gesture-tap-button"
    _attr_event_types = _BUTTON_ACTIONS

    def __init__(self, api: CasambiApi, unit: Unit, button_number: int) -> None:
        """Initialize the button event entity."""
        self._api = api
        self._unit = unit
        self._button_number = button_number
        self._attr_name = f"Button {button_number}"
        self._attr_unique_id = (
            f"{api.casa.networkId}-unit-{unit.uuid}-button-{button_number}-event"
        )

    async def async_added_to_hass(self) -> None:
        """Register switch event callback."""
        await super().async_added_to_hass()
        self._api.register_switch_event_callback(self._handle_switch_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister switch event callback."""
        self._api.unregister_switch_event_callback(self._handle_switch_event)
        await super().async_will_remove_from_hass()

    @property
    def device_info(self) -> DeviceInfo:
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

    def _is_kinetic_switch(self) -> bool:
        """Return True for EnOcean kinetic switches (e.g. PTM215B)."""
        return "Kinetic" in self._unit.unitType.mode

    @callback
    def _handle_switch_event(self, event_data: dict[str, Any]) -> None:
        """Handle incoming switch event dict from CasambiApi."""
        if event_data.get("unit_id") != self._unit.deviceId:
            return
        if event_data.get("button") != self._button_number:
            return

        # Deduplicate: PTM215B sends both 0x08 and 0x10 in the same BLE packet.
        # Use 0x08 for press/release (correct button numbers).
        # Use 0x10 for hold/release_after_hold (only source for these).
        msg_type = event_data.get("message_type")
        event_type = event_data.get("event", "unknown")
        if self._is_kinetic_switch():
            if msg_type == 0x10 and event_type in ("button_press", "button_release"):
                return
        elif msg_type == 0x08:
            return

        action = _EVENT_TO_ACTION.get(event_type)
        if action is None:
            return

        self._trigger_event(action, {"unit_id": event_data.get("unit_id")})
        self.async_write_ha_state()
