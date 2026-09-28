"""Config flow for Sirius Rangehood."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_SIRIUS_ENDPOINT, CONF_SIRIUS_MQTTS_ENDPOINT, DOMAIN
from .hub import SiriusHub, SiriusAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SIRIUS_ENDPOINT): str,
        vol.Required(CONF_SIRIUS_MQTTS_ENDPOINT): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class SiriusRangehoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sirius Rangehood."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_SIRIUS_ENDPOINT: user_input[CONF_SIRIUS_ENDPOINT]}
            )

            session = async_get_clientsession(self.hass)
            hub = SiriusHub(
                session,
                user_input[CONF_SIRIUS_ENDPOINT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )

            try:
                devices = await hub.async_discover_devices()
                if not devices:
                    _LOGGER.warning("Sirius login succeeded but no devices found")
                    errors["base"] = "no_devices"
                else:
                    _LOGGER.info(
                        "Sirius authenticated, %d device(s) discovered", len(devices)
                    )
                    return self.async_create_entry(
                        title=f"Sirius Rangehood ({len(devices)} device{'s' if len(devices) > 1 else ''})",
                        data=user_input,
                    )
            except SiriusAuthError:
                errors["base"] = "invalid_auth"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Re-authenticate with new credentials."""
        return await self.async_step_user(user_input)