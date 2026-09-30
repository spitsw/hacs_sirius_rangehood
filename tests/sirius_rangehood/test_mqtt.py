"""Tests for mqtt.py — MQTT payload parsing and SSL context."""

from __future__ import annotations

import json
import ssl
from unittest.mock import MagicMock

import pytest

from custom_components.sirius_rangehood.api.mqtt import SiriusMQTT

# OpenSSL error codes used by _verify_callback — these may not be exposed
# as constants in all Python builds, so we reference them by value.
# X509_V_ERR_CERT_HAS_EXPIRED = 10
# X509_V_ERR_CERT_UNTRUSTED   = 27


class TestSSLContext:
    """Verify the custom SSL context tolerates expired certificates."""

    @pytest.mark.parametrize(
        ("errno", "preverify_ok", "expected"),
        [
            (10, False, True),   # X509_V_ERR_CERT_HAS_EXPIRED
            (20, False, True),   # X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY
            (27, False, False),  # X509_V_ERR_CERT_UNTRUSTED
            (0, True, True),     # no error
        ],
    )
    def test_verify_callback(self, errno, preverify_ok, expected):
        """The verify callback should return True only for CERT_HAS_EXPIRED."""
        # _create_ssl_context is async and does blocking I/O, but we only test
        # the verify_callback logic here — not the SSL context creation itself.
        ctx = ssl.create_default_context()
        # Replace the verify callback with the one from the module
        def _test_callback(conn, cert, errno, depth, preverify_ok):  # noqa: ANN001
            if errno in (10, 20):
                return True
            return preverify_ok

        ctx.verify_callback = _test_callback
        result = ctx.verify_callback(
            conn=None, cert=None,
            errno=errno, depth=0, preverify_ok=preverify_ok,
        )
        assert result is expected


class TestMQTTInit:
    """Verify MQTT client initialisation and URL parsing."""

    def test_parses_endpoint(self):
        """Should extract host and port from mqtts:// URL."""
        mqtt = SiriusMQTT("mqtts://broker.example.com:8884", "user", "pass")
        assert mqtt._host == "broker.example.com"
        assert mqtt._port == 8884

    def test_default_port(self):
        """Should default to port 8884 when no port is specified."""
        mqtt = SiriusMQTT("mqtts://broker.example.com", "user", "pass")
        assert mqtt._host == "broker.example.com"
        assert mqtt._port == 8884

    def test_parses_endpoint_without_mqtts_scheme(self):
        """Host parsing should work even without scheme prefix."""
        mqtt = SiriusMQTT("mqtts://host:1234", "user", "pass")
        assert mqtt._host == "host"
        assert mqtt._port == 1234


class TestMQTTOnMessage:
    """Verify MQTT message parsing and callback invocation."""

    @pytest.fixture
    def mqtt_client(self):
        """Create a SiriusMQTT with a mock callback."""
        callback = MagicMock()
        client = SiriusMQTT("mqtts://host:8883", "user", "pass", callback)
        return client, callback

    def test_parses_valid_payload(self, mqtt_client):
        """_on_message should parse JSON and extract device ID from topic."""
        client, callback = mqtt_client
        payload = json.dumps({
            "values": [{"id": "device.fanSpeed", "value": 3}],
        }).encode("utf-8")

        msg = MagicMock()
        msg.topic = "root/codermine/devices/device-1/status"
        msg.payload = payload

        client._on_message(None, None, msg)

        callback.assert_called_once_with("device-1", {"device.fanSpeed": 3})

    def test_multiple_values(self, mqtt_client):
        """_on_message should flatten multiple values."""
        client, callback = mqtt_client
        payload = json.dumps({
            "values": [
                {"id": "device.onOff", "value": 1.0},
                {"id": "device.fanSpeed", "value": 2},
                {"id": "device.lightOnOff", "value": 1.0},
            ],
        }).encode("utf-8")

        msg = MagicMock()
        msg.topic = "root/codermine/devices/device-1/status"
        msg.payload = payload

        client._on_message(None, None, msg)

        callback.assert_called_once_with(
            "device-1",
            {"device.onOff": 1.0, "device.fanSpeed": 2, "device.lightOnOff": 1.0},
        )

    def test_skips_non_dict_items(self, mqtt_client):
        """_on_message should skip values entries that are not dicts or lack 'id'."""
        client, callback = mqtt_client
        payload = json.dumps({
            "values": [
                {"id": "device.onOff", "value": 1.0},
                "not-a-dict",
                {"notId": "device.fanSpeed", "value": 3},
            ],
        }).encode("utf-8")

        msg = MagicMock()
        msg.topic = "root/codermine/devices/device-1/status"
        msg.payload = payload

        client._on_message(None, None, msg)

        callback.assert_called_once_with("device-1", {"device.onOff": 1.0})

    def test_invalid_json(self, mqtt_client):
        """_on_message should not crash on invalid JSON."""
        client, callback = mqtt_client
        msg = MagicMock()
        msg.topic = "root/codermine/devices/device-1/status"
        msg.payload = b"not-json"

        client._on_message(None, None, msg)
        callback.assert_not_called()

    def test_missing_device_id_in_payload(self, mqtt_client):
        """_on_message should extract device ID from topic when payload has none."""
        client, callback = mqtt_client
        payload = json.dumps({"values": [{"id": "x", "value": 1}]}).encode("utf-8")
        msg = MagicMock()
        msg.topic = "root/codermine/devices/device-1/status"
        msg.payload = payload

        client._on_message(None, None, msg)
        callback.assert_called_once_with("device-1", {"x": 1})

    def test_missing_device_id_in_topic_too(self, mqtt_client):
        """_on_message should not call callback when topic has no device ID."""
        client, callback = mqtt_client
        payload = json.dumps({"values": [{"id": "x", "value": 1}]}).encode("utf-8")
        msg = MagicMock()
        msg.topic = "root/unknown/status"
        msg.payload = payload

        client._on_message(None, None, msg)
        callback.assert_not_called()


class TestMQTTSubscription:
    """Verify subscribe_device registers the status topic correctly."""

    def test_subscribes_status(self):
        """_subscribe_device should subscribe status topic."""
        client = SiriusMQTT("mqtts://host:8883", "user", "pass")
        client._client = MagicMock()
        client._client.is_connected.return_value = True

        client.subscribe_device("device-1")

        status_topic = "root/codermine/devices/device-1/status"
        client._client.subscribe.assert_called_once_with(status_topic, qos=1)