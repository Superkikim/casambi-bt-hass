"""Switch platform for Casambi integration.

Currently handles:
- Winsol Lamel Intelligent (Star): Automatique, Intelligent, Commencer/Arrêter
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .lamel_controls import async_setup_entry_switch


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi switch entities."""
    await async_setup_entry_switch(hass, config_entry, async_add_entities)
