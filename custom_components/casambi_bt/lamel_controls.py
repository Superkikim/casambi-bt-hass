"""Switch, button, number and sensor entities for the Winsol Lamel Intelligent (Star).

The Lamel Intelligent has 7 bytes of state (bit offsets):
  0-3   : sensorgroup header (read-only)
  4-27  : sensorgroupvalue 24 bits → Temperatuur (tag 0) + other sensors (read-only)
  28-35 : DIMMER  → Shadow/Sun position      ← number entity (Ombre / Soleil, 0-100%)
  36-43 : SLIDER  → Louvre Position $pos     ← number entity (Position des louvres, 0-142°)
  44-51 : SLIDER  → Cool/Warm $temp 15-30°C  ← number entity (Froid/Chaud)
  52    : ONOFF   → Automatique $auto         ← switch entity
  53    : ONOFF   → Intelligent $intel        ← switch entity
  54    : ONOFF   → $startstop               ← button entity (toggle louvre open/close)

Writes use casa.setControlValue() which reads the current raw_state bytes, patches
only the target bits, and sends — preserving all other controls including the
read-only sensorgroup blob. Reads use _read_bits() over unit.state.raw_state.
"""

from __future__ import annotations

import logging
from typing import Any, Final, cast

from CasambiBt import Unit, UnitControl, UnitControlType

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)

# ── Sensorgroup accumulator ───────────────────────────────────────────────────
# The Lamel module sends 4 rotating state packets (one per sensor).
# Each packet has a 4-bit header (bits 0-3) identifying which sensor's value
# is in blob_byte0 (bits 4-11).  We accumulate the latest value per header so
# each reading is always available even though only one comes per packet.
# unit_uuid → {header_value: blob_byte0}
_accumulated_lamel: dict[str, dict[int, int]] = {}

# Header value that carries the internal temperature (Temperatuur).
# Derived from cycling pattern: blob_byte0 cycles 78→20→9→5, and header=3→78
# (Travel Distance, confirmed: 78+25×256=6478).  Counting down: header=1→9°C.
# Adjust if extra_state_attributes shows a different mapping.
_TEMP_HEADER: int = 1

# ── Bit-level control offsets (bits in the 7-byte state) ─────────────────────
_CTRL_TEMP_BLOB_OFFSET: Final = 4  # sensorgroupvalue blob start (24 bits, read-only)
_CTRL_SHADOW_OFFSET: Final = (
    28  # DIMMER $shadow : Ombre/Soleil  (8 bits, 0=sun, 255=shadow)
)
_CTRL_POS_OFFSET: Final = 36  # SLIDER $pos   : Louvre position (8 bits, 0-255 = 0-142°)
_CTRL_TEMP_OFFSET: Final = 44  # SLIDER $temp  : Cool/Warm (8 bits, 0-255 = 15-30°C)
_CTRL_AUTO_OFFSET: Final = 52  # ONOFF $auto   : Automatique
_CTRL_INTEL_OFFSET: Final = 53  # ONOFF $intel  : Intelligent
_CTRL_START_OFFSET: Final = 54  # ONOFF $startstop : toggle louvre open/close

_TEMP_MIN: Final = 15.0  # °C (Cool/Warm setpoint range)
_TEMP_MAX: Final = 30.0  # °C


# ── Detection ─────────────────────────────────────────────────────────────────


def _is_lamel_intelligent(unit: Unit) -> bool:
    """Return True for a Winsol Lamel Intelligent (Star) — has DIMMER+SLIDER+ONOFF."""
    ctypes = {c.type for c in unit.unitType.controls}
    return (
        unit.unitType.mode.startswith("EXT/")
        and UnitControlType.DIMMER in ctypes
        and UnitControlType.SLIDER in ctypes
        and UnitControlType.ONOFF in ctypes
    )


# ── Raw-state bit read helper ─────────────────────────────────────────────────


def _read_bits(raw: bytes, offset: int, length: int) -> int:
    """Read `length` bits at bit `offset` from raw state bytes (little-endian)."""
    byte_offset = offset // 8
    bit_offset = offset % 8
    num_bytes = (length + bit_offset + 7) // 8
    val = int.from_bytes(raw[byte_offset : byte_offset + num_bytes], "little")
    return (val >> bit_offset) & ((1 << length) - 1)


def _find_ctrl(unit: Unit, offset: int) -> UnitControl:
    """Return the UnitControl at the given bit offset (must exist)."""
    return next(c for c in unit.unitType.controls if c.offset == offset)


# ── Platform setup functions ──────────────────────────────────────────────────


async def async_setup_entry_switch(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Lamel switch entities (Automatique, Intelligent)."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[CasambiLamelSwitch] = []
    for unit in casa_api.get_units():
        if not _is_lamel_intelligent(unit):
            continue
        for name, bit_offset, icon in [
            ("Automatique", _CTRL_AUTO_OFFSET, "mdi:auto-fix"),
            ("Intelligent", _CTRL_INTEL_OFFSET, "mdi:brain"),
        ]:
            entities.append(CasambiLamelSwitch(casa_api, unit, name, bit_offset, icon))

    _LOGGER.info("Creating %d Lamel switch entities", len(entities))
    if entities:
        async_add_entities(entities)


async def async_setup_entry_button(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Lamel button entities (Commencer/Arrêter toggle)."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[CasambiLamelToggleButton] = []
    for unit in casa_api.get_units():
        if not _is_lamel_intelligent(unit):
            continue
        entities.append(CasambiLamelToggleButton(casa_api, unit))

    _LOGGER.info("Creating %d Lamel button entities", len(entities))
    if entities:
        async_add_entities(entities)


async def async_setup_entry_number(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Lamel number entities (Ombre/Soleil, louvre position, Cool/Warm)."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[NumberEntity] = []
    for unit in casa_api.get_units():
        if not _is_lamel_intelligent(unit):
            continue
        entities.append(CasambiLamelShadowSun(casa_api, unit))
        entities.append(CasambiLamelTiltDegrees(casa_api, unit))
        entities.append(CasambiLamelCoolWarm(casa_api, unit))

    _LOGGER.info("Creating %d Lamel number entities", len(entities))
    if entities:
        async_add_entities(entities)


async def async_setup_entry_sensor_lamel(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Lamel sensor entities (internal temperature)."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[CasambiLamelTemperature] = []
    for unit in casa_api.get_units():
        if not _is_lamel_intelligent(unit):
            continue
        entities.append(CasambiLamelTemperature(casa_api, unit))

    _LOGGER.info("Creating %d Lamel temperature sensor entities", len(entities))
    if entities:
        async_add_entities(entities)


# ── Entity classes ────────────────────────────────────────────────────────────


class CasambiLamelSwitch(CasambiUnitEntity, SwitchEntity):
    """HA switch for one ONOFF control of a Winsol Lamel Intelligent unit."""

    def __init__(
        self,
        api: CasambiApi,
        unit: Unit,
        name: str,
        bit_offset: int,
        icon: str,
    ) -> None:
        """Initialise a Lamel switch for the given ONOFF bit offset."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name=name,
            entity_type=f"lamel-switch-{bit_offset}",
        )
        super().__init__(api, desc, unit)
        self._bit_offset = bit_offset
        self._ctrl: UnitControl = _find_ctrl(unit, bit_offset)
        self._attr_icon = icon

    @property
    def is_on(self) -> bool | None:
        """Return True when the ONOFF control bit is set."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        return bool(_read_bits(unit.state.raw_state, self._bit_offset, 1))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the ONOFF control bit to 1 (on)."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setControlValue(unit, self._ctrl, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the ONOFF control bit to 0 (off)."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setControlValue(unit, self._ctrl, 0)


class CasambiLamelToggleButton(CasambiUnitEntity, ButtonEntity):
    """Button that toggles the louvre between 0° (closed) and 142° (fully open).

    Logic mirrors the Casambi app's Commencer/Arrêter toggle:
      - raw pos ≥ 245 (≈ fully open) → set to 0 (close)
      - raw pos  < 245               → set to 255 (open fully)
    Uses raw state to avoid clobbering SLIDER $temp (Cool/Warm).
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialise the Commencer/Arrêter toggle button for the given unit."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Commencer/Arrêter",
            entity_type="lamel-startstop",
        )
        super().__init__(api, desc, unit)
        self._ctrl: UnitControl = _find_ctrl(unit, _CTRL_POS_OFFSET)
        self._attr_icon = "mdi:play-pause"

    async def async_press(self) -> None:
        """Toggle the louvre between fully open (255) and fully closed (0)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return
        current = _read_bits(unit.state.raw_state, _CTRL_POS_OFFSET, 8)
        target = 0 if current >= 245 else 255
        await self._api.casa.setControlValue(unit, self._ctrl, target)


class CasambiLamelShadowSun(CasambiUnitEntity, NumberEntity):
    """HA number for the Shadow/Sun (DIMMER) — 0%=full sun, 100%=full shadow."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialise the Shadow/Sun number entity for the given unit."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Ombre / Soleil",
            entity_type="lamel-shadow-sun",
        )
        super().__init__(api, desc, unit)
        self._ctrl: UnitControl = _find_ctrl(unit, _CTRL_SHADOW_OFFSET)
        self._attr_icon = "mdi:weather-partly-cloudy"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Return the current Shadow/Sun position as a percentage (0=sun, 100=shadow)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw_val = _read_bits(unit.state.raw_state, _CTRL_SHADOW_OFFSET, 8)
        return raw_val * 100 // 255

    async def async_set_native_value(self, value: float) -> None:
        """Set the Shadow/Sun position from a percentage value (0-100)."""
        unit = cast("Unit", self._obj)
        raw_val = max(0, min(255, round(value * 255 / 100)))
        await self._api.casa.setControlValue(unit, self._ctrl, raw_val)


class CasambiLamelTiltDegrees(CasambiUnitEntity, NumberEntity):
    """HA number for the louvre slat angle (SLIDER $pos) — 0 to 142 degrees."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialise the louvre tilt-angle number entity for the given unit."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Position des louvres",
            entity_type="lamel-tilt-degrees",
        )
        super().__init__(api, desc, unit)
        self._ctrl: UnitControl = _find_ctrl(unit, _CTRL_POS_OFFSET)
        self._attr_icon = "mdi:angle-acute"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 142.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_unit_of_measurement = "°"

    @property
    def native_value(self) -> float | None:
        """Return the current louvre slat angle in degrees (0-142)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw_val = _read_bits(unit.state.raw_state, _CTRL_POS_OFFSET, 8)
        return round(raw_val * 142 / 255)

    async def async_set_native_value(self, value: float) -> None:
        """Set the louvre slat angle from a degree value (0-142)."""
        unit = cast("Unit", self._obj)
        raw_val = max(0, min(255, round(value * 255 / 142)))
        await self._api.casa.setControlValue(unit, self._ctrl, raw_val)


class CasambiLamelCoolWarm(CasambiUnitEntity, NumberEntity):
    """HA number for the Cool/Warm ($temp) slider — temperature setpoint 15-30°C."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialise the Cool/Warm temperature-setpoint number entity for the given unit."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Froid/Chaud",
            entity_type="lamel-coolwarm",
        )
        super().__init__(api, desc, unit)
        self._ctrl: UnitControl = _find_ctrl(unit, _CTRL_TEMP_OFFSET)
        self._attr_icon = "mdi:thermometer"
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_min_value = _TEMP_MIN
        self._attr_native_max_value = _TEMP_MAX
        self._attr_native_step = 0.5
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_unit_of_measurement = "°C"

    @property
    def native_value(self) -> float | None:
        """Return the current Cool/Warm setpoint in degrees Celsius (15-30)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw_val = _read_bits(unit.state.raw_state, _CTRL_TEMP_OFFSET, 8)
        return round(_TEMP_MIN + raw_val * (_TEMP_MAX - _TEMP_MIN) / 255, 1)

    async def async_set_native_value(self, value: float) -> None:
        """Set the Cool/Warm temperature setpoint in degrees Celsius (15-30)."""
        unit = cast("Unit", self._obj)
        raw_val = max(0, min(255, round((value - _TEMP_MIN) * 255 / (_TEMP_MAX - _TEMP_MIN))))
        await self._api.casa.setControlValue(unit, self._ctrl, raw_val)


class CasambiLamelTemperature(CasambiUnitEntity, SensorEntity):
    """Internal temperature sensor of the Winsol Lamel module.

    The temperature is encoded in the sensorgroupvalue blob (bits 4-27 of raw state).
    We read the first byte of the blob (bits 4-11) as a raw value.
    The mapping raw→°C is unconfirmed — extra_state_attributes expose all 3 bytes
    of the blob so the user can calibrate.
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialise the internal-temperature sensor entity for the given unit."""
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Température module",
            entity_type="lamel-temperature",
        )
        super().__init__(api, desc, unit)
        self._attr_icon = "mdi:thermometer"

    # Override SensorEntity cached_properties (TypedEntityDescription lacks these)
    @property
    def state_class(self):
        """Return the state class for this sensor."""
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self):
        """Return the device class for this sensor."""
        return SensorDeviceClass.TEMPERATURE

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement for this sensor."""
        return "°C"

    @property
    def options(self):
        """Return None; this sensor has no discrete options."""
        return None

    @property
    def last_reset(self):
        """Return None; this sensor does not reset."""
        return None

    @property
    def suggested_display_precision(self):
        """Return None; use the default display precision."""
        return None

    @property
    def suggested_unit_of_measurement(self):
        """Return None; no suggested unit override."""
        return None

    @property
    def native_value(self) -> float | None:
        """Return the internal module temperature in degrees Celsius."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw = unit.state.raw_state
        header = _read_bits(raw, 0, 4)  # bits 0-3: sensorgroup header
        blob_byte0 = _read_bits(raw, 4, 8)  # bits 4-11: sensor value

        # Accumulate latest value per header (one packet per sensor, rotating)
        acc = _accumulated_lamel.setdefault(unit.uuid, {})
        acc[header] = blob_byte0

        val = acc.get(_TEMP_HEADER)
        return float(val) if val is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose sensorgroup accumulator for calibration.

        accumulated: {header: blob_byte0} — after 4 packets one entry per sensor.
        Known: header=3 → Travel Distance low byte (confirmed 78+25×256=6478).
        Assumed: header=1 → Températuur (blob_byte0=9 when temp=9°C).
        If temperature_header shows a different header for 9°C, update _TEMP_HEADER.
        """
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return {}
        raw = unit.state.raw_state
        header = _read_bits(raw, 0, 4)
        acc = _accumulated_lamel.get(unit.uuid, {})
        return {
            "raw_state_hex": raw.hex(),
            "current_header": header,
            "accumulated": dict(acc),  # {header: blob_byte0} for all seen headers
            "temperature_header": _TEMP_HEADER,
            "blob_byte1": _read_bits(raw, 12, 8),  # useful for Travel Distance (16-bit)
        }
