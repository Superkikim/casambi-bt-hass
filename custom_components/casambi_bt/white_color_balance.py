"""White/Color balance number entity for Casambi PWM+RGB+TW light units.

The WHITECOLORBALANCE control is a 6-bit value not yet decoded by
casambi-bt-revamped (mapped to UnitControlType.UNKOWN=99).

Raw encoding — state byte layout (5 bytes):
  FF FF TT MM 21
    TT = tint/hue byte (do not modify)
    MM = balance byte  = (tint_offset & 0x03) | (raw << 2)
    21 = device constant (do not modify)

  raw ∈ [0..63]  (64 discrete steps — not percentages)
  tint_offset = MM & 0x03  (lower 2 bits; preserves TT context)
  raw         = (MM >> 2) & 0x3F  ← what _read_bits(state, offset=26, length=6) extracts

Calibrated bi-linear model (Casambi Sensor Platform / Véranda LED type 19803):
  raw  0      →  Blanc=100%  Couleur=  0%  (Casambi app "100% / 0%")
  raw  0-31   →  Blanc=100% fixed,  Couleur = raw/31 × 100%
  raw 31      →  Blanc=100%  Couleur=100%  (factory default — both channels max)
  raw 31-63   →  Couleur=100% fixed, Blanc = (63-raw)/32 × 100%
  raw 63      →  Blanc=  0%  Couleur=100%  (Casambi app "0% / 100%")

HA entity display (0-100%):
  100% = raw  0 = pure Blanc   (Blanc 100%, Couleur   0%)
    0% = raw 63 = pure Couleur (Blanc   0%, Couleur 100%)
  ~50% = raw 31 = centre       (Blanc 100%, Couleur 100% — both maxed)

Formula:
  READ : HA% = round((63 - raw) × 100 / 63)
  WRITE: raw = round((100 - HA%) × 63 / 100)  clamped to [0, 63]

Detection: unit must have both a UnitControlType.RGB control and a
UnitControlType.UNKOWN control with length=6 and default=31.
"""

from __future__ import annotations

import logging
from typing import Any, cast

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
# Note: c.max is None for UNKOWN controls (lib does not populate it)
_WCB_LENGTH: int = 6
_WCB_DEFAULT: int = 31  # midpoint
_WCB_RAW_MAX: int = 63  # full 6-bit range


# ── Detection ─────────────────────────────────────────────────────────────────


def _find_wcb_control(unit: Unit):
    """Return the WHITECOLORBALANCE control for the unit, or None if absent."""
    has_rgb = any(c.type == UnitControlType.RGB for c in unit.unitType.controls)
    if not has_rgb:
        return None
    for c in unit.unitType.controls:
        if (
            c.type == UnitControlType.UNKOWN
            and c.length == _WCB_LENGTH
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

    HA 100% = raw  0 = Blanc 100% / Couleur   0%
    HA  ~50% = raw 31 = Blanc 100% / Couleur 100% (factory default)
    HA   0% = raw 63 = Blanc   0% / Couleur 100%
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a White/Color balance entity for the given unit."""
        ctrl = _find_wcb_control(unit)
        self._ctrl_offset: int = ctrl.offset
        self._ctrl_length: int = ctrl.length
        desc = TypedEntityDescription(
            key=unit.uuid,
            name="Balance des blancs",
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
        """Return the current balance as % (linear: 0%=raw63=Couleur, 100%=raw0=Blanc)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return None
        raw_val = _read_bits(unit.state.raw_state, self._ctrl_offset, self._ctrl_length)
        return round((_WCB_RAW_MAX - raw_val) * 100 / _WCB_RAW_MAX)

    async def async_set_native_value(self, value: float) -> None:
        """Set the balance from a percentage (linear: 0%→raw63, 100%→raw0)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return
        raw_val = max(
            0, min(_WCB_RAW_MAX, round(_WCB_RAW_MAX - value * _WCB_RAW_MAX / 100))
        )
        raw = bytearray(unit.state.raw_state)
        _write_bits(raw, self._ctrl_offset, self._ctrl_length, raw_val)
        await _send_raw_state(self._api, unit, raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw WCB bits for calibration (see wcb_calibrate.py)."""
        unit = cast("Unit", self._obj)
        if unit.state is None or unit.state.raw_state is None:
            return {}
        raw = unit.state.raw_state
        wcb_raw = _read_bits(raw, self._ctrl_offset, self._ctrl_length)
        return {
            "wcb_raw": wcb_raw,
            "raw_state_hex": raw.hex(),
        }
