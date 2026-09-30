"""Binary sensor platform for Sirius Rangehood timer status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CAP_TIMER_ACTIVE, CAP_TIMER_ENABLE
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
        if CAP_TIMER_ENABLE not in device.get("_limits", {}):
            continue
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodTimerActive(coordinator, did, device, entry))

    async_add_entities(entities)


class SiriusRangehoodTimerActive(CoordinatorEntity, BinarySensorEntity):
    """Whether the timer is currently counting down."""

    _attr_has_entity_name = True
    _attr_translation_key = "timer_active"

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the timer active binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer_active"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        """Return whether the timer is running."""
        state = self._get_device_state()
        val = state.get(CAP_TIMER_ACTIVE)
        if val is not None:
            return bool(val)
        return None