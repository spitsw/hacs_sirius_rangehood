"""Tests for hub.py — HTTP API client and device flattening."""

from __future__ import annotations

import pytest

from custom_components.sirius_rangehood_custom.api.hub import SiriusAuthError, SiriusHub


class TestFlattenDevice:
    """Verify _flatten_device processes API responses correctly."""

    def test_flatten_basic(self):
        """Should flatten properties and capabilities into one dict."""
        raw = {
            "id": 1,
            "uid": "uid-1",
            "description": "My Rangehood",
            "properties": [
                {"id": "property.device.fw.version", "value": "1.2.3"},
                {"id": "property.device.network.rssi", "value": -70},
            ],
            "capabilities": [
                {
                    "capabilityUid": "device.fanSpeed",
                    "value": 3,
                    "minValue": 0,
                    "maxValue": 4,
                },
            ],
        }
        hub = SiriusHub.__new__(SiriusHub)
        flat = hub._flatten_device(raw)

        assert flat["id"] == 1
        assert flat["uid"] == "uid-1"
        assert flat["name"] == "My Rangehood"
        assert flat["property.device.fw.version"] == "1.2.3"
        assert flat["property.device.network.rssi"] == -70
        # Capability value is NOT stored in the flat dict — live state
        # comes from MQTT. Only _limits captures min/max bounds.
        assert "device.fanSpeed" not in flat
        assert "_limits" in flat
        assert flat["_limits"]["device.fanSpeed"] == {"min": 0.0, "max": 4.0}

    def test_flatten_uses_device_name_property(self):
        """Should use property.device_name as display name if present."""
        raw = {
            "id": 2,
            "uid": "uid-2",
            "description": "Fallback Name",
            "properties": [
                {"id": "property.device_name", "value": "Kitchen Rangehood"},
            ],
            "capabilities": [],
        }
        hub = SiriusHub.__new__(SiriusHub)
        flat = hub._flatten_device(raw)
        assert flat["name"] == "Kitchen Rangehood"

    def test_flatten_no_properties(self):
        """Should handle devices with no properties or capabilities."""
        raw = {
            "id": 3,
            "uid": "uid-3",
            "description": "Bare Device",
            "properties": [],
            "capabilities": [],
        }
        hub = SiriusHub.__new__(SiriusHub)
        flat = hub._flatten_device(raw)
        assert flat["id"] == 3
        assert flat["uid"] == "uid-3"

    def test_flatten_missing_optional_fields(self):
        """Should handle missing uid gracefully."""
        raw = {
            "id": 4,
            "description": "No UID",
            "properties": [],
            "capabilities": [],
        }
        hub = SiriusHub.__new__(SiriusHub)
        flat = hub._flatten_device(raw)
        assert flat["id"] == 4
        assert flat["uid"] == ""


class TestSiriusAuthError:
    """Verify SiriusAuthError is raiseable and catchable."""

    def test_is_exception(self):
        assert issubclass(SiriusAuthError, Exception)

    def test_can_be_raised_and_caught(self):
        try:
            raise SiriusAuthError("test")
        except SiriusAuthError:
            assert True
        except Exception:
            pytest.fail("SiriusAuthError should be caught by except SiriusAuthError")