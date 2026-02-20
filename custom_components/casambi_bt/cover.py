"""Support for Casambi compatible covers (blinds, shutters, venetian blinds)."""

from __future__ import annotations

import logging
from typing import cast

from CasambiBt import Unit, UnitControlType

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CasambiApi
from .const import DOMAIN
from .entities import CasambiUnitEntity, TypedEntityDescription

_LOGGER = logging.getLogger(__name__)


def _is_cover_unit(unit: Unit) -> bool:
    """Return True if the unit should be treated as a cover (blind/shutter).

    Cover units are identified by having an EXT/ mode (externally controlled
    actuator) combined with a DIMMER control (position feedback).
    """
    controls = {c.type for c in unit.unitType.controls}
    return unit.unitType.mode.startswith("EXT/") and UnitControlType.DIMMER in controls


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the Casambi cover entities.

    All covers (SO! shutters and Lamel venetian blinds) use CasambiCover.
    Tilt (slat angle) for Lamel is exposed as a NumberEntity in lamel_controls.py.
    """
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    cover_entities = [
        CasambiCover(casa_api, unit)
        for unit in casa_api.get_units()
        if _is_cover_unit(unit)
    ]

    _LOGGER.info("Creating %d cover entities", len(cover_entities))
    async_add_entities(cover_entities)


class CasambiCover(CasambiUnitEntity, CoverEntity):
    """Defines a Casambi cover entity for blinds and shutters."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a Casambi cover entity."""
        desc = TypedEntityDescription(key=unit.uuid, name=None, entity_type="cover")
        super().__init__(api, desc, unit)

        self._attr_device_class = CoverDeviceClass.BLIND
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
        )

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position (0=closed, 100=open).

        Winsol/Casambi convention is inverted: dimmer=0 means fully open,
        dimmer=255 means fully closed. We invert to match HA convention.
        """
        unit = cast("Unit", self._obj)
        if unit.state is not None and unit.state.dimmer is not None:
            return 100 - (unit.state.dimmer * 100 // 255)
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return True if the cover is fully closed."""
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover (dimmer=0 in Winsol convention)."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setLevel(unit, 0)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover (dimmer=255 in Winsol convention)."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setLevel(unit, 255)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Move the cover to a specific position (0=closed, 100=open)."""
        unit = cast("Unit", self._obj)
        position = kwargs[ATTR_POSITION]
        # Invert: HA 100%=open → Winsol dimmer=0; HA 0%=closed → Winsol dimmer=255
        await self._api.casa.setLevel(unit, (100 - position) * 255 // 100)
