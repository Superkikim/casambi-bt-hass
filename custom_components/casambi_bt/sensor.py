"""Sensor platform for Casambi."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .switch_sensor import async_setup_entry as async_setup_switch_sensors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi sensor entities."""
    # Set up switch sensors
    await async_setup_switch_sensors(hass, config_entry, async_add_entities)