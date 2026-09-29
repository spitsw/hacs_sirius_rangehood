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
            }
            for d in data["devices"]
        ],
        "coordinator_data": coordinator.data,
        "hub_token_expiry": (
            hub._token_expiry.isoformat() if hub._token_expiry else None
        ),
        "mqtt_host": hub._sirius_endpoint if hasattr(hub, "_sirius_endpoint") else None,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a device entry.

    Delegates to the config-entry-level diagnostics since the component
    stores all device state in a single coordinator.
    """
    return await async_get_config_entry_diagnostics(hass, entry)