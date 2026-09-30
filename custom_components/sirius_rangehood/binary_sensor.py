"""Binary sensor platform for Sirius Rangehood filter status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CAP_FILTER_WORN, PROP_FW_VERSION
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodFilterWorn(coordinator, did, device, entry))

    async_add_entities(entities)


class SiriusRangehoodFilterWorn(CoordinatorEntity, BinarySensorEntity):
    """Filter worn indicator — on when the filter needs cleaning."""

    _attr_has_entity_name = True
    _attr_translation_key = "filter_worn"

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the filter worn binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_filter_worn"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.get("name", f"Sirius Rangehood {device_id}"),
            manufacturer="Sirius",
            model=device.get("description", "Rangehood"),
            sw_version=device.get(PROP_FW_VERSION),
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        """Return whether the filter needs cleaning."""
        state = self._get_device_state()
        val = state.get(CAP_FILTER_WORN)
        if val is not None:
            return bool(val)
        return None

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:air-filter-alert" if self.is_on else "mdi:air-filter"