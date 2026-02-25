"""Constants for the Casambi Bluetooth integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "casambi_bt"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SCENE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_IMPORT_GROUPS: Final = "import_groups"
