"""Environmental sensor entities for Casambi Sensor Platform V4 units."""

from __future__ import annotations

import logging
from typing import Any, cast

from CasambiBt import Unit, UnitControlType

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)

# Sensor Platform V4 state encoding (reverse-engineered from BLE traffic):
#
# The device cycles through 4 BLE state packets, one per sensor, ~every 4 s.
# Each 5-byte packet encodes a single sensor reading:
#   byte[0] = 0x04  (constant)
#   byte[1] = packet type encoded in bits[7:6]:
#               00 → rain  (1 = dry, 5 = raining)
#               01 → wind speed  (raw/4 = app value)
#               10 → solar radiation  (raw/4 = app value, e.g. 68/4=17)
#               11 → PIR presence (0 = absent, 1 = present)
#   byte[2] = sensor value (raw)
#   byte[3] = 0x00 (constant)
#   byte[4] = 0x3C (constant)
#
# Because all 4 HA entities share the same unit state (which holds the last
# packet received), we accumulate per-type values in a module-level dict so
# each entity can always return its most recent reading.

# unit_uuid → {packet_type: raw_value}
_accumulated: dict[str, dict[int, int]] = {}

# Numeric sensors: sensor_index → (translation_key, icon, divisor)
_NUMERIC_SPECS: dict[int, tuple[str, str, int]] = {
    1: ("wind",  "mdi:weather-windy", 4),
    2: ("solar", "mdi:weather-sunny", 4),
}

# Binary sensors: sensor_index → (translation_key, icon, device_class, on_threshold)
_BINARY_SPECS: dict[int, tuple[str, str, BinarySensorDeviceClass, int]] = {
    0: ("rain", "mdi:weather-rainy", BinarySensorDeviceClass.PRECIPITATION, 2),
    3: ("pir",  "mdi:motion-sensor", BinarySensorDeviceClass.MOTION,        1),
}

_ALL_SENSOR_COUNT = len(_NUMERIC_SPECS) + len(_BINARY_SPECS)


def _is_sensor_platform(unit: Unit) -> bool:
    """Return True if unit is a Casambi Sensor Platform (EXT/ mode, SENSOR controls, no DIMMER)."""
    controls = {c.type for c in unit.unitType.controls}
    return (
        unit.unitType.mode.startswith("EXT/")
        and UnitControlType.SENSOR in controls
        and UnitControlType.DIMMER not in controls
    )


def _decode_packet(raw: bytes) -> tuple[int, int] | None:
    """Decode a Sensor Platform V4 BLE state packet.

    Returns (packet_type, raw_value):
      packet_type  = bits[7:6] of raw[1]  (0=rain, 1=wind, 2=solar, 3=PIR)
      raw_value    = raw[2]
    Returns None if the packet is too short to decode.
    """
    if len(raw) < 3:
        return None
    return (raw[1] >> 6) & 0x03, raw[2]


def _iter_sensor_controls(unit: Unit, count: int):
    """Yield (sensor_index, control_index) for the first `count` SENSOR controls."""
    sensor_controls = [
        (i, c)
        for i, c in enumerate(unit.unitType.controls)
        if c.type == UnitControlType.SENSOR
    ]
    for sensor_index, (control_index, _ctrl) in enumerate(sensor_controls[:count]):
        yield sensor_index, control_index


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up numeric environment sensors (wind, solar) for Sensor Platform V4."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
    for unit in casa_api.casa.units:
        if not _is_sensor_platform(unit):
            continue

        sensor_controls = [
            (i, c)
            for i, c in enumerate(unit.unitType.controls)
            if c.type == UnitControlType.SENSOR
        ]
        count = min(len(sensor_controls), _ALL_SENSOR_COUNT)
        _LOGGER.info(
            "Sensor platform '%s' (deviceId=%d): %d SENSOR control(s)",
            unit.name,
            unit.deviceId,
            len(sensor_controls),
        )

        for sensor_index, control_index in _iter_sensor_controls(unit, count):
            if sensor_index in _NUMERIC_SPECS:
                entities.append(
                    CasambiEnvironmentSensor(casa_api, unit, control_index, sensor_index)
                )

    _LOGGER.info("Creating %d numeric environment sensor entities", len(entities))
    if entities:
        async_add_entities(entities)


async def async_setup_entry_binary_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary environment sensors (rain, PIR) for Sensor Platform V4."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
    for unit in casa_api.casa.units:
        if not _is_sensor_platform(unit):
            continue

        sensor_controls = [
            (i, c)
            for i, c in enumerate(unit.unitType.controls)
            if c.type == UnitControlType.SENSOR
        ]
        count = min(len(sensor_controls), _ALL_SENSOR_COUNT)

        for sensor_index, control_index in _iter_sensor_controls(unit, count):
            if sensor_index in _BINARY_SPECS:
                entities.append(
                    CasambiEnvironmentBinarySensor(
                        casa_api, unit, control_index, sensor_index
                    )
                )

    _LOGGER.info("Creating %d binary environment sensor entities", len(entities))
    if entities:
        async_add_entities(entities)


# ── Shared accumulator helper ──────────────────────────────────────────────────


def _update_accumulator(unit: Unit, raw: bytes) -> dict[int, int]:
    """Decode packet, update accumulator and return it."""
    decoded = _decode_packet(raw)
    if decoded is not None:
        packet_type, value = decoded
        uuid = unit.uuid
        if uuid not in _accumulated:
            _accumulated[uuid] = {}
        _accumulated[uuid][packet_type] = value
    return _accumulated.get(unit.uuid, {})


# ── Numeric sensor entity ──────────────────────────────────────────────────────


class CasambiEnvironmentSensor(CasambiUnitEntity, SensorEntity):
    """HA sensor entity for a numeric sub-sensor of a Casambi Sensor Platform V4."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        control_index: int,
        sensor_index: int,
    ) -> None:
        """Initialize a numeric environment sensor entity."""
        tk, icon, divisor = _NUMERIC_SPECS[sensor_index]
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key=tk,
            entity_type=f"env-sensor-{control_index}",  # unchanged → stable unique_id
        )
        super().__init__(api, desc, unit)
        self._sensor_index = sensor_index
        self._divisor = divisor
        self._attr_icon = icon
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return this sensor's most recently accumulated value."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        acc = _update_accumulator(unit, unit.state.raw_state)
        acc_value = acc.get(self._sensor_index)
        if acc_value is None:
            return None
        return acc_value // self._divisor

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic info for troubleshooting."""
        unit = cast("Unit", self._obj)
        raw = unit.state.raw_state if unit.state else None
        decoded = _decode_packet(raw) if raw else None
        return {
            "raw_state_hex": raw.hex() if raw else None,
            "current_packet_type": decoded[0] if decoded else None,
            "current_packet_value": decoded[1] if decoded else None,
            "sensor_cache": dict(_accumulated.get(unit.uuid, {})),
        }


# ── Binary sensor entity ───────────────────────────────────────────────────────


class CasambiEnvironmentBinarySensor(CasambiUnitEntity, BinarySensorEntity):
    """HA binary sensor entity for a binary sub-sensor of a Casambi Sensor Platform V4."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        control_index: int,
        sensor_index: int,
    ) -> None:
        """Initialize a binary environment sensor entity."""
        tk, icon, device_class, threshold = _BINARY_SPECS[sensor_index]
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key=tk,
            entity_type=f"env-sensor-{control_index}",  # same pattern → stable unique_id
        )
        super().__init__(api, desc, unit)
        self._sensor_index = sensor_index
        self._on_threshold = threshold
        self._attr_icon = icon
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        """Return True when rain is detected or motion is present."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        acc = _update_accumulator(unit, unit.state.raw_state)
        acc_value = acc.get(self._sensor_index)
        if acc_value is None:
            return None
        return acc_value >= self._on_threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic info for troubleshooting."""
        unit = cast("Unit", self._obj)
        raw = unit.state.raw_state if unit.state else None
        decoded = _decode_packet(raw) if raw else None
        return {
            "raw_state_hex": raw.hex() if raw else None,
            "current_packet_type": decoded[0] if decoded else None,
            "current_packet_value": decoded[1] if decoded else None,
            "sensor_cache": dict(_accumulated.get(unit.uuid, {})),
        }
