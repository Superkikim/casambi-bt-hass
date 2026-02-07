"""The Casambi Bluetooth integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
import contextlib
import json
import logging
from pathlib import Path
from typing import Final
import yaml

from CasambiBt import Casambi, Group, Scene, Unit, UnitControlType
from CasambiBt.errors import AuthenticationError, BluetoothError, NetworkNotFoundError

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.httpx_client import get_async_client

from .const import DOMAIN, PLATFORMS

_LOGGER: Final = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Casambi Bluetooth from a config entry."""
    _LOGGER.debug(
        "Setting up entry title=%s entry_id=%s unique_id=%s address=%s",
        entry.title,
        entry.entry_id,
        entry.unique_id,
        entry.data.get(CONF_ADDRESS),
    )

    # Help testers verify the installed library build quickly.
    try:
        import CasambiBt as _casambi_pkg  # local import for path logging + version

        lib_ver = getattr(_casambi_pkg, "__version__", "unknown")
        lib_path = getattr(_casambi_pkg, "__file__", "unknown")
    except Exception:
        lib_ver = "unknown"
        lib_path = "unknown"
    _LOGGER.info("Using casambi-bt-revamped=%s (%s)", lib_ver, lib_path)

    # Check if we need to migrate from old data structure
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        existing_data = hass.data[DOMAIN][entry.entry_id]
        if isinstance(existing_data, CasambiApi):
            _LOGGER.warning("Migrating from old Casambi data structure")
            # Disconnect the old API instance
            with contextlib.suppress(Exception):
                await existing_data.disconnect()

    api = CasambiApi(hass, entry, entry.data[CONF_ADDRESS], entry.data[CONF_PASSWORD])
    await api.connect()

    # No buffering/dedup here; emit exactly what the library delivers.
    def _emit_event(event: dict) -> None:
        """Emit one event to HA."""
        # Convert any bytes objects to hex strings for JSON serialization
        raw_packet = event.get("raw_packet")
        decrypted_data = event.get("decrypted_data")
        payload_hex = event.get("payload_hex")
        extra_data = event.get("extra_data")

        # The library provides ASCII-hex bytes for raw_packet/decrypted_data/payload_hex.
        # Convert bytes -> str via ASCII decode directly (not .hex()).
        raw_packet_str = (
            raw_packet.decode("ascii") if isinstance(raw_packet, (bytes, bytearray)) else raw_packet
        )
        decrypted_data_str = (
            decrypted_data.decode("ascii") if isinstance(decrypted_data, (bytes, bytearray)) else decrypted_data
        )
        payload_hex_str = (
            payload_hex.decode("ascii") if isinstance(payload_hex, (bytes, bytearray)) else payload_hex
        )

        unit_id = event.get("unit_id")
        button = event.get("button")
        action = event.get("event")
        event_id = event.get("event_id")

        # Optional INVOCATION metadata (new parser)
        opcode = event.get("opcode")
        target_type = event.get("target_type")
        origin = event.get("origin")
        age = event.get("age")
        invocation_flags = event.get("invocation_flags", event.get("flags"))
        button_event_index = event.get("button_event_index")
        param_p = event.get("param_p")
        param_s = event.get("param_s")

        hass.bus.async_fire(
            f"{DOMAIN}_switch_event",
            {
                "entry_id": entry.entry_id,
                "unit_id": unit_id,
                "button": button,
                "action": action,
                "message_type": event.get("message_type"),
                "flags": invocation_flags,
                "event_id": event_id,
                "opcode": opcode,
                "target_type": target_type,
                "origin": origin,
                "age": age,
                "button_event_index": button_event_index,
                "param_p": param_p,
                "param_s": param_s,
                # NotifyInput fields (target_type=0x12), exposed by casambi-bt-revamped parser
                "input_index": event.get("input_index"),
                "input_code": event.get("input_code"),
                "input_b1": event.get("input_b1"),
                "input_channel": event.get("input_channel"),
                "input_value16": event.get("input_value16"),
                "input_mapped_event": event.get("input_mapped_event"),
                "packet_sequence": event.get("packet_sequence"),
                "arrival_sequence": event.get("arrival_sequence"),
                "raw_packet": raw_packet_str,
                "decrypted_data": decrypted_data_str,
                "message_position": event.get("message_position"),
                "payload_hex": payload_hex_str,
                "extra_data": extra_data.hex() if isinstance(extra_data, bytes) else extra_data,
            }
        )

    # Register switch event handler that fires Home Assistant events
    def handle_switch_event(event_data: dict) -> None:
        """Immediately emit switch events from the library."""
        _emit_event(event_data)

    # Register the event handler if the library supports it
    if hasattr(api.casa, 'registerSwitchEventHandler'):
        api.register_switch_event_callback(handle_switch_event)
        _LOGGER.info("Switch event handler registered - events will fire as casambi_bt_switch_event")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_setup_services(hass)

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Casambi integration."""
    
    # Register get_network_config service if not already registered
    if not hass.services.has_service(DOMAIN, "get_network_config"):
        async def handle_get_network_config(call: ServiceCall) -> dict:
            """Handle the get_network_config service call."""
            unit_id = call.data.get("unit_id")
            output_format = call.data.get("format", "json")
            
            # Get the first configured entry (could be enhanced to support multiple)
            entries = hass.config_entries.async_entries(DOMAIN)
            if not entries:
                raise ValueError("No Casambi integration configured")
            
            entry = entries[0]
            casa_api: CasambiApi = hass.data[DOMAIN][entry.entry_id]
            
            # Get the raw network data
            raw_data = casa_api.casa.rawNetworkData
            if not raw_data:
                raise ValueError("No network data available")
            
            # If unit_id is specified, extract just that unit's data
            if unit_id is not None:
                network = raw_data.get("network", {})
                units = network.get("units", [])
                
                unit_data = None
                for unit in units:
                    if unit.get("deviceID") == unit_id:
                        unit_data = unit
                        break
                
                if not unit_data:
                    raise ValueError(f"Unit with ID {unit_id} not found")
                
                result_data = {
                    "unit": unit_data,
                    "network_id": casa_api.casa.networkId,
                    "network_name": casa_api.casa.networkName,
                }
            else:
                # Return full network config
                result_data = raw_data
            
            # Format the output
            if output_format == "yaml":
                return {"config": yaml.dump(result_data, default_flow_style=False)}
            else:
                return {"config": json.dumps(result_data, indent=2)}
        
        # Register the service
        hass.services.async_register(
            DOMAIN,
            "get_network_config",
            handle_get_network_config,
            supports_response="only",
        )
        _LOGGER.info("Registered get_network_config service")
    
    # Register update_button_config service if not already registered
    if not hass.services.has_service(DOMAIN, "update_button_config"):
        async def handle_update_button_config(call: ServiceCall) -> None:
            """Handle the update_button_config service call."""
            unit_id = call.data.get("unit_id")
            button_index = call.data.get("button_index")
            action_type = call.data.get("action_type")
            target_unit_id = call.data.get("target_unit_id")
            
            # Get the first available CasambiApi instance
            casa_api = None
            for entry_id in hass.data.get(DOMAIN, {}):
                casa_api = hass.data[DOMAIN][entry_id]
                break
            
            if not casa_api:
                raise ValueError("No Casambi connection available")
            
            # Update cached button config in library
            await casa_api.casa.update_button_config(
                unit_id=unit_id,
                button_index=button_index,
                action_type=action_type,
                target_id=target_unit_id,
            )

            _LOGGER.info(
                "Updated button %s on unit %s to %s targeting %s (cache)",
                button_index,
                unit_id,
                action_type,
                target_unit_id,
            )

            # Immediately apply the switchConfig to the device (auto method)
            try:
                # Fast path: try SetParameter first with default tag 1
                await casa_api.casa.apply_switch_config_ble(unit_id=unit_id, parameter_tag=1)
                _LOGGER.info(
                    "Applied switchConfig via SetParameter after update (unit=%s, tag=1)", unit_id
                )
            except Exception as e:
                _LOGGER.info(
                    "SetParameter apply failed for unit %s after update (%s). Falling back to ExtPacket.",
                    unit_id,
                    e,
                )
                await casa_api.casa.apply_switch_config_ble_large(unit_id=unit_id)
                _LOGGER.info(
                    "Applied switchConfig via ExtPacket after update (unit=%s)", unit_id
                )
    
        # Register the update_button_config service
        hass.services.async_register(
            DOMAIN,
            "update_button_config",
            handle_update_button_config,
        )
        _LOGGER.info("Registered update_button_config service")

    # Register apply_switch_config service if not already registered
    if not hass.services.has_service(DOMAIN, "apply_switch_config"):
        async def handle_apply_switch_config(call: ServiceCall) -> None:
            """Handle the apply_switch_config service call."""
            unit_id = call.data.get("unit_id")
            method = (call.data.get("method") or "auto").lower()
            parameter_tag = call.data.get("parameter_tag")

            # Get the first available CasambiApi instance
            casa_api = None
            for entry_id in hass.data.get(DOMAIN, {}):
                casa_api = hass.data[DOMAIN][entry_id]
                break
            if not casa_api:
                raise ValueError("No Casambi connection available")

            if method == "set_parameter":
                tag = 1 if parameter_tag is None else int(parameter_tag)
                await casa_api.casa.apply_switch_config_ble(unit_id=unit_id, parameter_tag=tag)
                _LOGGER.info(
                    "Applied switchConfig via SetParameter (unit=%s, tag=%s)", unit_id, tag
                )
            elif method == "ext":
                await casa_api.casa.apply_switch_config_ble_large(unit_id=unit_id)
                _LOGGER.info(
                    "Applied switchConfig via ExtPacket (unit=%s)", unit_id
                )
            else:
                # Auto: try SetParameter first, fall back to ExtPacket on size error
                try:
                    tag = 1 if parameter_tag is None else int(parameter_tag)
                    await casa_api.casa.apply_switch_config_ble(unit_id=unit_id, parameter_tag=tag)
                    _LOGGER.info(
                        "Applied switchConfig via SetParameter (unit=%s, tag=%s)", unit_id, tag
                    )
                except Exception as e:
                    # Fallback to ext method on size or protocol error
                    _LOGGER.info(
                        "SetParameter failed for unit %s (%s). Falling back to ExtPacket.",
                        unit_id,
                        e,
                    )
                    await casa_api.casa.apply_switch_config_ble_large(unit_id=unit_id)
                    _LOGGER.info(
                        "Applied switchConfig via ExtPacket (unit=%s)", unit_id
                    )

        # Register the apply_switch_config service
        hass.services.async_register(
            DOMAIN,
            "apply_switch_config",
            handle_apply_switch_config,
        )
        _LOGGER.info("Registered apply_switch_config service")

    # Register dump_classic_diagnostics service if not already registered
    if not hass.services.has_service(DOMAIN, "dump_classic_diagnostics"):
        async def handle_dump_classic_diagnostics(call: ServiceCall) -> dict:
            """Log Classic protocol diagnostics (safe for sharing).

            Returns enhanced diagnostics including:
            - Full connection state
            - Last 20 TX packets with timestamps
            - Last 20 RX packets with timestamps
            - GATT subscription status
            - Any errors encountered
            """
            entry_id = call.data.get("entry_id")
            include_packet_history = call.data.get("include_packets", True)
            include_network_config = call.data.get("include_network_config", False)

            casa_api: CasambiApi | None = None
            if entry_id:
                casa_api = hass.data.get(DOMAIN, {}).get(entry_id)
                if casa_api is None:
                    raise ValueError(f"Entry id {entry_id} not found in hass.data[{DOMAIN!r}]")
            else:
                for _eid in hass.data.get(DOMAIN, {}):
                    casa_api = hass.data[DOMAIN][_eid]
                    break
                if casa_api is None:
                    raise ValueError("No Casambi connection available")

            casa = casa_api.casa
            client = getattr(casa, "_casaClient", None)
            network = getattr(casa, "_casaNetwork", None)

            units = getattr(casa, "units", []) or []
            units_with_security_key = sum(
                1 for u in units if getattr(u, "securityKey", None) is not None
            )

            protocol_mode = getattr(client, "protocolMode", None)
            protocol_mode_name = getattr(protocol_mode, "name", None)

            conn_hash8 = getattr(client, "_classicConnHash8", None)
            conn_hash8_hex = conn_hash8.hex() if isinstance(conn_hash8, (bytes, bytearray)) else None

            notify_uuids = getattr(client, "_classicNotifyCharUuids", None)
            if isinstance(notify_uuids, set):
                notify_uuids = sorted(str(u) for u in notify_uuids)

            # Get enhanced diagnostics from client if available
            client_diag = {}
            if client is not None and hasattr(client, "getClassicDiagnostics"):
                try:
                    client_diag = client.getClassicDiagnostics()
                except Exception as e:
                    client_diag = {"error": str(e)}

            diag = {
                "entry_id": casa_api.conf_entry.entry_id,
                "address": casa_api.address,
                "connected": getattr(casa, "connected", False),
                "cloud_protocolVersion": getattr(network, "protocolVersion", None),
                "protocolMode": protocol_mode_name,
                "classic_header_mode": getattr(client, "_classicHeaderMode", None),
                "classic_hash_source": getattr(client, "_classicHashSource", None),
                "classic_data_uuid": getattr(client, "_dataCharUuid", None),
                "classic_tx_uuid": getattr(client, "_classicTxCharUuid", None),
                "classic_notify_uuids": notify_uuids,
                "classic_conn_hash8_hex": conn_hash8_hex,
                "classic_visitorKey_present": bool(getattr(network, "classicVisitorKey", lambda: None)()),
                "classic_managerKey_present": bool(getattr(network, "classicManagerKey", lambda: None)()),
                "cloud_session_is_manager": bool(getattr(network, "isManager", lambda: False)()),
                "classic_rx_stats": {
                    "frames": getattr(client, "_classicRxFrames", None),
                    "verified": getattr(client, "_classicRxVerified", None),
                    "unverifiable": getattr(client, "_classicRxUnverifiable", None),
                    "parse_fail": getattr(client, "_classicRxParseFail", None),
                    "type6_unitstate": getattr(client, "_classicRxType6", None),
                    "type7_switch": getattr(client, "_classicRxType7", None),
                    "type9_netconf": getattr(client, "_classicRxType9", None),
                    "cmdstream": getattr(client, "_classicRxCmdStream", None),
                    "unknown": getattr(client, "_classicRxUnknown", None),
                },
                "classic_first_rx_ts": getattr(client, "_classicFirstRxTs", None),
                "units": len(units),
                "units_with_securityKey": units_with_security_key,
                "keyStore_present": bool(
                    (getattr(casa, "rawNetworkData", None) or {})
                    .get("network", {})
                    .get("keyStore")
                ),
            }

            # Include packet history if requested
            if include_packet_history:
                diag["classic_tx_history"] = client_diag.get("classic_tx_history", [])
                diag["classic_rx_history"] = client_diag.get("classic_rx_history", [])
                diag["classic_tx_count"] = client_diag.get("classic_tx_count", 0)
                diag["classic_rx_count"] = client_diag.get("classic_rx_count", 0)

            # Include full network config if requested
            if include_network_config:
                raw_network = casa.rawNetworkData
                if raw_network:
                    diag["network_config"] = raw_network

            _LOGGER.warning("[CASAMBI_CLASSIC_DIAGNOSTICS] %s", diag)
            return {"diagnostics": diag}

        hass.services.async_register(
            DOMAIN,
            "dump_classic_diagnostics",
            handle_dump_classic_diagnostics,
            supports_response="optional",
        )
        _LOGGER.info("Registered dump_classic_diagnostics service")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    casa_api: CasambiApi = hass.data[DOMAIN][entry.entry_id]
    await casa_api.disconnect()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


def get_cache_dir(hass: HomeAssistant) -> Path:
    """Return the cache dir that should be used by CasambiBt."""
    conf_path = Path(hass.config.config_dir)
    return conf_path / ".storage" / DOMAIN


class CasambiApi:
    """Defines a Casambi API."""

    def __init__(
        self,
        hass: HomeAssistant,
        conf_entry: ConfigEntry,
        address: str,
        password: str,
    ) -> None:
        """Initialize a Casambi API."""

        self.hass = hass
        self.conf_entry = conf_entry
        self.address = address
        self.password = password
        self.casa: Casambi = Casambi(get_async_client(hass), get_cache_dir(hass))

        self._callback_map: dict[int, list[Callable[[Unit], None]]] = {}
        self._switch_event_callbacks: list[Callable[[dict], None]] = []
        self._cancel_bluetooth_callback: Callable[[], None] | None = None
        self._reconnect_lock = asyncio.Lock()
        self._first_disconnect = True

    def _register_bluetooth_callback(self) -> None:
        self._cancel_bluetooth_callback = bluetooth.async_register_callback(
            self.hass,
            self._bluetooth_callback,
            {"address": self.address, "connectable": True},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

    async def connect(self) -> None:
        """Connect to the Casmabi network."""
        try:
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if not device:
                raise NetworkNotFoundError  # noqa: TRY301

            self.casa.registerDisconnectCallback(self._casa_disconnect)
            self.casa.registerUnitChangedHandler(self._unit_changed_handler)

            # Register switch event handler if available (new in casambi-bt 0.3.0)
            if hasattr(self.casa, 'registerSwitchEventHandler'):
                self.casa.registerSwitchEventHandler(self._switch_event_handler)
            else:
                _LOGGER.warning("Switch event handler not available in casambi-bt library. Please update to latest version.")

            await self.casa.connect(device, self.password)
            self._first_disconnect = True
            _LOGGER.info(
                "[CASAMBI_HA_NETWORK] address=%s protocolVersion=%s is_classic=%s",
                self.address,
                self.protocol_version,
                self.is_classic_network,
            )
        except BluetoothError as err:
            raise ConfigEntryNotReady("Failed to use bluetooth") from err
        except NetworkNotFoundError as err:
            raise ConfigEntryNotReady(
                f"Network with address {self.address} wasn't found"
            ) from err
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                f"Failed to authenticate to network {self.address}"
            ) from err
        except Exception as err:  # pylint: disable=broad-except
            raise ConfigEntryError(
                f"Unexpected error creating network {self.address}"
            ) from err

        # Only register bluetooth callback after connection.
        # Otherwise we get an immediate callback and attempt two connections at once.
        if not self._cancel_bluetooth_callback:
            self._register_bluetooth_callback()

    @property
    def available(self) -> bool:
        """Return True if the controller is available."""
        return self.casa.connected

    @property
    def protocol_version(self) -> int | None:
        """Return the cloud protocolVersion for the network if available."""
        raw = getattr(self.casa, "rawNetworkData", None) or {}
        pv = raw.get("network", {}).get("protocolVersion")
        return pv if isinstance(pv, int) else None

    @property
    def is_classic_network(self) -> bool:
        """Best-effort Classic detection for HA behavior.

        Classic networks should remain controllable even if unit online status is unknown.
        """
        pv = self.protocol_version
        return pv is not None and pv < 10

    def get_units(
        self, control_types: list[UnitControlType] | None = None
    ) -> Iterable[Unit]:
        """Return all units in the network optionally filtered by control type."""

        if not control_types:
            return self.casa.units

        return filter(
            lambda u: any(uc.type in control_types for uc in u.unitType.controls),  # type: ignore[arg-type]
            self.casa.units,
        )

    def get_groups(self) -> Iterable[Group]:
        """Return all groups in the network."""

        return self.casa.groups

    def get_scenes(self) -> Iterable[Scene]:
        """Return all scenes in the network."""

        return self.casa.scenes

    async def disconnect(self) -> None:
        """Disconnects from the controller and disables automatic reconnect."""
        async with self._reconnect_lock:
            if self._cancel_bluetooth_callback is not None:
                self._cancel_bluetooth_callback()
                self._cancel_bluetooth_callback = None

            # This needs to happen before we disconnect.
            # We don't want to be informed about disconnects initiated by us.
            self.casa.unregisterDisconnectCallback(self._casa_disconnect)

            try:
                await self.casa.disconnect()
            except Exception:
                _LOGGER.exception("Error during disconnect.")
            self.casa.unregisterUnitChangedHandler(self._unit_changed_handler)

            # Unregister switch event handler if available
            if hasattr(self.casa, 'unregisterSwitchEventHandler'):
                self.casa.unregisterSwitchEventHandler(self._switch_event_handler)

    @callback
    def _casa_disconnect(self) -> None:
        if self._first_disconnect:
            self._first_disconnect = False
            self.conf_entry.async_create_background_task(
                self.hass, self._delayed_reconnect(), "Delayed reconnect"
            )

    async def _delayed_reconnect(self) -> None:
        await asyncio.sleep(30)

        async with self._reconnect_lock:
            if self.casa.connected:
                return

        _LOGGER.debug("Starting delayed reconnect.")
        device = bluetooth.async_ble_device_from_address(self.hass, self.address)
        if device is not None:
            try:
                await self.try_reconnect()
            except Exception:
                _LOGGER.exception("Error during reconnect. This is not unusual.")
        else:
            _LOGGER.debug("Skipping reconnect. HA reports device not present.")

    async def try_reconnect(self) -> None:
        """Attemtps to reconnect to the Casambi network. Disconnects first to ensure a consitent state."""
        if self._reconnect_lock.locked():
            return

        # Use locking to ensure that only one reconnect can happen at a time.
        # Not sure if this is necessary.
        await self._reconnect_lock.acquire()

        try:
            try:
                await self.casa.disconnect()
            # HACK: This is a workaround for https://github.com/lkempf/casambi-bt-hass/issues/26
            # We don't actually need to disconnect except to clean up so this should be ok to ignore.
            except AttributeError:
                _LOGGER.debug("Unexpected failure during disconnect.")
            await self.connect()
        finally:
            self._reconnect_lock.release()

    def register_unit_updates(self, unit: Unit, c: Callable[[Unit], None]) -> None:
        """Register a callback for unit updates.

        :param unit: The unit for which changes should be reported.
        :param c: The callback.
        """
        self._callback_map.setdefault(unit.deviceId, []).append(c)

    def unregister_unit_updates(self, unit: Unit, c: Callable[[Unit], None]) -> None:
        """Unregister a callback for unit updates.

        :param unit: The unit for which changes should no longer be reported.
        :param c: The callback.
        """
        self._callback_map[unit.deviceId].remove(c)

    @callback
    def _unit_changed_handler(self, unit: Unit) -> None:
        if unit.deviceId not in self._callback_map:
            return
        for c in self._callback_map[unit.deviceId]:
            c(unit)

    @callback
    def _switch_event_handler(self, event_data: dict) -> None:
        """Handle switch events from the Casambi network."""
        _LOGGER.debug("Switch event received: %s", event_data)
        for cb in self._switch_event_callbacks:
            if asyncio.iscoroutinefunction(cb):
                self.conf_entry.async_create_task(
                    self.hass, cb(event_data), "switch_event_callback"
                )
            else:
                cb(event_data)

    def register_switch_event_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for switch events."""
        self._switch_event_callbacks.append(callback)
        _LOGGER.debug("Registered switch event callback: %s", callback)

    def unregister_switch_event_callback(self, callback: Callable[[dict], None]) -> None:
        """Unregister a callback for switch events."""
        if callback in self._switch_event_callbacks:
            self._switch_event_callbacks.remove(callback)
            _LOGGER.debug("Unregistered switch event callback: %s", callback)

    @callback
    def _bluetooth_callback(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        _change: bluetooth.BluetoothChange,
    ) -> None:
        if not self.casa.connected and service_info.connectable:
            self.conf_entry.async_create_background_task(
                self.hass, self.try_reconnect(), "Reconnect"
            )
