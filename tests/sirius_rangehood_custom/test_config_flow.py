"""Tests for config_flow.py — URL validation and step logic."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sirius_rangehood_custom import config_flow as cf
from custom_components.sirius_rangehood_custom.config_flow import _validate_urls
from custom_components.sirius_rangehood_custom.const import (
    CONF_INSECURE_TLS,
    CONF_SIRIUS_ENDPOINT,
    CONF_SIRIUS_MQTTS_ENDPOINT,
    DOMAIN,
)


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
    """The user flow should offer a menu, log in, then create an entry."""

    async def _fake_discover(*_args, **_kwargs):
        return [{"id": 1, "uid": "u1", "name": "n", "description": "d"}]

    monkeypatch.setattr(cf, "_try_discover_devices", _fake_discover)

    result = await hass.config_entries.flow.async_init(
        cf.DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"credentials", "endpoints"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "credentials"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "user", "password": "pass"}
    )
    assert result["type"] == "create_entry"
    assert result["data"][cf.CONF_USERNAME] == "user"
    assert result["data"][cf.CONF_SIRIUS_ENDPOINT] == cf.DEFAULT_SIRIUS_ENDPOINT
    assert (
        result["data"][cf.CONF_SIRIUS_MQTTS_ENDPOINT]
        == cf.DEFAULT_SIRIUS_MQTTS_ENDPOINT
    )


async def test_reconfigure_reaches_endpoints_without_login(hass) -> None:
    """Endpoint editing must be reachable even when the stored URL is broken."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SIRIUS_ENDPOINT: "https://broken.example.com",
            CONF_SIRIUS_MQTTS_ENDPOINT: "mqtts://broken.example.com:8884",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            CONF_INSECURE_TLS: False,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] == "menu"
    assert "endpoints" in result["menu_options"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "endpoints"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "endpoints"
