# Copyright (c) 2026 Warren Spits
"""Binary sensor platform for Sirius Rangehood filter status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .api import CAP_FILTER_WORN
from .entity import SiriusEntity, sirius_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    data = entry.runtime_data
    coordinator = data.coordinator
    devices = data.devices

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodFilterWorn(coordinator, did, device, entry))
    async_add_entities(entities)


class SiriusRangehoodFilterWorn(SiriusEntity, BinarySensorEntity):
    """Filter worn indicator; on when the filter needs cleaning."""

    _attr_translation_key = "filter_worn"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the filter-worn binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_filter_worn"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        """Return True when the filter needs cleaning."""
        state = self._get_device_state()
        val = state.get(CAP_FILTER_WORN)
        if val is not None:
            return bool(val)
        return None

    @property
    def icon(self) -> str:
        """Return the filter icon reflecting the current state."""
        return "mdi:air-filter-alert" if self.is_on else "mdi:air-filter"
