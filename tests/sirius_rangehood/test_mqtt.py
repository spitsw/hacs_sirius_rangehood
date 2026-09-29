"""Tests for mqtt.py — MQTT payload parsing and SSL context."""

from __future__ import annotations

import json
import ssl
from unittest.mock import MagicMock

import pytest

from custom_components.sirius_rangehood.api.mqtt import (
    SiriusMQTT,
    _create_ssl_context,
)

# OpenSSL error codes used by _verify_callback — these may not be exposed
# as constants in all Python builds, so we reference them by value.
# X509_V_ERR_CERT_HAS_EXPIRED = 10
# X509_V_ERR_CERT_UNTRUSTED   = 27


class TestSSLContext:
    """Verify the custom SSL context tolerates expired certificates."""

    def test_create_ssl_context_returns_context(self):
        """Should return a functioning SSLContext."""
        ctx = _create_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_callback is not None

    def test_verify_callback_accepts_expired(self):
        """The verify callback should return True for CERT_HAS_EXPIRED."""
        ctx = _create_ssl_context()
        result = ctx.verify_callback(
            conn=None,
            cert=None,
            errno=10,  # X509_V_ERR_CERT_HAS_EXPIRED
            depth=0,
            preverify_ok=False,
        )
        assert result is True

    def test_verify_callback_forwards_other_errors(self):
        """For non-expiry errors, the callback should return preverify_ok."""
        ctx = _create_ssl_context()
        result = ctx.verify_callback(
            conn=None,
            cert=None,
            errno=27,  # X509_V_ERR_CERT_UNTRUSTED
            depth=0,
            preverify_ok=False,
        )
        assert result is False


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
        """_on_message should parse JSON and extract deviceId + values."""
        client, callback = mqtt_client
        payload = json.dumps({
            "deviceId": "device-1",
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
            "deviceId": "device-1",
            "values": [
                {"id": "device.onOff", "value": 1.0},
                {"id": "device.fanSpeed", "value": 2},
                {"id": "device.lightOnOff", "value": 1.0},
            ],
        }).encode("utf-8")

        msg = MagicMock()
        msg.topic = "topic"
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
            "deviceId": "device-1",
            "values": [
                {"id": "device.onOff", "value": 1.0},
                "not-a-dict",
                {"notId": "device.fanSpeed", "value": 3},
            ],
        }).encode("utf-8")

        msg = MagicMock()
        msg.topic = "topic"
        msg.payload = payload

        client._on_message(None, None, msg)

        callback.assert_called_once_with("device-1", {"device.onOff": 1.0})

    def test_invalid_json(self, mqtt_client):
        """_on_message should not crash on invalid JSON."""
        client, callback = mqtt_client
        msg = MagicMock()
        msg.topic = "topic"
        msg.payload = b"not-json"

        client._on_message(None, None, msg)
        callback.assert_not_called()

    def test_missing_device_id(self, mqtt_client):
        """_on_message should not call callback when deviceId is missing."""
        client, callback = mqtt_client
        payload = json.dumps({"values": [{"id": "x", "value": 1}]}).encode("utf-8")
        msg = MagicMock()
        msg.topic = "topic"
        msg.payload = payload

        client._on_message(None, None, msg)
        callback.assert_not_called()


class TestMQTTSubscription:
    """Verify subscribe_device registers topics correctly."""

    def test_subscribes_status_and_response(self):
        """_subscribe_device should subscribe status and response topics."""
        client = SiriusMQTT("mqtts://host:8883", "user", "pass")
        client._client = MagicMock()
        client._client.is_connected.return_value = True

        client.subscribe_device("device-1")

        status_topic = "root/codermine/devices/device-1/status"
        response_topic = "root/codermine/devices/device-1/response/#"
        client._client.subscribe.assert_any_call(status_topic, qos=1)
        client._client.subscribe.assert_any_call(response_topic, qos=1)