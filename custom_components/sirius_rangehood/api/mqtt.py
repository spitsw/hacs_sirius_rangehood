"""MQTTS client for receiving real-time status from Sirius devices."""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any, Callable
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]  # device_id, payload


def _create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that validates the certificate chain but ignores expiry.

    The Sirius MQTT server has a valid certificate that has expired; this
    context skips the expiry check while still validating everything else
    (chain of trust, hostname, etc.).
    """
    context = ssl.create_default_context()

    def _verify_callback(conn, cert, errno, depth, preverify_ok):  # noqa: ANN001
        # X509_V_ERR_CERT_HAS_EXPIRED = 10 — use raw value because this
        # constant may not be exposed by the ssl module on all platforms.
        if errno == 10:
            return True
        return preverify_ok

    context.verify_callback = _verify_callback
    return context


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
    ) -> None:
        self._username = username
        self._password = password
        self._status_callback = status_callback
        self._client: mqtt.Client | None = None
        self._subscribed_devices: set[str] = set()

        parsed = urlparse(mqtts_endpoint)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or self._DEFAULT_PORT

    def _on_connect(self, _client, _userdata, _flags, rc) -> None:  # noqa: ANN001
        """Handle connection events."""
        if rc == 0:
            _LOGGER.info("MQTT connected to %s", self._host)
            for device_id in self._subscribed_devices:
                self._subscribe_device(device_id)
        else:
            _LOGGER.error("MQTT connection failed (rc=%d)", rc)

    def _on_disconnect(self, _client, _userdata, rc) -> None:  # noqa: ANN001
        """Handle disconnection."""
        _LOGGER.warning("MQTT disconnected (rc=%d), reconnecting...", rc)

    def _on_message(self, _client, _userdata, msg) -> None:  # noqa: ANN001
        """Handle incoming MQTT messages."""
        topic = msg.topic
        try:
            raw = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            _LOGGER.warning("Invalid MQTT payload on %s: %s", topic, err)
            return

        payload = raw if isinstance(raw, dict) else {}
        values_list = payload.pop("values", [])
        device_id = payload.get("deviceId")
        if not device_id:
            _LOGGER.debug("MQTT message on %s missing deviceId", topic)
            return

        flat: dict[str, object] = {}
        for item in values_list:
            if isinstance(item, dict) and "id" in item:
                flat[item["id"]] = item["value"]

        _LOGGER.debug("MQTT status update for %s: %s", device_id, flat)
        if self._status_callback:
            self._status_callback(device_id, flat)

    async def async_start(self) -> bool:
        """Connect to the MQTTS broker. Returns True if connection initiated."""
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._client.tls_set_context(_create_ssl_context())
        self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        # Exponential backoff: 1 s → up to 120 s between reconnect attempts
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

        try:
            self._client.connect_async(self._host, self._port, keepalive=self._KEEPALIVE)
            self._client.loop_start()
            _LOGGER.debug("MQTT connection initiated to %s:%d", self._host, self._port)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("MQTT connection failed: %s", err)
            return False

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
        """Subscribe to MQTT topics for a device."""
        status_topic = f"root/codermine/devices/{device_id}/status"
        response_topic = f"root/codermine/devices/{device_id}/response/#"
        if self._client:
            self._client.subscribe(status_topic, qos=1)
            self._client.subscribe(response_topic, qos=1)
            _LOGGER.debug("Subscribed to MQTT topics for %s", device_id)