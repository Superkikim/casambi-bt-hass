"""DALI-2 combined presence + daylight sensor entities for Casambi."""

from __future__ import annotations

import logging
from typing import cast

from CasambiBt import Unit

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)

# State encoding (reverse-engineered from BLE traffic, 2026-03-13):
#
# The unit state is a 16-bit little-endian value:
#   bits  0– 1  (2 bits)  → presence  (0 = absent, 1 = present)
#   bits  2–13  (12 bits) → daylight in lux
#   bit  14     (1 bit)   → reserved / unknown flag
#
# The lib decodes these into unit.state._unknown_controls as a list of
# (bit_offset, bit_size, value) tuples, in the same order.

_PRESENCE_IDX = 0  # _unknown_controls[0] → (0, 2, presence_value)
_LUX_IDX = 1       # _unknown_controls[1] → (2, 12, lux_value)


def _is_dali2_sensor(unit: Unit) -> bool:
    """Return True if unit is a DALI-2 Sensor{Presence,Daylight}."""
    return unit.unitType.mode.startswith("DALI Sensor")


def _unknown_controls(unit: Unit) -> list[tuple[int, int, int]] | None:
    """Return _unknown_controls from unit state, or None if unavailable."""
    if unit.state is None:
        return None
    return getattr(unit.state, "_unknown_controls", None)


async def async_setup_entry_dali2_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DALI-2 lux sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    dali2_units = [u for u in casa_api.casa.units if _is_dali2_sensor(u)]
    _LOGGER.warning(
        "[CASAMBI_DALI2] Creating %d lux sensor(s): %s",
        len(dali2_units),
        [f"{u.name}(id={u.deviceId})" for u in dali2_units],
    )
    entities = [CasambiDali2LuxSensor(casa_api, u) for u in dali2_units]
    if entities:
        async_add_entities(entities)


async def async_setup_entry_dali2_binary_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DALI-2 presence binary sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    dali2_units = [u for u in casa_api.casa.units if _is_dali2_sensor(u)]
    _LOGGER.warning(
        "[CASAMBI_DALI2] Creating %d presence binary sensor(s): %s",
        len(dali2_units),
        [f"{u.name}(id={u.deviceId})" for u in dali2_units],
    )
    entities = [CasambiDali2PresenceSensor(casa_api, u) for u in dali2_units]
    if entities:
        async_add_entities(entities)


class CasambiDali2LuxSensor(CasambiUnitEntity, SensorEntity):
    """Lux (daylight) sensor for a DALI-2 Sensor{Presence,Daylight} unit."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize DALI-2 lux sensor."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key="dali2_lux",
            entity_type="dali2-lux",
        )
        super().__init__(api, desc, unit)
        self._attr_device_class = SensorDeviceClass.ILLUMINANCE
        self._attr_native_unit_of_measurement = "lx"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    # TypedEntityDescription does not extend SensorEntityDescription — override
    # sensor-specific cached properties explicitly to prevent AttributeError.
    @property
    def state_class(self):
        """Return MEASUREMENT state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def options(self):
        """Return None (no fixed option list)."""
        return None

    @property
    def last_reset(self):
        """Return None (current measurement)."""
        return None

    @property
    def native_unit_of_measurement(self):
        """Return lux as unit of measurement."""
        return "lx"

    @property
    def suggested_display_precision(self):
        """Return None (use default precision)."""
        return None

    @property
    def suggested_unit_of_measurement(self):
        """Return None (no conversion suggested)."""
        return None

    @property
    def native_value(self) -> int | None:
        """Return lux value decoded from bits 2–13 of the BLE state."""
        controls = _unknown_controls(cast("Unit", self._obj))
        if not controls or len(controls) <= _LUX_IDX:
            return None
        return controls[_LUX_IDX][2]


class CasambiDali2PresenceSensor(CasambiUnitEntity, BinarySensorEntity):
    """Presence / motion binary sensor for a DALI-2 Sensor{Presence,Daylight} unit."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize DALI-2 presence binary sensor."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key="dali2_presence",
            entity_type="dali2-presence",
        )
        super().__init__(api, desc, unit)
        self._attr_device_class = BinarySensorDeviceClass.MOTION

    @property
    def is_on(self) -> bool | None:
        """Return True when presence is detected (bits 0–1 non-zero)."""
        controls = _unknown_controls(cast("Unit", self._obj))
        if not controls or len(controls) <= _PRESENCE_IDX:
            return None
        return controls[_PRESENCE_IDX][2] != 0
