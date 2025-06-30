"""MQTT handler for Casambi switch events."""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Final

try:
    from homeassistant.components import mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER: Final = logging.getLogger(__name__)


class CasambiMQTTHandler:
    """Handle MQTT publishing for Casambi switch events."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the MQTT handler."""
        self.hass = hass
        self.entry_id = entry_id
        self._mqtt_available = MQTT_AVAILABLE and mqtt.async_mqtt_client_is_available(hass)
        
        if not self._mqtt_available:
            _LOGGER.warning("MQTT is not available. Switch events will not be published.")

    async def publish_switch_event(self, event_data: dict[str, Any]) -> None:
        """Publish a switch event to MQTT."""
        if not self._mqtt_available:
            return

        try:
            # Create topic structure
            unit_id = event_data.get("unit_id", "unknown")
            button = event_data.get("button", 0)
            topic = f"{DOMAIN}/switch/{self.entry_id}/{unit_id}/button_{button}"
            
            # Prepare payload
            payload = {
                "unit_id": unit_id,
                "button": button,
                "event": event_data.get("event", "unknown"),
                "action": "press" if event_data.get("event") == "button_press" else "release",
                "timestamp": dt_util.now().isoformat(),
                "message_type": event_data.get("message_type", None),
                "flags": event_data.get("flags", None),
            }
            
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            # Publish to MQTT
            await mqtt.async_publish(
                self.hass,
                topic,
                json.dumps(payload),
                retain=False,
                qos=0,
            )
            
            _LOGGER.debug(f"Published switch event to MQTT: {topic} - {payload}")
            
            # Also publish to a general event topic for easier monitoring
            general_topic = f"{DOMAIN}/switch/{self.entry_id}/events"
            general_payload = payload.copy()
            general_payload["topic"] = topic
            
            await mqtt.async_publish(
                self.hass,
                general_topic,
                json.dumps(general_payload),
                retain=False,
                qos=0,
            )
            
        except Exception:
            _LOGGER.exception("Error publishing switch event to MQTT")

    def is_available(self) -> bool:
        """Check if MQTT is available."""
        return self._mqtt_available