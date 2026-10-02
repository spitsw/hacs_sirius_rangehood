# Copyright (c) 2026 Warren Spits
"""Diagnostics platform for Sirius Rangehood."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .api import PROP_FW_VERSION, PROP_IP_ADDRESS, PROP_SECURE_ID, PROP_SSID
from .const import DOMAIN
from .entity import device_key

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry

    from .data import SiriusRangehoodConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    PROP_IP_ADDRESS,
    PROP_SSID,
    PROP_SECURE_ID,
}


def _device_summary(device: dict[str, Any]) -> dict[str, Any]:
    """Return a redactable summary of a device's static metadata."""
    return {
        "id": device["id"],
        "uid": device.get("uid"),
        "name": device.get("name"),
        "model": device.get("description"),
        "fw_version": device.get(PROP_FW_VERSION),
        "capabilities": list(device.get("_limits", {})),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SiriusRangehoodConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    hub = data.hub
    coordinator = data.coordinator
    mqtt = data.mqtt

    diagnostics = {
        "entry_id": entry.entry_id,
        "data": dict(entry.data),
        "devices": [_device_summary(d) for d in data.devices],
        "coordinator": {
            "data": coordinator.data,
            "last_update_success": coordinator.last_update_success,
        },
        "hub": {
            "endpoint": hub.endpoint,
            "token_expiry": (
                hub.token_expiry.isoformat() if hub.token_expiry else None
            ),
        },
        "mqtt": {
            "connected": mqtt.connected if mqtt else False,
            "host": mqtt.host if mqtt else None,
        }
        if mqtt
        else None,
    }
    return async_redact_data(diagnostics, TO_REDACT)


async def async_get_device_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SiriusRangehoodConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a specific device."""
    data = entry.runtime_data
    hub = data.hub

    device_info = None
    for d in data.devices:
        if {(DOMAIN, device_key(d))} == device.identifiers:
            device_info = _device_summary(d)
            break

    diagnostics = {
        "entry_id": entry.entry_id,
        "device": device_info,
        "coordinator": {
            "last_update_success": data.coordinator.last_update_success,
        },
        "hub": {
            "token_expiry": hub.token_expiry.isoformat() if hub.token_expiry else None,
        },
    }
    return async_redact_data(diagnostics, TO_REDACT)
