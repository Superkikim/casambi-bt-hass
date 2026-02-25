"""Environmental sensor entities for Casambi Sensor Platform V4 units."""

from __future__ import annotations

import logging
from typing import Any, cast

from CasambiBt import Unit, UnitControlType

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
#               00 → rain  (0 = dry, 1 = raining)
#               01 → solar radiation
#               10 → wind speed  (raw byte value, display unit TBD)
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

# packet_type → (French name, MDI icon, divisor, state_class)
# Divisor: raw_byte / divisor = displayed app value.
# Rain and PIR are binary (0/1) → no state_class (no graph needed).
# Wind and solar are continuous measurements → MEASUREMENT enables HA history graph.
_SENSOR_SPECS: list[tuple[str, str, int, SensorStateClass | None]] = [
    (
        "Pluie",
        "mdi:weather-rainy",
        1,
        SensorStateClass.MEASUREMENT,
    ),  # type 0: raw value (1=sec, 5=pluie — confirmed)
    (
        "Vent",
        "mdi:weather-windy",
        4,
        SensorStateClass.MEASUREMENT,
    ),  # type 1: raw/4 = vitesse
    (
        "Ensoleillement",
        "mdi:weather-sunny",
        4,
        SensorStateClass.MEASUREMENT,
    ),  # type 2: raw/4 = valeur app (68/4=17 ✓)
    ("Présence (PIR)", "mdi:motion-sensor", 1, None),  # type 3: 0=absent, 1=présent
]


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
      packet_type  = bits[7:6] of raw[1]  (0=rain, 1=solar, 2=wind, 3=PIR)
      raw_value    = raw[2]
    Returns None if the packet is too short to decode.
    """
    if len(raw) < 3:
        return None
    return (raw[1] >> 6) & 0x03, raw[2]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi environmental sensor entities."""
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
        count = min(len(sensor_controls), len(_SENSOR_SPECS))
        _LOGGER.info(
            "Sensor platform '%s' (deviceId=%d): %d SENSOR control(s), creating %d entities",
            unit.name,
            unit.deviceId,
            len(sensor_controls),
            count,
        )

        for sensor_index, (control_index, _control) in enumerate(
            sensor_controls[:count]
        ):
            entities.append(
                CasambiEnvironmentSensor(
                    casa_api,
                    unit,
                    control_index,  # used only to keep the existing unique_id stable
                    sensor_index,  # == packet_type (0–3)
                )
            )

    _LOGGER.info("Creating %d environment sensor entities", len(entities))
    if entities:
        async_add_entities(entities)


class CasambiEnvironmentSensor(CasambiUnitEntity, SensorEntity):
    """HA sensor entity for one sub-sensor of a Casambi Sensor Platform V4."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        control_index: int,
        sensor_index: int,
    ) -> None:
        """Initialize a Casambi environment sensor entity."""
        name, icon, _, sc = _SENSOR_SPECS[sensor_index]
        desc = TypedEntityDescription(
            key=unit.uuid,
            name=name,
            entity_type=f"env-sensor-{control_index}",  # unchanged → stable unique_id
        )
        super().__init__(api, desc, unit)
        self._sensor_index = sensor_index  # = packet_type this entity reads
        self._attr_icon = icon
        self._state_class = sc

    # -----------------------------------------------------------------------
    # Override SensorEntity cached_properties that unconditionally read from
    # entity_description.  TypedEntityDescription extends EntityDescription
    # (not SensorEntityDescription), so those attributes are absent.
    # -----------------------------------------------------------------------
    @property
    def state_class(self):
        """Return the state class for this sensor."""
        return self._state_class

    @property
    def options(self):
        """Return None (no fixed option list for numeric sensors)."""
        return None

    @property
    def last_reset(self):
        """Return None (no accumulated total, only current measurement)."""
        return None

    @property
    def native_unit_of_measurement(self):
        """Return None (raw dimensionless values until units are confirmed)."""
        return None

    @property
    def suggested_display_precision(self):
        """Return None (use default precision)."""
        return None

    @property
    def suggested_unit_of_measurement(self):
        """Return None (no unit conversion suggested)."""
        return None

    # -----------------------------------------------------------------------
    # State
    # -----------------------------------------------------------------------

    @property
    def native_value(self) -> int | None:
        """Return this sensor's most recently accumulated value."""
        unit = cast("Unit", self._obj)
        if unit.state is None:
            return None
        raw = unit.state.raw_state
        if raw is None:
            return None

        decoded = _decode_packet(raw)
        if decoded is None:
            return None
        packet_type, value = decoded

        # Update the shared accumulator for the packet type carried by this packet.
        uuid = unit.uuid
        if uuid not in _accumulated:
            _accumulated[uuid] = {}
        _accumulated[uuid][packet_type] = value

        # Return the last seen value for THIS sensor's packet type, scaled.
        acc_value = _accumulated[uuid].get(self._sensor_index)
        if acc_value is None:
            return None
        divisor = _SENSOR_SPECS[self._sensor_index][2]
        return acc_value // divisor

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
