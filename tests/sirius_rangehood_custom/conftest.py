"""Test fixtures for Sirius Rangehood tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_device_data():
    """Return a sample flattened device dict as returned by _flatten_device."""
    return {
        "id": 42,
        "uid": "sirius-abc-123",
        "name": "Test Rangehood",
        "description": "Sirius Smart Rangehood",
        "property.device_name": "Test Rangehood",
        "property.device.ref": "REF-001",
        "property.device.type": "rangehood",
        "property.device_class": "class_a",
        "property.device.fw.code": "FW-2.0",
        "property.device.fw.version": "2.1.0",
        "property.device.secureId": "sec-123",
        "property.device.network.rssi": -65,
        "property.device.network.ssid": "MyWiFi",
        "property.device.network.address": "192.168.1.100",
        "device.onOff": 1.0,
        "device.fanSpeed": 3,
        "device.boostValue": 5,
        "device.lightOnOff": 0.0,
        "device.lightBrightness": 80.0,
        "device.lightColorTemperature": 3500,
        "_limits": {},
    }


@pytest.fixture
def mock_mqtt_payload():
    """Return a sample MQTT status message payload."""
    return {
        "deviceId": "sirius-abc-123",
        "values": [
            {"id": "device.onOff", "value": 1.0},
            {"id": "device.fanSpeed", "value": 4},
            {"id": "device.lightOnOff", "value": 1.0},
            {"id": "device.lightBrightness", "value": 100.0},
            {"id": "device.lightColorTemperature", "value": 4000},
        ],
    }


@pytest.fixture
def mock_hub():
    """Return a mock SiriusHub."""
    hub = MagicMock()
    hub.async_ensure_token = AsyncMock(return_value="fake-jwt-token")
    hub.async_discover_devices = AsyncMock(return_value=[])
    hub.async_send_command = AsyncMock(return_value=True)
    hub.async_get_status = AsyncMock(return_value=True)
    return hub
