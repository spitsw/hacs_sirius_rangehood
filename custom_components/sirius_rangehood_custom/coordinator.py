# Copyright (c) 2026 Warren Spits
"""DataUpdateCoordinator for Sirius Rangehood."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import GET_STATUS_INTERVAL, SiriusAuthError, SiriusHub
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

_LOGGER = logging.getLogger(__name__)

MQTT_ISSUE_ID = "mqtt_unavailable"


class SiriusRangehoodCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """
    Owns the authoritative per-device state for a Sirius account.

    Both data paths funnel through this coordinator: MQTT push updates via
    :meth:`apply_mqtt_update`, and the periodic HTTP ``getStatus`` heartbeat
    via :meth:`_async_update_data`. It also tracks MQTT broker connectivity so
    entities can go unavailable and a Repairs issue can surface on outage.
    """

    _MQTT_GRACE_PERIOD = timedelta(seconds=30)

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
        self._mqtt_connected = False
        self._mqtt_down_since: datetime | None = None
        self._grace_unsub: CALLBACK_TYPE | None = None
        self._mqtt_repair_raised = False

    @property
    def hub(self) -> SiriusHub:
        """Return the HTTP API client backing this coordinator."""
        return self._hub

    @property
    def mqtt_connected(self) -> bool:
        """Return True while the MQTT broker connection is up."""
        return self._mqtt_connected

    @property
    def mqtt_available(self) -> bool:
        """
        Return True when MQTT state is fresh enough to trust.

        A short grace period after a disconnect avoids flapping entities
        unavailable during paho's automatic reconnect.
        """
        if self._mqtt_connected:
            return True
        if self._mqtt_down_since is None:
            return True
        return datetime.now(UTC) - self._mqtt_down_since < self._MQTT_GRACE_PERIOD

    def set_mqtt_connected(self, connected: bool) -> None:  # noqa: FBT001
        """
        Record broker connectivity and refresh consumers.

        Must only be called on the HA event loop; the paho-mqtt thread reaches
        it via ``hass.loop.call_soon_threadsafe``.
        """
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None
        self._mqtt_connected = connected
        if connected:
            self._mqtt_down_since = None
            self._clear_mqtt_repair()
        else:
            self._mqtt_down_since = datetime.now(UTC)
            self._grace_unsub = async_call_later(
                self.hass,
                self._MQTT_GRACE_PERIOD.total_seconds(),
                self._on_mqtt_grace_elapsed,
            )
        self.async_set_updated_data(self._snapshot())

    def _on_mqtt_grace_elapsed(self, _now: datetime) -> None:
        """Raise the outage repair once the grace period has passed."""
        self._grace_unsub = None
        self._raise_mqtt_repair()
        self.async_set_updated_data(self._snapshot())

    def _raise_mqtt_repair(self) -> None:
        if self._mqtt_repair_raised:
            return
        self._mqtt_repair_raised = True
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            MQTT_ISSUE_ID,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=MQTT_ISSUE_ID,
        )

    def _clear_mqtt_repair(self) -> None:
        if not self._mqtt_repair_raised:
            return
        self._mqtt_repair_raised = False
        ir.async_delete_issue(self.hass, DOMAIN, MQTT_ISSUE_ID)

    async def async_shutdown(self) -> None:
        """Cancel pending timers before shutting the coordinator down."""
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None
        await super().async_shutdown()

    def request_reauth(self) -> None:
        """Ask Home Assistant to start the re-authentication flow."""
        self._entry.async_start_reauth(self.hass)

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a shallow copy of the device state for listeners."""
        return dict(self.device_states)

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
                return self._snapshot()
            if isinstance(result, Exception):
                _LOGGER.error("getStatus failed for device %s", device_id)
            elif result is False:
                _LOGGER.debug("getStatus request not accepted for %s", device_id)
        return self._snapshot()

    def apply_mqtt_update(self, device_id: str, payload: dict[str, Any]) -> None:
        """
        Merge an MQTT status payload and notify listeners.

        Must only be called on the HA event loop; the paho-mqtt thread reaches
        it via ``hass.loop.call_soon_threadsafe``.
        """
        if device_id in self.device_states:
            _LOGGER.debug("MQTT status for device %s: %s", device_id, payload)
            self.device_states[device_id].update(payload)
            self.async_set_updated_data(self._snapshot())
