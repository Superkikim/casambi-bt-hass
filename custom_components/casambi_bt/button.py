"""Button platform for Casambi integration.

Currently handles:
- Winsol Lamel Intelligent (Star): Commencer/Arrêter (toggle louvre open/close)
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .lamel_controls import async_setup_entry_button


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Casambi button entities."""
    await async_setup_entry_button(hass, config_entry, async_add_entities)
