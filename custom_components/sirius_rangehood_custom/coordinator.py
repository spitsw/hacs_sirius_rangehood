# Copyright (c) 2026 Warren Spits
"""DataUpdateCoordinator for Sirius Rangehood."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import GET_STATUS_INTERVAL, SiriusAuthError, SiriusHub
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SiriusRangehoodCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """
    Owns the authoritative per-device state for a Sirius account.

    Both data paths funnel through this coordinator: MQTT push updates via
    :meth:`apply_mqtt_update`, and the periodic HTTP ``getStatus`` heartbeat
    via :meth:`_async_update_data`.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        hub: SiriusHub,
        device_states: dict[str, dict[str, Any]],
    ) -> None:
        """Initialize the coordinator with the discovered device state."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} devices",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=GET_STATUS_INTERVAL),
        )
        self._entry = entry
        self._hub = hub
        self.device_states = device_states

    @property
    def hub(self) -> SiriusHub:
        """Return the HTTP API client backing this coordinator."""
        return self._hub

    def request_reauth(self) -> None:
        """Ask Home Assistant to start the re-authentication flow."""
        self.hass.async_create_task(
            self.hass.config_entries.async_start_reauth(self._entry.entry_id)
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Heartbeat: send getStatus for all devices in parallel."""
        _LOGGER.debug("Coordinator update for %d device(s)", len(self.device_states))
        results = await asyncio.gather(
            *[self._hub.async_get_status(did) for did in self.device_states],
            return_exceptions=True,
        )
        for device_id, result in zip(list(self.device_states), results, strict=False):
            if isinstance(result, SiriusAuthError):
                _LOGGER.warning(
                    "Auth failed for device %s, requesting reauth", device_id
                )
                self.request_reauth()
                return dict(self.device_states)
            if isinstance(result, Exception):
                _LOGGER.error("getStatus failed for device %s", device_id)
        return dict(self.device_states)

    def apply_mqtt_update(self, device_id: str, payload: dict[str, Any]) -> None:
        """
        Merge an MQTT status payload and notify listeners.

        Must only be called on the HA event loop; the paho-mqtt thread reaches
        it via ``hass.loop.call_soon_threadsafe``.
        """
        if device_id in self.device_states:
            _LOGGER.debug("MQTT status for device %s: %s", device_id, payload)
            self.device_states[device_id].update(payload)
            self.async_set_updated_data(dict(self.device_states))
