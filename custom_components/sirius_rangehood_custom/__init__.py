# Copyright (c) 2026 Warren Spits
"""Integration setup for Sirius Rangehood."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .api import SiriusAuthError, SiriusHub, SiriusMQTT
from .const import (
    CONF_INSECURE_TLS,
    CONF_SIRIUS_ENDPOINT,
    CONF_SIRIUS_MQTTS_ENDPOINT,
    DOMAIN,
)
from .coordinator import SiriusRangehoodCoordinator
from .data import SiriusRangehoodData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SiriusRangehoodConfigEntry

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.FAN,
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.NUMBER,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SiriusRangehoodConfigEntry,
) -> bool:
    """Set up Sirius Rangehood from a config entry."""
    sirius_endpoint = entry.data[CONF_SIRIUS_ENDPOINT]
    mqtts_endpoint = entry.data[CONF_SIRIUS_MQTTS_ENDPOINT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    insecure_tls = entry.data.get(CONF_INSECURE_TLS, False)

    session = async_get_clientsession(hass, verify_ssl=not insecure_tls)
    hub = SiriusHub(session, sirius_endpoint, username, password)

    # Auth token persistence
    store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}_auth_{entry.entry_id}")
    hub.attach_store(store)
    stored = await store.async_load()
    if stored:
        hub.restore_token(stored.get("token"), stored.get("expiry"))

    # Discover devices: gets static properties + initial capability values
    try:
        devices = await hub.async_discover_devices()
    except SiriusAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:
        msg = f"Sirius device discovery failed: {err}"
        raise ConfigEntryNotReady(msg) from err
    if not devices:
        msg = "No Sirius devices discovered"
        raise ConfigEntryNotReady(msg)

    # Shared device state: uid (str) -> flattened state dict
    device_states: dict[str, dict[str, Any]] = {}
    for device in devices:
        did = device.get("uid", str(device["id"]))
        device_states[did] = dict(device)

    # Coordinator owns the authoritative state and the getStatus heartbeat.
    coordinator = SiriusRangehoodCoordinator(hass, entry, hub, device_states)

    # MQTT status callback: called from paho-mqtt background thread.
    # All device_states access happens on the HA event loop to avoid concurrent
    # reads/writes from both the paho thread and the coordinator.
    def _on_mqtt_status(device_id: str, payload: dict[str, Any]) -> None:
        """Forward MQTT update to the HA event loop for thread-safe processing."""
        hass.loop.call_soon_threadsafe(
            coordinator.apply_mqtt_update, device_id, payload
        )

    # Start MQTT
    mqtt = SiriusMQTT(
        mqtts_endpoint, username, password, _on_mqtt_status, insecure_tls=insecure_tls
    )
    mqtt_connected = await mqtt.async_start()
    if mqtt_connected:
        for device in devices:
            mqtt.subscribe_device(device.get("uid", str(device["id"])))

    try:
        # Initial refresh sends getStatus to bootstrap live state via MQTT
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.exception("Initial refresh failed, cleaning up")
        await mqtt.async_stop()
        return False

    _LOGGER.info(
        "Sirius Rangehood setup complete: %d device(s), %s",
        len(devices),
        "MQTT connected" if mqtt_connected else "MQTT offline",
    )

    await _async_refresh_token(hass, entry, hub)

    entry.runtime_data = SiriusRangehoodData(
        hub=hub,
        mqtt=mqtt,
        coordinator=coordinator,
        device_states=device_states,
        devices=devices,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_refresh_token(
    hass: HomeAssistant,
    entry: SiriusRangehoodConfigEntry,
    hub: SiriusHub,
) -> None:
    """Refresh the auth token, rescheduling one minute before it next expires."""
    try:
        await hub.async_ensure_token()
    except Exception:
        _LOGGER.exception("Failed to refresh auth token")
    expiry = hub.token_expiry
    if expiry is None:
        return
    remaining = (expiry - datetime.now(UTC)).total_seconds() - 60
    if remaining > 0:
        entry.async_on_unload(
            async_call_later(
                hass,
                remaining,
                lambda _now: hass.async_create_task(
                    _async_refresh_token(hass, entry, hub)
                ),
            )
        )


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SiriusRangehoodConfigEntry,
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = entry.runtime_data
    if unloaded and data:
        await data.mqtt.async_stop()
        await data.coordinator.async_shutdown()

    return unloaded


async def _async_update_listener(
    hass: HomeAssistant,
    entry: SiriusRangehoodConfigEntry,
) -> None:
    """Reconfigure on update."""
    await hass.config_entries.async_reload(entry.entry_id)
