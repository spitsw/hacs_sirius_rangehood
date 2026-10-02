"""Tests for config_flow.py — URL validation and step logic."""

from __future__ import annotations

from custom_components.sirius_rangehood_custom import config_flow as cf
from custom_components.sirius_rangehood_custom.config_flow import _validate_urls


class TestValidateURLs:
    """Verify URL validation logic used in the config flow."""

    def test_valid_urls(self) -> None:
        """Should return None when both URLs are valid."""
        result = _validate_urls(
            "https://sirius.iotpga.it",
            "mqtts://sirius.iotpga.it:8884",
        )
        assert result is None

    def test_invalid_https_url(self) -> None:
        """Should return 'invalid_https_url' when HTTPS URL doesn't start with https://."""
        result = _validate_urls(
            "http://sirius.iotpga.it",
            "mqtts://sirius.iotpga.it:8884",
        )
        assert result == "invalid_https_url"

    def test_invalid_mqtts_url(self) -> None:
        """Should return 'invalid_mqtts_url' when MQTTS URL doesn't start with mqtts://."""
        result = _validate_urls(
            "https://sirius.iotpga.it",
            "mqtt://sirius.iotpga.it:8884",
        )
        assert result == "invalid_mqtts_url"

    def test_both_urls_invalid(self) -> None:
        """Should return the HTTPS error first."""
        result = _validate_urls(
            "ftp://bad.com",
            "tcp://bad.com",
        )
        assert result == "invalid_https_url"

    def test_empty_urls(self) -> None:
        """Should reject empty strings (no scheme)."""
        result = _validate_urls("", "")
        assert result == "invalid_https_url"


async def test_user_flow_creates_entry_with_defaults(hass, monkeypatch) -> None:
    """The user flow should discover devices, then create an entry."""

    async def _fake_discover(*_args, **_kwargs):
        return [{"id": 1, "uid": "u1", "name": "n", "description": "d"}]

    monkeypatch.setattr(cf, "_try_discover_devices", _fake_discover)

    result = await hass.config_entries.flow.async_init(
        cf.DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user", "password": "pass"}
    )
    assert result["type"] == "menu"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] == "create_entry"
    assert result["data"][cf.CONF_USERNAME] == "user"
    assert result["data"][cf.CONF_SIRIUS_ENDPOINT] == cf.DEFAULT_SIRIUS_ENDPOINT
    assert (
        result["data"][cf.CONF_SIRIUS_MQTTS_ENDPOINT]
        == cf.DEFAULT_SIRIUS_MQTTS_ENDPOINT
    )
