"""Tests for const.py — percentage/speed mapping and constants."""

from __future__ import annotations

from custom_components.sirius_rangehood.const import (
    CAP_FAN_SPEED,
    DEFAULT_SIRIUS_ENDPOINT,
    DEFAULT_SIRIUS_MQTTS_ENDPOINT,
    DOMAIN,
    FAN_SPEED_BOOST,
    FAN_SPEED_HIGH,
    FAN_SPEED_LOW,
    FAN_SPEED_MEDIUM,
    FAN_SPEED_OFF,
    PERCENTAGE_TO_SPEED,
    SPEED_TO_PERCENTAGE,
)


def _nearest_speed(percentage: int) -> int:
    """Replicate the nearest-match logic from fan.py:async_set_percentage."""
    return min(PERCENTAGE_TO_SPEED.items(), key=lambda x: abs(x[0] - percentage))[1]


class TestFanSpeedMapping:
    """Verify speed ↔ percentage mapping is correct and bijective."""

    def test_speed_to_percentage(self):
        """Verify each speed maps to the expected percentage."""
        assert SPEED_TO_PERCENTAGE[FAN_SPEED_OFF] == 0
        assert SPEED_TO_PERCENTAGE[FAN_SPEED_LOW] == 25
        assert SPEED_TO_PERCENTAGE[FAN_SPEED_MEDIUM] == 50
        assert SPEED_TO_PERCENTAGE[FAN_SPEED_HIGH] == 75
        assert SPEED_TO_PERCENTAGE[FAN_SPEED_BOOST] == 100

    def test_percentage_to_speed(self):
        """Verify each percentage maps back to the expected speed."""
        assert PERCENTAGE_TO_SPEED[0] == FAN_SPEED_OFF
        assert PERCENTAGE_TO_SPEED[25] == FAN_SPEED_LOW
        assert PERCENTAGE_TO_SPEED[50] == FAN_SPEED_MEDIUM
        assert PERCENTAGE_TO_SPEED[75] == FAN_SPEED_HIGH
        assert PERCENTAGE_TO_SPEED[100] == FAN_SPEED_BOOST

    def test_bijection(self):
        """Verify speed→percentage→speed round-trips cleanly for all speeds."""
        for speed in (FAN_SPEED_OFF, FAN_SPEED_LOW, FAN_SPEED_MEDIUM, FAN_SPEED_HIGH, FAN_SPEED_BOOST):
            pct = SPEED_TO_PERCENTAGE[speed]
            assert PERCENTAGE_TO_SPEED[pct] == speed

    def test_nearest_match_low(self):
        """Verify percentage 10 maps to FAN_SPEED_OFF (closer to 0 than 25)."""
        speed = _nearest_speed(10)
        assert speed == FAN_SPEED_OFF

    def test_nearest_match_high(self):
        """Verify percentage 90 maps to FAN_SPEED_BOOST (nearest to 100%)."""
        speed = _nearest_speed(90)
        assert speed == FAN_SPEED_BOOST

    def test_nearest_match_low_boundary(self):
        """Verify percentage 12 still maps to FAN_SPEED_OFF (closer to 0)."""
        speed = _nearest_speed(12)
        assert speed == FAN_SPEED_OFF

    def test_nearest_match_medium(self):
        """Verify percentage 62 maps to FAN_SPEED_MEDIUM (nearest to 50)."""
        speed = _nearest_speed(62)
        assert speed == FAN_SPEED_MEDIUM


class TestConstants:
    """Verify important constants are present and well-formed."""

    def test_domain(self):
        assert DOMAIN == "sirius_rangehood"

    def test_cap_fan_speed(self):
        assert CAP_FAN_SPEED == "device.fanSpeed"

    def test_default_endpoints(self):
        assert DEFAULT_SIRIUS_ENDPOINT == "https://sirius.iotpga.it"
        assert DEFAULT_SIRIUS_MQTTS_ENDPOINT == "mqtts://sirius.iotpga.it:8884"