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

# Sensor Platform V4 packet_type mapping (reverse-engineered from BLE traffic):
#
# The device cycles through 4 BLE state packets, one per sensor, ~every 4 s.
# packet_type = raw[1] bits[7:6]:
#   0 → rain  (1 = dry, 5 = raining)
#   1 → wind speed  (raw/4 = app value)
#   2 → solar radiation  (raw/4 = app value)
#   3 → PIR presence (0 = absent, 1 = present)
#
# Accumulation is now handled by the library (unit.sensor_cache).

# Numeric sensors: packet_type → (translation_key, icon, divisor)
_NUMERIC_SPECS: dict[int, tuple[str, str, int]] = {
    1: ("wind", "mdi:weather-windy", 4),
    2: ("solar", "mdi:weather-sunny", 4),
}

# Binary sensors: packet_type → (translation_key, icon, device_class, on_threshold)
_BINARY_SPECS: dict[int, tuple[str, str, BinarySensorDeviceClass, int]] = {
    0: ("rain", "mdi:weather-rainy", BinarySensorDeviceClass.MOISTURE, 2),
    3: ("pir", "mdi:motion-sensor", BinarySensorDeviceClass.MOTION, 1),
}


def _is_sensor_platform(unit: Unit) -> bool:
    """Return True if unit is a Casambi Sensor Platform (EXT/Elements mode, SENSOR controls, no DIMMER)."""
    controls = {c.type for c in unit.unitType.controls}
    return (
        unit.unitType.mode.startswith("EXT/Elements")
        and UnitControlType.SENSOR in controls
        and UnitControlType.DIMMER not in controls
    )


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

        _LOGGER.info(
            "Sensor platform '%s' (deviceId=%d): creating numeric sensors",
            unit.name,
            unit.deviceId,
        )
        for packet_type in _NUMERIC_SPECS:
            entities.append(CasambiEnvironmentSensor(casa_api, unit, packet_type))

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

        for packet_type in _BINARY_SPECS:
            entities.append(
                CasambiEnvironmentBinarySensor(casa_api, unit, packet_type)
            )

    _LOGGER.info("Creating %d binary environment sensor entities", len(entities))
    if entities:
        async_add_entities(entities)


# ── Numeric sensor entity ──────────────────────────────────────────────────────


class CasambiEnvironmentSensor(CasambiUnitEntity, SensorEntity):
    """HA sensor entity for a numeric sub-sensor of a Casambi Sensor Platform V4."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        packet_type: int,
    ) -> None:
        """Initialize a numeric environment sensor entity."""
        tk, icon, divisor = _NUMERIC_SPECS[packet_type]
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key=tk,
            entity_type=f"env-sensor-{packet_type}",  # stable unique_id
        )
        super().__init__(api, desc, unit)
        self._packet_type = packet_type
        self._divisor = divisor
        self._attr_icon = icon

    # TypedEntityDescription extends EntityDescription, not SensorEntityDescription,
    # so HA's SensorEntity cached_properties would fail reading state_class etc.
    # Override them explicitly to prevent AttributeError.

    @property
    def state_class(self):
        """Return MEASUREMENT state class for continuous sensor."""
        return SensorStateClass.MEASUREMENT

    @property
    def options(self):
        """Return None (no fixed option list)."""
        return None

    @property
    def last_reset(self):
        """Return None (current measurement, no accumulated total)."""
        return None

    @property
    def native_unit_of_measurement(self):
        """Return None (raw dimensionless values)."""
        return None

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
        """Return this sensor's most recently received value from the library cache."""
        unit = cast("Unit", self._obj)
        raw_value = unit.sensor_cache.get(self._packet_type)
        if raw_value is None:
            return None
        return raw_value // self._divisor

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic info for troubleshooting."""
        unit = cast("Unit", self._obj)
        return {
            "packet_type": self._packet_type,
            "sensor_cache": dict(unit.sensor_cache),
        }


# ── Binary sensor entity ───────────────────────────────────────────────────────


class CasambiEnvironmentBinarySensor(CasambiUnitEntity, BinarySensorEntity):
    """HA binary sensor entity for a binary sub-sensor of a Casambi Sensor Platform V4."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        packet_type: int,
    ) -> None:
        """Initialize a binary environment sensor entity."""
        tk, icon, device_class, threshold = _BINARY_SPECS[packet_type]
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key=tk,
            entity_type=f"env-sensor-{packet_type}",  # stable unique_id
        )
        super().__init__(api, desc, unit)
        self._packet_type = packet_type
        self._on_threshold = threshold
        self._attr_icon = icon
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        """Return True when rain is detected or motion is present."""
        unit = cast("Unit", self._obj)
        raw_value = unit.sensor_cache.get(self._packet_type)
        if raw_value is None:
            return None
        return raw_value >= self._on_threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic info for troubleshooting."""
        unit = cast("Unit", self._obj)
        return {
            "packet_type": self._packet_type,
            "sensor_cache": dict(unit.sensor_cache),
        }
