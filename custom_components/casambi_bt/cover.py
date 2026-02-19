"""Support for Casambi compatible covers (blinds, shutters, venetian blinds)."""

from __future__ import annotations

import logging
from typing import cast

from CasambiBt import Unit, UnitControlType

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
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
    """Create the Casambi cover entities."""
    casa_api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]

    cover_entities = []
    for unit in casa_api.get_units():
        if not _is_cover_unit(unit):
            continue
        controls = {c.type for c in unit.unitType.controls}
        if UnitControlType.SLIDER in controls:
            cover_entities.append(CasambiLamelCover(casa_api, unit))
            _LOGGER.debug("Adding lamel cover (with tilt): %s", unit.name)
        else:
            cover_entities.append(CasambiCover(casa_api, unit))
            _LOGGER.debug("Adding cover: %s", unit.name)

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
        """Return the current position (0=closed, 100=open)."""
        unit = cast("Unit", self._obj)
        if unit.state is not None and unit.state.dimmer is not None:
            return unit.state.dimmer * 100 // 255
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return True if the cover is fully closed."""
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setLevel(unit, 255)

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setLevel(unit, 0)

    async def async_set_cover_position(self, **kwargs) -> None:
        """Move the cover to a specific position (0=closed, 100=open)."""
        unit = cast("Unit", self._obj)
        position = kwargs[ATTR_POSITION]
        await self._api.casa.setLevel(unit, position * 255 // 100)


class CasambiLamelCover(CasambiCover):
    """Cover entity for Casambi venetian blinds with tilt (slat angle) control."""

    def __init__(self, api: CasambiApi, unit: Unit) -> None:
        """Initialize a Casambi lamel cover entity."""
        super().__init__(api, unit)
        self._attr_supported_features |= (
            CoverEntityFeature.OPEN_TILT
            | CoverEntityFeature.CLOSE_TILT
            | CoverEntityFeature.SET_TILT_POSITION
        )

    # Physical range of the Winsol Lamel slat angle
    TILT_MAX_DEGREES: float = 142.0

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return the current tilt (slat angle) position (0=closed, 100=open)."""
        unit = cast("Unit", self._obj)
        if unit.state is not None and unit.state.slider is not None:
            return unit.state.slider * 100 // 255
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return tilt angle in degrees as extra attribute."""
        tilt_pct = self.current_cover_tilt_position
        if tilt_pct is not None:
            return {"tilt_degrees": round(tilt_pct * self.TILT_MAX_DEGREES / 100, 1)}
        return {}

    async def async_open_tilt(self, **kwargs) -> None:
        """Open the slats fully."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setSlider(unit, 255)

    async def async_close_tilt(self, **kwargs) -> None:
        """Close the slats fully."""
        unit = cast("Unit", self._obj)
        await self._api.casa.setSlider(unit, 0)

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        """Set the slat angle (0=closed, 100=open)."""
        unit = cast("Unit", self._obj)
        tilt = kwargs[ATTR_TILT_POSITION]
        await self._api.casa.setSlider(unit, tilt * 255 // 100)
