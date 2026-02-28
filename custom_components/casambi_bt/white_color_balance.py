"""White/Color balance helpers for Casambi PWM+RGB+TW light units.

The WHITECOLORBALANCE control is a 6-bit value not yet decoded by
casambi-bt-revamped (mapped to UnitControlType.UNKOWN=99).

Raw encoding — state byte layout (5 bytes):
  FF FF TT MM 21
    TT = tint/hue byte (do not modify)
    MM = balance byte  = (tint_offset & 0x03) | (raw << 2)
    21 = device constant (do not modify)

  raw ∈ [0..63]  (64 discrete steps)
  tint_offset = MM & 0x03  (lower 2 bits; preserves TT context)
  raw         = (MM >> 2) & 0x3F  ← what _read_bits(state, offset=26, length=6) extracts

Calibrated bi-linear model (Casambi Sensor Platform / Véranda LED type 19803):
  raw  0      →  White=100%  Color=  0%
  raw  0-31   →  White=100% fixed,  Color = raw/31 × 100%
  raw 31      →  White=100%  Color=100%  (factory default — both channels max)
  raw 31-63   →  Color=100% fixed, White = (63-raw)/32 × 100%
  raw 63      →  White=  0%  Color=100%

HA attribute white_balance (0-100%):
  100% = raw  0 = pure White
    0% = raw 63 = pure Color
  ~50% = raw 31 = centre (both channels maxed)

Formula:
  READ : white_balance% = round((63 - raw) × 100 / 63)
  WRITE: raw = round((100 - white_balance%) × 63 / 100)  clamped to [0, 63]

Detection: unit must have both a UnitControlType.RGB control and a
UnitControlType.UNKOWN control with length=6 and default=31.

These helpers are used by light.py (attribute + set method) and __init__.py
(set_white_balance service handler). No HA entity is created from this module.
"""

from __future__ import annotations

import logging

from CasambiBt import Unit, UnitControlType

from . import CasambiApi

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
