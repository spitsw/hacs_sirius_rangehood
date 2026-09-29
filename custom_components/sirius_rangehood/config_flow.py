"""Config flow for Sirius Rangehood."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_INSECURE_TLS,
    CONF_SIRIUS_ENDPOINT,
    CONF_SIRIUS_MQTTS_ENDPOINT,
    DOMAIN,
)
from .api import (
    DEFAULT_SIRIUS_ENDPOINT,
    DEFAULT_SIRIUS_MQTTS_ENDPOINT,
)
from .api import SiriusHub, SiriusAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SIRIUS_ENDPOINT, default=DEFAULT_SIRIUS_ENDPOINT): str,
        vol.Required(CONF_SIRIUS_MQTTS_ENDPOINT, default=DEFAULT_SIRIUS_MQTTS_ENDPOINT): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_INSECURE_TLS, default=False): bool,
    }
)


def _validate_urls(sirius_endpoint: str, mqtts_endpoint: str) -> str | None:
    """Return an error key if URL schemes are invalid, else None."""
    if not sirius_endpoint.startswith("https://"):
        return "invalid_https_url"
    if not mqtts_endpoint.startswith("mqtts://"):
        return "invalid_mqtts_url"
    return None


async def _try_discover_devices(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    errors: dict[str, str],
) -> list[dict[str, Any]] | None:
    """Validate credentials and discover Sirius devices.

    Populates *errors* on failure; returns the device list on success or
    *None* when errors were set (caller should re-show the form).
    """
    session = async_get_clientsession(hass)
    insecure = user_input.get(CONF_INSECURE_TLS, False)
    hub = SiriusHub(
        session,
        user_input[CONF_SIRIUS_ENDPOINT],
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
        insecure_tls=insecure,
    )
    try:
        devices = await hub.async_discover_devices(retry=False)
        if not devices:
            _LOGGER.warning("Sirius login succeeded but no devices found")
            errors["base"] = "no_devices"
            return None
        _LOGGER.info(
            "Sirius authenticated, %d device(s) discovered", len(devices)
        )
        return devices
    except SiriusAuthError:
        errors["base"] = "invalid_auth"
        return None
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error during config flow")
        errors["base"] = "cannot_connect"
        return None


class SiriusRangehoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sirius Rangehood."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url_error = _validate_urls(
                user_input[CONF_SIRIUS_ENDPOINT],
                user_input[CONF_SIRIUS_MQTTS_ENDPOINT],
            )
            if url_error:
                errors["base"] = url_error
            else:
                self._async_abort_entries_match(
                    {CONF_SIRIUS_ENDPOINT: user_input[CONF_SIRIUS_ENDPOINT]}
                )
                devices = await _try_discover_devices(
                    self.hass, user_input, errors
                )
                if devices is not None:
                    return self.async_create_entry(
                        title=(
                            f"Sirius Rangehood ({len(devices)} device"
                            f"{'s' if len(devices) > 1 else ''})"
                        ),
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Re-authenticate with new credentials after a token rejection."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            url_error = _validate_urls(
                user_input[CONF_SIRIUS_ENDPOINT],
                user_input[CONF_SIRIUS_MQTTS_ENDPOINT],
            )
            if url_error:
                errors["base"] = url_error
            else:
                devices = await _try_discover_devices(
                    self.hass, user_input, errors
                )
                if devices is not None:
                    _LOGGER.info("Sirius reauth succeeded, %d device(s)", len(devices))
                    return self.async_update_reload_and_abort(
                        entry,
                        data={
                            **entry.data,
                            CONF_SIRIUS_ENDPOINT: user_input[CONF_SIRIUS_ENDPOINT],
                            CONF_SIRIUS_MQTTS_ENDPOINT: user_input[CONF_SIRIUS_MQTTS_ENDPOINT],
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_INSECURE_TLS: user_input.get(CONF_INSECURE_TLS, False),
                        },
                    )
        else:
            user_input = {
                CONF_SIRIUS_ENDPOINT: entry.data.get(CONF_SIRIUS_ENDPOINT, DEFAULT_SIRIUS_ENDPOINT),
                CONF_SIRIUS_MQTTS_ENDPOINT: entry.data.get(CONF_SIRIUS_MQTTS_ENDPOINT, DEFAULT_SIRIUS_MQTTS_ENDPOINT),
                CONF_USERNAME: entry.data.get(CONF_USERNAME, ""),
                CONF_PASSWORD: "",
            }

        schema = vol.Schema(
            {
                vol.Required(CONF_SIRIUS_ENDPOINT, default=user_input[CONF_SIRIUS_ENDPOINT]): str,
                vol.Required(CONF_SIRIUS_MQTTS_ENDPOINT, default=user_input[CONF_SIRIUS_MQTTS_ENDPOINT]): str,
                vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_INSECURE_TLS, default=entry.data.get(CONF_INSECURE_TLS, False)): bool,
            }
        )
        return self.async_show_form(
            step_id="reauth",
            data_schema=schema,
            errors=errors,
            description_placeholders={"endpoint": user_input[CONF_SIRIUS_ENDPOINT]},
        )