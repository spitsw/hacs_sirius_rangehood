"""MQTTS client for receiving real-time status from Sirius devices."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Callable
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]  # device_id, payload


async def _create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that tolerates known certificate issues.

    The Sirius MQTT server presents a valid DigiCert-signed certificate
    that has expired. Some HA Docker images may also lack the DigiCert
    root CA. The context uses ``CERT_OPTIONAL`` so the TLS handshake
    completes even when the certificate chain can't be fully verified.

    ``ssl.create_default_context()`` calls ``load_default_certs()`` which
    reads system certificate files from disk — blocking I/O that must not
    run on the event loop.
    """
    context = await asyncio.get_event_loop().run_in_executor(
        None, ssl.create_default_context
    )
    # Don't abort the handshake on certificate validation errors —
    # the cert is known to be valid but expired, and the issuer root
    # may not be in the container's trust store.
    context.verify_mode = ssl.CERT_OPTIONAL
    context.check_hostname = False


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
        insecure_tls: bool = False,
    ) -> None:
        self._username = username
        self._password = password
        self._status_callback = status_callback
        self._insecure_tls = insecure_tls
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

        # device ID is always in the topic path:
        #   .../devices/{device_id}/status
        parts = topic.split("/")
        try:
            device_id = parts[parts.index("devices") + 1]
        except (ValueError, IndexError):
            _LOGGER.debug("MQTT message on %s: could not extract device ID from topic", topic)
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
        if self._insecure_tls:
            _LOGGER.warning("MQTT TLS verification disabled for %s:%d", self._host, self._port)
            ctx = await asyncio.get_event_loop().run_in_executor(
                None, ssl.create_default_context
            )
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._client.tls_set_context(ctx)
        else:
            self._client.tls_set_context(await _create_ssl_context())
            _LOGGER.debug("MQTT TLS enabled (expired-cert tolerant) for %s:%d", self._host, self._port)
        self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

        try:
            # Connect synchronously in a thread executor to avoid event-loop blocking
            # and paho async threading issues. loop_start() is called afterwards.
            def _connect() -> None:
                self._client.connect(self._host, self._port, keepalive=self._KEEPALIVE)

            _LOGGER.debug("Connecting to MQTT broker %s:%d (insecure=%s)...",
                           self._host, self._port, self._insecure_tls)
            await asyncio.get_event_loop().run_in_executor(None, _connect)
            self._client.loop_start()
            # Synchronous connect() already handled CONNACK, so _on_connect won't
            # fire again. Subscribe upfront.
            for device_id in self._subscribed_devices:
                self._subscribe_device(device_id)
            _LOGGER.info("MQTT connected to %s:%d", self._host, self._port)
            return True
        except (OSError, ConnectionError) as err:
            _LOGGER.error("MQTT connection to %s:%d failed: %s", self._host, self._port, err)
            return False
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("MQTT connection to %s:%d failed: %s", self._host, self._port, err)
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
        """Subscribe to MQTT status topic for a device."""
        status_topic = f"root/codermine/devices/{device_id}/status"
        if self._client:
            self._client.subscribe(status_topic, qos=1)
            _LOGGER.debug("Subscribed to MQTT status for %s", device_id)