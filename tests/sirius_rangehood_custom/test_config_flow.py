"""Tests for config_flow.py — URL validation and step logic."""

from __future__ import annotations

from custom_components.sirius_rangehood_custom.config_flow import _validate_urls


class TestValidateURLs:
    """Verify URL validation logic used in the config flow."""

    def test_valid_urls(self):
        """Should return None when both URLs are valid."""
        result = _validate_urls(
            "https://sirius.iotpga.it",
            "mqtts://sirius.iotpga.it:8884",
        )
        assert result is None

    def test_invalid_https_url(self):
        """Should return 'invalid_https_url' when HTTPS URL doesn't start with https://."""
        result = _validate_urls(
            "http://sirius.iotpga.it",
            "mqtts://sirius.iotpga.it:8884",
        )
        assert result == "invalid_https_url"

    def test_invalid_mqtts_url(self):
        """Should return 'invalid_mqtts_url' when MQTTS URL doesn't start with mqtts://."""
        result = _validate_urls(
            "https://sirius.iotpga.it",
            "mqtt://sirius.iotpga.it:8884",
        )
        assert result == "invalid_mqtts_url"

    def test_both_urls_invalid(self):
        """Should return the HTTPS error first."""
        result = _validate_urls(
            "ftp://bad.com",
            "tcp://bad.com",
        )
        assert result == "invalid_https_url"

    def test_empty_urls(self):
        """Should reject empty strings (no scheme)."""
        result = _validate_urls("", "")
        assert result == "invalid_https_url"
