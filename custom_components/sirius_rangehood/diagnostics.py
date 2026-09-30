"""Diagnostics platform for Sirius Rangehood."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    hub = data["hub"]
    coordinator = data["coordinator"]
    mqtt = data.get("mqtt")

    return {
        "entry_id": entry.entry_id,
        "data": {
            k: v for k, v in entry.data.items() if k != "password"
        },
        "devices": [
            {
                "id": d["id"],
                "uid": d.get("uid"),
                "name": d.get("name"),
                "model": d.get("description"),
                "fw_version": d.get("property.device.fw.version"),
                "capabilities": list(d.get("_limits", {})),
            }
            for d in data["devices"]
        ],
        "coordinator": {
            "data": coordinator.data,
            "last_update_success": coordinator.last_update_success,
        },
        "hub": {
            "endpoint": hub._sirius_endpoint,
            "token_expiry": (
                hub._token_expiry.isoformat() if hub._token_expiry else None
            ),
        },
        "mqtt": {
            "connected": mqtt._client.is_connected() if mqtt and mqtt._client else False,
            "host": mqtt._host if mqtt else None,
        } if mqtt else None,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a device entry.

    Delegates to the config-entry-level diagnostics since the component
    stores all device state in a single coordinator.
    """
    return await async_get_config_entry_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a device entry.

    Delegates to the config-entry-level diagnostics since the component
    stores all device state in a single coordinator.
    """
    return await async_get_config_entry_diagnostics(hass, entry)