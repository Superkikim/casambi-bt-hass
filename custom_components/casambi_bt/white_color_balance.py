"""White/Color balance helpers for Casambi PWM+RGB+TW light units.

The WHITECOLORBALANCE control is a 6-bit cross-fade value decoded natively by
casambi-bt-skk>=0.4.0b2.post6 as UnitControlType.WHITECOLORBALANCE.

Raw encoding:
  raw ∈ [0..63]  (6-bit value)
  raw  0 = pure white channel
  raw 63 = pure color channel

HA attribute white_balance (0–100%):
  100% = raw  0 = pure White
    0% = raw 63 = pure Color

Formula:
  READ : white_balance% = round((63 - raw) × 100 / 63)
  WRITE: raw = round((100 - white_balance%) × 63 / 100)  clamped to [0, 63]

Detection: unit must have a UnitControlType.WHITECOLORBALANCE control.

These helpers are used by light.py (attribute + set method) and __init__.py
(set_white_balance service handler). A number entity is also created for UI
slider access via the number platform (see async_setup_entry_number_white_color_balance).
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

_WCB_RAW_MAX: int = 63  # full 6-bit range


# ── Detection ─────────────────────────────────────────────────────────────────


def _is_white_color_balance_unit(unit: Unit) -> bool:
    """Return True for units that carry a WHITECOLORBALANCE control."""
    return unit.unitType.get_control(UnitControlType.WHITECOLORBALANCE) is not None


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
    """

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a White balance number entity for the given unit."""
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
        if unit.state is None or unit.state.white_balance is None:
            return None
        return round((_WCB_RAW_MAX - unit.state.white_balance) * 100 / _WCB_RAW_MAX)

    async def async_set_native_value(self, value: float) -> None:
        """Set the white balance from a percentage."""
        unit = cast("Unit", self._obj)
        raw_val = max(
            0, min(_WCB_RAW_MAX, round(_WCB_RAW_MAX - value * _WCB_RAW_MAX / 100))
        )
        await self._api.casa.setWhiteColorBalance(unit, raw_val)
