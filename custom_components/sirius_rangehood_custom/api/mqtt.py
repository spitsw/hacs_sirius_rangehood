# Copyright (c) 2026 Warren Spits
"""MQTTS client for receiving real-time status from Sirius devices."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]  # device_id, payload

_TOPIC_ERRORS = (ValueError, IndexError)
_JSON_ERRORS = (json.JSONDecodeError, UnicodeDecodeError)


class SiriusMQTT:
    """Manages a MQTTS connection to the Sirius server."""

    _DEFAULT_PORT = 8884
    _KEEPALIVE = 60

    def __init__(
        self,
        mqtts_endpoint: str,
        username: str,
        password: str,
        status_callback: StatusCallback | None = None,
        *,
        insecure_tls: bool = False,
    ) -> None:
        """Parse the broker endpoint and store connection details."""
        self._username = username
        self._password = password
        self._status_callback = status_callback
        self._insecure_tls = insecure_tls
        self._client: mqtt.Client | None = None
        self._subscribed_devices: set[str] = set()

        parsed = urlparse(mqtts_endpoint)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or self._DEFAULT_PORT

    @property
    def connected(self) -> bool:
        """Return True when the client is connected to the broker."""
        return bool(self._client and self._client.is_connected())

    @property
    def host(self) -> str:
        """Return the broker host."""
        return self._host

    def _on_connect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        rc: int,
    ) -> None:
        """Handle connection events."""
        if rc == 0:
            _LOGGER.info("MQTT connected to %s", self._host)
            for device_id in self._subscribed_devices:
                self._subscribe_device(device_id)
        else:
            _LOGGER.error("MQTT connection failed (rc=%d)", rc)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        rc: int,
    ) -> None:
        """Handle disconnection."""
        _LOGGER.warning("MQTT disconnected (rc=%d), reconnecting...", rc)

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming MQTT messages."""
        topic = msg.topic
        try:
            raw = json.loads(msg.payload.decode("utf-8"))
        except _JSON_ERRORS as err:
            _LOGGER.warning("Invalid MQTT payload on %s: %s", topic, err)
            return

        payload = raw if isinstance(raw, dict) else {}
        values_list = payload.pop("values", [])

        # The device ID is always the path segment after "devices" in the
        # topic (root/codermine/devices/{device_id}/status).
        parts = topic.split("/")
        try:
            device_id = parts[parts.index("devices") + 1]
        except _TOPIC_ERRORS:
            _LOGGER.debug(
                "MQTT message on %s: could not extract device ID from topic", topic
            )
            return

        flat: dict[str, object] = {}
        for item in values_list:
            if isinstance(item, dict) and "id" in item:
                flat[item["id"]] = item["value"]

        _LOGGER.debug("MQTT status update for %s: %s", device_id, flat)
        if self._status_callback:
            self._status_callback(device_id, flat)

    async def async_start(self) -> bool:
        """Connect to the MQTTS broker. Returns True if connection established."""
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

        try:
            # Build TLS context and connect: all blocking I/O, run in executor
            def _connect() -> None:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                self._client.tls_set_context(ctx)
                self._client.connect(self._host, self._port, keepalive=self._KEEPALIVE)

            _LOGGER.debug(
                "Connecting to MQTT broker %s:%d (insecure=%s)...",
                self._host,
                self._port,
                self._insecure_tls,
            )
            await asyncio.get_running_loop().run_in_executor(None, _connect)
            self._client.loop_start()
            # Synchronous connect() already handled CONNACK, so _on_connect won't
            # fire again. Subscribe upfront.
            for device_id in self._subscribed_devices:
                self._subscribe_device(device_id)
        except OSError:
            _LOGGER.exception("MQTT connection to %s:%d failed", self._host, self._port)
            return False
        except Exception:
            _LOGGER.exception("MQTT connection to %s:%d failed", self._host, self._port)
            return False
        else:
            _LOGGER.info("MQTT connected to %s:%d", self._host, self._port)
            return True

    async def async_stop(self) -> None:
        """Disconnect the MQTT client."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            _LOGGER.debug("MQTT disconnected")

    def subscribe_device(self, device_id: str) -> None:
        """Subscribe to status topics for a device."""
        self._subscribed_devices.add(device_id)
        if self._client and self._client.is_connected():
            self._subscribe_device(device_id)

    def _subscribe_device(self, device_id: str) -> None:
        """Subscribe to MQTT status topic for a device."""
        status_topic = f"root/codermine/devices/{device_id}/status"
        if self._client:
            self._client.subscribe(status_topic, qos=1)
            _LOGGER.debug("Subscribed to MQTT status for %s", device_id)
