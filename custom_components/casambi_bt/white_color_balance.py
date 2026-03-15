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
(set_white_balance service handler). A number entity is also created for UI
slider access via the number platform (see async_setup_entry_number_white_color_balance).
"""

from __future__ import annotations

import logging
from typing import cast

from CasambiBt import Unit, UnitControl, UnitControlType

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


# ── Platform setup ────────────────────────────────────────────────────────────


async def async_setup_entry_number_white_color_balance(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create White balance number entities for units that support it."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[CasambiWhiteColorBalance] = [
        CasambiWhiteColorBalance(casa_api, unit)
        for unit in casa_api.get_units()
        if _is_white_color_balance_unit(unit)
    ]

    _LOGGER.info("Creating %d white balance number entities", len(entities))
    if entities:
        async_add_entities(entities)


# ── Entity class ──────────────────────────────────────────────────────────────


class CasambiWhiteColorBalance(CasambiUnitEntity, NumberEntity):
    """HA number entity for the WHITECOLORBALANCE cross-fade slider.

    100% = raw  0 = pure White
      0% = raw 63 = pure Color
    ~50% = raw 31 = centre (both channels maxed — factory default)
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a White balance number entity for the given unit."""
        ctrl = _find_wcb_control(unit)
        self._ctrl: UnitControl = ctrl
        desc = TypedEntityDescription(
            key=unit.uuid,
            translation_key="white_balance",
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
        """Return the current white balance as %."""
        unit = cast("Unit", self._obj)
        if unit.state is None:
            return None
        entry = next(
            (v for o, _l, v in unit.state.unknown_controls if o == self._ctrl.offset),
            None,
        )
        if entry is None:
            return None
        return round((_WCB_RAW_MAX - entry) * 100 / _WCB_RAW_MAX)

    async def async_set_native_value(self, value: float) -> None:
        """Set the white balance from a percentage."""
        unit = cast("Unit", self._obj)
        raw_val = max(
            0, min(_WCB_RAW_MAX, round(_WCB_RAW_MAX - value * _WCB_RAW_MAX / 100))
        )
        await self._api.casa.setControlValue(unit, self._ctrl, raw_val)
