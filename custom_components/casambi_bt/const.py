"""Constants for the Casambi Bluetooth integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "casambi_bt"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.COVER, Platform.LIGHT, Platform.SCENE, Platform.NUMBER, Platform.SENSOR]

CONF_IMPORT_GROUPS: Final = "import_groups"
