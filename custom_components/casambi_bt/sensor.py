"""Sensor platform for Casambi."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .environment_sensor import async_setup_entry as async_setup_environment_sensors
from .network_sensor import async_setup_entry as async_setup_network_sensors
from .switch_config_sensor import async_setup_entry as async_setup_switch_config_sensors
from .switch_sensor import async_setup_entry as async_setup_switch_sensors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi sensor entities."""
    # Set up environmental sensors (Sensor Platform V4: wind, lux, rain, PIR)
    await async_setup_environment_sensors(hass, config_entry, async_add_entities)

    # Set up network configuration sensor
    await async_setup_network_sensors(hass, config_entry, async_add_entities)
    
    # Set up switch configuration sensors
    await async_setup_switch_config_sensors(hass, config_entry, async_add_entities)
    
    # Set up switch event sensors
    await async_setup_switch_sensors(hass, config_entry, async_add_entities)

    # Set up Lamel internal temperature sensor
    from .lamel_controls import async_setup_entry_sensor_lamel
    await async_setup_entry_sensor_lamel(hass, config_entry, async_add_entities)