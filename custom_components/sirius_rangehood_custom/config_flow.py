# Copyright (c) 2026 Warren Spits
"""Config flow for Sirius Rangehood."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DEFAULT_SIRIUS_ENDPOINT,
    DEFAULT_SIRIUS_MQTTS_ENDPOINT,
    SiriusAuthError,
    SiriusHub,
)
from .const import (
    CONF_INSECURE_TLS,
    CONF_SIRIUS_ENDPOINT,
    CONF_SIRIUS_MQTTS_ENDPOINT,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

STEP_ENDPOINTS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SIRIUS_ENDPOINT, default=DEFAULT_SIRIUS_ENDPOINT): str,
        vol.Required(
            CONF_SIRIUS_MQTTS_ENDPOINT, default=DEFAULT_SIRIUS_MQTTS_ENDPOINT
        ): str,
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
    *,
    sirius_endpoint: str = DEFAULT_SIRIUS_ENDPOINT,
    insecure_tls: bool = False,
) -> list[dict[str, Any]] | None:
    """Validate credentials against an endpoint and discover devices."""
    session = async_get_clientsession(hass, verify_ssl=not insecure_tls)
    hub = SiriusHub(
        session,
        sirius_endpoint,
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
    )
    try:
        devices = await hub.async_discover_devices(retry=False)
    except SiriusAuthError:
        errors["base"] = "invalid_auth"
        return None
    except Exception:
        _LOGGER.exception("Unexpected error during config flow")
        errors["base"] = "cannot_connect"
        return None
    else:
        if not devices:
            _LOGGER.warning("Sirius login succeeded but no devices found")
            errors["base"] = "no_devices"
            return None
        _LOGGER.info("Sirius authenticated, %d device(s) discovered", len(devices))
        return devices


class SiriusRangehoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sirius Rangehood."""

    VERSION = 1

    _user_input: dict[str, Any]
    _config: dict[str, Any]
    _devices: list[dict[str, Any]]

    def _existing_entry(self) -> ConfigEntry | None:
        """Return the entry being reconfigured or reauthenticated, if any."""
        if self.source == "reconfigure":
            return self._get_reconfigure_entry()
        if self.source == "reauth":
            return self._get_reauth_entry()
        return None

    def _async_save_entry(self) -> ConfigFlowResult:
        """Create a new entry, or update the existing one, with current settings."""
        data = {**self._user_input, **self._config}
        title = (
            f"Sirius Rangehood ({len(self._devices)} device"
            f"{'s' if len(self._devices) > 1 else ''})"
        )
        entry = self._existing_entry()
        if entry:
            # Reconfigure/reauth: keep everything, overwrite only what changed.
            return self.async_update_reload_and_abort(
                entry, data={**entry.data, **data}
            )
        return self.async_create_entry(title=title, data=data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial or reconfigure step: credentials only."""
        errors: dict[str, str] = {}
        entry = self._existing_entry()

        prefill: dict[str, Any] = {}
        if user_input is None and entry is not None:
            prefill = {CONF_USERNAME: entry.data.get(CONF_USERNAME, "")}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, default=prefill.get(CONF_USERNAME, "")
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        if user_input is not None:
            endpoint = (
                entry.data.get(CONF_SIRIUS_ENDPOINT, DEFAULT_SIRIUS_ENDPOINT)
                if entry
                else DEFAULT_SIRIUS_ENDPOINT
            )
            mqtts_endpoint = (
                entry.data.get(
                    CONF_SIRIUS_MQTTS_ENDPOINT, DEFAULT_SIRIUS_MQTTS_ENDPOINT
                )
                if entry
                else DEFAULT_SIRIUS_MQTTS_ENDPOINT
            )
            insecure_tls = entry.data.get(CONF_INSECURE_TLS, False) if entry else False

            devices = await _try_discover_devices(
                self.hass,
                user_input,
                errors,
                sirius_endpoint=endpoint,
                insecure_tls=insecure_tls,
            )
            if devices is not None:
                self._user_input = user_input
                self._config = {
                    CONF_SIRIUS_ENDPOINT: endpoint,
                    CONF_SIRIUS_MQTTS_ENDPOINT: mqtts_endpoint,
                    CONF_INSECURE_TLS: insecure_tls,
                }
                self._devices = devices
                if entry is None:
                    self._async_abort_entries_match(
                        {CONF_USERNAME: user_input[CONF_USERNAME]}
                    )
                return await self.async_step_menu()

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authenticate with new credentials after a token rejection."""
        return await self.async_step_user(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry."""
        return await self.async_step_user(user_input)

    async def async_step_menu(
        self, _: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show menu: finish with current settings or change endpoints."""
        is_reconf = self.source == "reconfigure"
        return self.async_show_menu(
            step_id="menu",
            menu_options={
                "finish": "Keep current endpoints" if is_reconf else "Finish setup",
                "endpoints": "Change endpoints"
                if is_reconf
                else "Configure custom endpoints",
            },
        )

    async def async_step_finish(
        self, _: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the entry, keeping the validated settings."""
        return self._async_save_entry()

    async def async_step_endpoints(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                endpoint = user_input[CONF_SIRIUS_ENDPOINT]
                insecure_tls = user_input.get(CONF_INSECURE_TLS, False)
                devices = await _try_discover_devices(
                    self.hass,
                    self._user_input,
                    errors,
                    sirius_endpoint=endpoint,
                    insecure_tls=insecure_tls,
                )
                if devices is not None:
                    self._devices = devices
                    self._config = {
                        CONF_SIRIUS_ENDPOINT: endpoint,
                        CONF_SIRIUS_MQTTS_ENDPOINT: user_input[
                            CONF_SIRIUS_MQTTS_ENDPOINT
                        ],
                        CONF_INSECURE_TLS: insecure_tls,
                    }
                    return self._async_save_entry()

        schema = self.add_suggested_values_to_schema(
            STEP_ENDPOINTS_SCHEMA, self._config
        )
        return self.async_show_form(
            step_id="endpoints",
            data_schema=schema,
            errors=errors,
        )
