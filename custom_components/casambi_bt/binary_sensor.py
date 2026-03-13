"""Binary Sensor implementation for Casambi."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, CasambiApi
from .entities import CasambiNetworkEntity

_LOGGER = logging.getLogger(__name__)


NETWORK_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="status",
        name="Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_unload_entry(_hass: HomeAssistant, _entry: ConfigEntry) -> bool:
    """Support unloading of entry."""
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor."""
    _LOGGER.debug("Setting up binary sensor entities. config_entry: %s", config_entry)
    api: CasambiApi = hass.data[DOMAIN][config_entry.entry_id]
    binary_sensors = []

    # create network sensors
    for description in NETWORK_SENSORS:
        _LOGGER.debug("Adding CasambiBinarySensorEntity for network...")
        binary_sensors.append(CasambiBinarySensorEntity(api, description))

    if binary_sensors:
        _LOGGER.debug("Adding binary sensor entities...")
        async_add_entities(binary_sensors)
    else:
        _LOGGER.debug("No binary sensor entities available.")

    # Sensor Platform V4: rain (precipitation) and PIR (motion) binary sensors
    from .environment_sensor import async_setup_entry_binary_sensors  # noqa: I001, PLC0415

    await async_setup_entry_binary_sensors(hass, config_entry, async_add_entities)

    # DALI-2 Sensor{Presence,Daylight}: presence binary sensor
    from .dali2_sensor import async_setup_entry_dali2_binary_sensors  # noqa: PLC0415

    await async_setup_entry_dali2_binary_sensors(hass, config_entry, async_add_entities)


class CasambiBinarySensorEntity(BinarySensorEntity, CasambiNetworkEntity):
    """Defines a Casambi Binary Sensor Entity."""

    def __init__(self, api: CasambiApi, description: BinarySensorEntityDescription):
        """Initialize a Casambi Binary Sensor Entity."""
        super().__init__(api=api, description=description)

    @property
    def is_on(self) -> bool:
        """Getter for state."""
        return self._api.available

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True
