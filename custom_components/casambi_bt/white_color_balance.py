"""White/Color balance number entity for Casambi PWM+RGB+TW light units.

The WHITECOLORBALANCE control is a 6-bit cross-fade slider that is not yet
decoded by casambi-bt-revamped, which maps it to UnitControlType.UNKOWN=99.

Raw encoding (offset=26, length=6 in the unit state byte array):
  raw=0  → 100% Couleur / 0% Blanc   (pure color)
  raw=31 → 100% Couleur / 100% Blanc  (both at max — factory default)
  raw=63 → 0% Couleur  / 100% Blanc   (pure white)

HA display range 0-100%:
  0%   = no color  (pure white)  ↔ raw 63
  100% = no white  (pure color)  ↔ raw 0

Detection: any unit that combines a UnitControlType.RGB control with a
UnitControlType.UNKOWN control whose bit-length is 6 and whose maximum value
is 63 (and whose default is 31, the midpoint).  This three-property signature
uniquely identifies WHITECOLORBALANCE on Casambi RGB/TW fixtures without
false-matching other unknown controls on other device types.
"""

from __future__ import annotations

import logging
from typing import cast

from CasambiBt import Unit, UnitControlType

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)

# Signature that identifies a WHITECOLORBALANCE control
_WCB_LENGTH: int = 6
_WCB_MAX: int = 63
_WCB_DEFAULT: int = 31  # midpoint (both channels at 100%)


# ── Detection ─────────────────────────────────────────────────────────────────


def _find_wcb_control(unit: Unit):
    """Return the WHITECOLORBALANCE control for the unit, or None if absent.

    The detection requires THREE matching properties to avoid false-positives
    on other UNKOWN controls that may exist on unrelated device types:
      1. type == UNKOWN  (lib doesn't decode WHITECOLORBALANCE yet)
      2. length == 6, max == 63  (6-bit cross-fade range)
      3. default == 31  (midpoint default — both channels at 100%)
    Additionally the unit must have an RGB control (colour light, not motor).
    """
    has_rgb = any(c.type == UnitControlType.RGB for c in unit.unitType.controls)
    if not has_rgb:
        return None
    for c in unit.unitType.controls:
        if (
            c.type == UnitControlType.UNKOWN
            and c.length == _WCB_LENGTH
            and c.max == _WCB_MAX
            and c.default == _WCB_DEFAULT
        ):
            return c
    return None


def _is_white_color_balance_unit(unit: Unit) -> bool:
    """Return True for units that carry a WHITECOLORBALANCE control."""
    return _find_wcb_control(unit) is not None


# ── Raw-state bit helpers ─────────────────────────────────────────────────────


def _read_bits(raw: bytes, offset: int, length: int) -> int:
    """Read `length` bits at bit `offset` from raw state bytes (little-endian)."""
    byte_offset = offset // 8
    bit_offset = offset % 8
    num_bytes = (length + bit_offset + 7) // 8
    val = int.from_bytes(raw[byte_offset : byte_offset + num_bytes], "little")
    return (val >> bit_offset) & ((1 << length) - 1)


def _write_bits(raw: bytearray, offset: int, length: int, value: int) -> None:
    """Set `length` bits at bit `offset` in mutable raw state bytes (little-endian)."""
    val_shifted = value << (offset % 8)
    byte_len = (length + offset % 8 + 7) // 8
    val_bytes = val_shifted.to_bytes(byte_len, byteorder="little", signed=False)
    clear_mask = ((1 << length) - 1) << (offset % 8)
    for i in range(byte_len):
        byte_idx = offset // 8 + i
        mask_byte = (clear_mask >> (i * 8)) & 0xFF
        raw[byte_idx] = (raw[byte_idx] & ~mask_byte) | (val_bytes[i] & mask_byte)


async def _send_raw_state(api: CasambiApi, unit: Unit, raw: bytearray) -> None:
    """Send a full raw-state packet to the unit (bypasses UnitState abstraction)."""
    from CasambiBt._operation import OpCode  # private but stable  # noqa: PLC0415

    await api.casa._send(unit, bytes(raw), OpCode.SetState)  # noqa: SLF001


# ── Platform setup ────────────────────────────────────────────────────────────


async def async_setup_entry_number_white_color_balance(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create White/Color balance number entities for units that support it."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[CasambiWhiteColorBalance] = []
    for unit in casa_api.get_units():
        if not _is_white_color_balance_unit(unit):
            continue
        entities.append(CasambiWhiteColorBalance(casa_api, unit))

    _LOGGER.info("Creating %d White/Color balance entities", len(entities))
    if entities:
        async_add_entities(entities)


# ── Entity class ──────────────────────────────────────────────────────────────


class CasambiWhiteColorBalance(CasambiUnitEntity, NumberEntity):
    """HA number entity for the WHITECOLORBALANCE cross-fade slider.

    Maps the 6-bit raw control (0-63) to a 0-100% display range where:
      0%   = no color component  (pure white)
      100% = no white component  (pure color)
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a White/Color balance entity for the given unit."""
        ctrl = _find_wcb_control(unit)
        self._ctrl_offset: int = ctrl.offset
        self._ctrl_length: int = ctrl.length
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Blanc / Couleur",
            entity_type="white-color-balance",
        )
        super().__init__(api, desc, unit)
        self._attr_icon = "mdi:palette"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Return the current balance as % (0=white, 100=color)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw_val = _read_bits(unit.state.raw_state, self._ctrl_offset, self._ctrl_length)
        # Invert: raw 0 → 100% color, raw 63 → 0% color
        return round((63 - raw_val) * 100 / 63)

    async def async_set_native_value(self, value: float) -> None:
        """Set the balance from a percentage (0=white, 100=color)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return
        # Invert: 0% → raw 63 (white), 100% → raw 0 (color)
        raw_val = round((100 - value) * 63 / 100)
        raw = bytearray(unit.state.raw_state)
        _write_bits(raw, self._ctrl_offset, self._ctrl_length, max(0, min(63, raw_val)))
        await _send_raw_state(self._api, unit, raw)
