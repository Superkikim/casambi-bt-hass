"""Environmental sensor entities for Casambi sensor platform units."""

from __future__ import annotations

import logging
from typing import Any, cast

from CasambiBt import Unit, UnitControlType

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)


def _is_sensor_platform(unit: Unit) -> bool:
    """Return True if unit is a Casambi environmental sensor platform.

    Sensor platforms have EXT/ mode (external actuator/sensor) with at least
    one SENSOR-type control and no DIMMER control (to distinguish from covers).
    """
    controls = {c.type for c in unit.unitType.controls}
    return (
        unit.unitType.mode.startswith("EXT/")
        and UnitControlType.SENSOR in controls
        and UnitControlType.DIMMER not in controls
    )


def _extract_sensor_value(raw_state: bytes, control) -> int | None:
    """Extract a SENSOR control value from raw state bytes using bit arithmetic.

    Replicates the same extraction logic used by the library for other control
    types (DIMMER, SLIDER, etc.) — offset in bits, little-endian byte order.
    """
    byte_len = (control.length + control.offset % 8 - 1) // 8 + 1
    start = control.offset // 8
    if start + byte_len > len(raw_state):
        return None
    c_bytes = raw_state[start : start + byte_len]
    c_int = int.from_bytes(c_bytes, byteorder="little", signed=False)
    c_int >>= control.offset % 8
    c_int &= 2**control.length - 1
    return c_int


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi environmental sensor entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    sensor_entities = []
    for unit in casa_api.casa.units:
        if not _is_sensor_platform(unit):
            continue

        sensor_controls = [
            (i, c)
            for i, c in enumerate(unit.unitType.controls)
            if c.type == UnitControlType.SENSOR
        ]

        _LOGGER.info(
            "Sensor platform '%s' (deviceId=%d): found %d SENSOR control(s): %s",
            unit.name,
            unit.deviceId,
            len(sensor_controls),
            [
                (i, f"offset={c.offset} len={c.length} min={c.min} max={c.max}")
                for i, c in sensor_controls
            ],
        )

        for sensor_index, (control_index, control) in enumerate(sensor_controls):
            sensor_entities.append(
                CasambiEnvironmentSensor(
                    casa_api, unit, control, control_index, sensor_index
                )
            )

    _LOGGER.info("Creating %d environment sensor entities", len(sensor_entities))
    if sensor_entities:
        async_add_entities(sensor_entities)


class CasambiEnvironmentSensor(CasambiUnitEntity, SensorEntity):
    """Sensor entity for one SENSOR-type control on a Casambi sensor platform."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        control,
        control_index: int,
        sensor_index: int,
    ) -> None:
        """Initialize a Casambi environmental sensor."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name=f"Sensor {sensor_index + 1}",
            entity_type=f"env-sensor-{control_index}",
        )
        super().__init__(api, desc, unit)
        self._control = control
        self._control_index = control_index
        self._sensor_index = sensor_index

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:weather-partly-cloudy"

    @property
    def native_value(self) -> int | None:
        """Return the current sensor value as a raw integer."""
        unit = cast("Unit", self._obj)
        if unit.state is None:
            return None
        raw = unit.state.raw_state
        if raw is None:
            return None
        return _extract_sensor_value(raw, self._control)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes for identifying the physical sensor."""
        unit = cast("Unit", self._obj)
        raw = unit.state.raw_state if unit.state else None
        return {
            "control_index": self._control_index,
            "bit_offset": self._control.offset,
            "bit_length": self._control.length,
            "value_min": self._control.min,
            "value_max": self._control.max,
            "raw_state_hex": raw.hex() if raw else None,
        }
