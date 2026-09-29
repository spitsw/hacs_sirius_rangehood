"""Integration setup for Sirius Rangehood."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_SIRIUS_ENDPOINT,
    CONF_SIRIUS_MQTTS_ENDPOINT,
    DEVICES_POLL_INTERVAL,
    DOMAIN,
    GET_STATUS_INTERVAL,
    LIVE_CAPABILITY_KEYS,
)
from .hub import SiriusHub, SiriusAuthError
from .mqtt import SiriusMQTT

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.FAN, Platform.LIGHT, Platform.SWITCH, Platform.SENSOR]

# ── Reauth trigger helper (used by coordinator update & device-poll) ──


def _trigger_reauth(hass: HomeAssistant, entry_id: str) -> None:
    """Fire a reauthentication flow."""
    hass.async_create_task(
        hass.config_entries.async_start_reauth(entry_id)
    )


# ── Token persistence ──


async def _restore_token(
    hass: HomeAssistant, entry: ConfigEntry, hub: SiriusHub
) -> None:
    """Load a previously persisted auth token from HA storage."""
    from homeassistant.helpers.storage import Store  # noqa: PLC0415 — inline to avoid top-level HA import ordering

    store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}_auth_{entry.entry_id}")
    hub.attach_store(store)

    stored = await store.async_load()
    if stored:
        hub.restore_token(
            stored.get("token"),
            stored.get("expiry"),
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sirius Rangehood from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    sirius_endpoint = entry.data[CONF_SIRIUS_ENDPOINT]
    mqtts_endpoint = entry.data[CONF_SIRIUS_MQTTS_ENDPOINT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = async_get_clientsession(hass)
    hub = SiriusHub(session, sirius_endpoint, username, password)

    await _restore_token(hass, entry, hub)

    # Discover devices — gets static properties + initial capability values
    devices = await hub.async_discover_devices()
    if not devices:
        _LOGGER.warning("No Sirius devices discovered")
        return False

    # Shared device state: device_id (int) -> flattened state dict
    device_states: dict[int, dict[str, Any]] = {}
    for device in devices:
        device_states[device["id"]] = dict(device)

    entry_id = entry.entry_id

    # Coordinator — sends getStatus heartbeat every 5 min
    async def _async_update_data() -> dict[int, dict[str, Any]]:
        """Heartbeat: send getStatus for all devices in parallel."""
        _LOGGER.debug("Coordinator update for %d device(s)", len(device_states))
        results = await asyncio.gather(
            *[hub.async_get_status(did) for did in device_states],
            return_exceptions=True,
        )
        for device_id, result in zip(list(device_states), results):
            if isinstance(result, SiriusAuthError):
                _LOGGER.warning("Auth failed for device %d, requesting reauth", device_id)
                _trigger_reauth(hass, entry_id)
                return dict(device_states)
            if isinstance(result, Exception):
                _LOGGER.exception("getStatus failed for device %d", device_id)
        return dict(device_states)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN} devices",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=GET_STATUS_INTERVAL),
    )

    # Separate timer — poll /devices/ hourly for static property changes
    async def _poll_devices(_now: datetime | None = None) -> None:
        """Poll /devices/ for new devices and static property changes."""
        try:
            fresh = await hub.async_discover_devices()
            new_ids: set[int] = set()
            for device in fresh:
                did = device["id"]
                if did in device_states:
                    for k, v in device.items():
                        if k not in LIVE_CAPABILITY_KEYS:
                            device_states[did][k] = v
                else:
                    new_ids.add(did)

            if new_ids:
                _LOGGER.info(
                    "New Sirius device(s) detected (IDs: %s), reloading entry",
                    sorted(new_ids),
                )
                hass.async_create_task(
                    hass.config_entries.async_reload(entry_id)
                )
        except SiriusAuthError:
            _LOGGER.warning("Auth rejected during /devices/ poll, requesting reauth")
            _trigger_reauth(hass, entry_id)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to refresh devices from /devices/")

    entry.async_on_unload(
        async_track_time_interval(
            hass, _poll_devices, timedelta(seconds=DEVICES_POLL_INTERVAL)
        )
    )

    # MQTT status callback — called from paho-mqtt background thread.
    # All device_states access happens on the HA event loop to avoid concurrent
    # reads/writes from both the paho thread and the coordinator.
    def _on_mqtt_status(device_id: str, payload: dict[str, Any]) -> None:
        """Forward MQTT update to the HA event loop for thread-safe processing."""
        hass.loop.call_soon_threadsafe(
            _apply_mqtt_update, device_id, payload
        )

    def _apply_mqtt_update(device_id: str, payload: dict[str, Any]) -> None:
        """Match device, update state, and notify coordinator (HA event loop only)."""
        for did, state in device_states.items():
            if state.get("uid") == device_id:
                _LOGGER.debug("MQTT status for device %d: %s", did, payload)
                device_states[did].update(payload)
                coordinator.async_set_updated_data(dict(device_states))
                return
        _LOGGER.debug("MQTT status for unknown uid %s, reloading", device_id)
        hass.async_create_task(
            hass.config_entries.async_reload(entry_id)
        )

    # Start MQTT
    mqtt = SiriusMQTT(mqtts_endpoint, username, password, _on_mqtt_status)
    mqtt_connected = await mqtt.async_start()
    if mqtt_connected:
        for device in devices:
            mqtt.subscribe_device(device.get("uid", str(device["id"])))

    try:
        # Initial refresh sends getStatus to bootstrap live state via MQTT
        await coordinator.async_config_entry_first_refresh()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Initial refresh failed, cleaning up")
        await mqtt.async_stop()
        return False

    _LOGGER.info(
        "Sirius Rangehood setup complete: %d device(s), %s",
        len(devices),
        "MQTT connected" if mqtt_connected else "MQTT offline",
    )

    # Proactive token refresh — refresh 1 minute before expiry so API calls
    # never have to wait for a login round-trip.
    async def _refresh_token(now: datetime | None = None) -> None:
        """Refresh the auth token before it expires."""
        try:
            await hub.async_ensure_token()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to refresh auth token")
        if hub._token_expiry:
            remaining = (hub._token_expiry - datetime.now()).total_seconds() - 60
            if remaining > 0:
                entry.async_on_unload(
                    async_call_later(hass, remaining, _refresh_token)
                )

    await _refresh_token()

    def _reauth() -> None:
        _trigger_reauth(hass, entry_id)

    # Store runtime data
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
        "mqtt": mqtt,
        "coordinator": coordinator,
        "device_states": device_states,
        "devices": devices,
        "reauth": _trigger_reauth,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        mqtt: SiriusMQTT = data["mqtt"]
        await mqtt.async_stop()
        coordinator = data["coordinator"]
        await coordinator.async_shutdown()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reconfigure on update."""
    await hass.config_entries.async_reload(entry.entry_id)