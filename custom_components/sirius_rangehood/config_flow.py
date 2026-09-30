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
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_ENDPOINTS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SIRIUS_ENDPOINT, default=DEFAULT_SIRIUS_ENDPOINT): str,
        vol.Required(CONF_SIRIUS_MQTTS_ENDPOINT, default=DEFAULT_SIRIUS_MQTTS_ENDPOINT): str,
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
    sirius_endpoint: str = DEFAULT_SIRIUS_ENDPOINT,
    mqtts_endpoint: str = DEFAULT_SIRIUS_MQTTS_ENDPOINT,
) -> list[dict[str, Any]] | None:
    """Validate credentials and discover Sirius devices."""
    session = async_get_clientsession(hass)
    hub = SiriusHub(
        session,
        sirius_endpoint,
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
        insecure_tls=user_input.get(CONF_INSECURE_TLS, False),
    )
    try:
        devices = await hub.async_discover_devices(retry=False)
        if not devices:
            _LOGGER.warning("Sirius login succeeded but no devices found")
            errors["base"] = "no_devices"
            return None
        _LOGGER.info("Sirius authenticated, %d device(s) discovered", len(devices))
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
        """Handle the initial step — credentials only."""
        errors: dict[str, str] = {}

        if user_input is not None:
            devices = await _try_discover_devices(self.hass, user_input, errors)
            if devices is not None:
                self._user_input = user_input
                self._devices = devices
                self._async_abort_entries_match(
                    {CONF_USERNAME: user_input[CONF_USERNAME]}
                )
                return await self.async_step_setup_method()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_setup_method(
        self, _: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show menu: finish with defaults or configure endpoints."""
        return self.async_show_menu(
            step_id="setup_method",
            menu_options={
                "finish": "Finish setup",
                "endpoints": "Configure custom endpoints",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reconfigure an existing entry — update credentials or endpoints."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        current_endpoint = entry.data.get(CONF_SIRIUS_ENDPOINT, DEFAULT_SIRIUS_ENDPOINT)
        current_mqtts = entry.data.get(CONF_SIRIUS_MQTTS_ENDPOINT, DEFAULT_SIRIUS_MQTTS_ENDPOINT)

        if user_input is not None:
            devices = await _try_discover_devices(
                self.hass, user_input, errors,
                sirius_endpoint=current_endpoint,
                mqtts_endpoint=current_mqtts,
            )
            if devices is not None:
                self._user_input = user_input
                self._devices = devices
                return await self.async_step_update_method()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_update_method(
        self, _: dict[str, Any] | None = None
    ) -> FlowResult:
        """Menu for reconfigure: keep endpoints or change them."""
        return self.async_show_menu(
            step_id="update_method",
            menu_options={
                "finish": "Keep current endpoints",
                "endpoints": "Change endpoints",
            },
        )

    async def async_step_finish(
        self, _: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create or update the config entry with current settings."""
        data = {
            **self._user_input,
            CONF_SIRIUS_ENDPOINT: (
                self._user_input.get(CONF_SIRIUS_ENDPOINT, DEFAULT_SIRIUS_ENDPOINT)
            ),
            CONF_SIRIUS_MQTTS_ENDPOINT: (
                self._user_input.get(CONF_SIRIUS_MQTTS_ENDPOINT, DEFAULT_SIRIUS_MQTTS_ENDPOINT)
            ),
            CONF_INSECURE_TLS: self._user_input.get(CONF_INSECURE_TLS, False),
        }
        title = (
            f"Sirius Rangehood ({len(self._devices)} device"
            f"{'s' if len(self._devices) > 1 else ''})"
        )

        if reconf := self._get_reconfigure_entry():
            return self.async_update_reload_and_abort(
                reconf,
                data={**reconf.data, **data},
            )
        return self.async_create_entry(title=title, data=data)

    async def async_step_endpoints(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional custom endpoint configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url_error = _validate_urls(
                user_input[CONF_SIRIUS_ENDPOINT],
                user_input[CONF_SIRIUS_MQTTS_ENDPOINT],
            )
            if url_error:
                errors["base"] = url_error
            else:
                data = {
                    **self._user_input,
                    CONF_SIRIUS_ENDPOINT: user_input[CONF_SIRIUS_ENDPOINT],
                    CONF_SIRIUS_MQTTS_ENDPOINT: user_input[CONF_SIRIUS_MQTTS_ENDPOINT],
                    CONF_INSECURE_TLS: user_input.get(CONF_INSECURE_TLS, False),
                }
                title = (
                    f"Sirius Rangehood ({len(self._devices)} device"
                    f"{'s' if len(self._devices) > 1 else ''})"
                )
                if reconf := self._get_reconfigure_entry():
                    return self.async_update_reload_and_abort(
                        reconf,
                        data={**reconf.data, **data},
                    )
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="endpoints",
            data_schema=STEP_ENDPOINTS_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Re-authenticate with new credentials after a token rejection."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        current_endpoint = entry.data.get(CONF_SIRIUS_ENDPOINT, DEFAULT_SIRIUS_ENDPOINT)
        current_mqtts = entry.data.get(CONF_SIRIUS_MQTTS_ENDPOINT, DEFAULT_SIRIUS_MQTTS_ENDPOINT)
        current_insecure = entry.data.get(CONF_INSECURE_TLS, False)

        if user_input is not None:
            devices = await _try_discover_devices(
                self.hass, user_input, errors,
                sirius_endpoint=current_endpoint,
                mqtts_endpoint=current_mqtts,
            )
            if devices is not None:
                _LOGGER.info("Sirius reauth succeeded, %d device(s)", len(devices))
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_INSECURE_TLS: user_input.get(CONF_INSECURE_TLS, current_insecure),
                    },
                )
        else:
            user_input = {
                CONF_USERNAME: entry.data.get(CONF_USERNAME, ""),
                CONF_PASSWORD: "",
                CONF_INSECURE_TLS: current_insecure,
            }

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_INSECURE_TLS, default=user_input[CONF_INSECURE_TLS]): bool,
            }
        )
        return self.async_show_form(
            step_id="reauth",
            data_schema=schema,
            errors=errors,
            description_placeholders={"endpoint": current_endpoint},
        )