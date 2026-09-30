"""Number platform for Sirius Rangehood timer control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    CAP_TIMER_MODIFIABLE,
    CAP_TIMER_VALUE,
    SiriusAuthError,
)
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodTimer(coordinator, did, device, entry))

    async_add_entities(entities)


class SiriusRangehoodTimer(CoordinatorEntity, NumberEntity):
    """Timer duration for auto-shutoff.

    Shows the countdown duration in minutes. The API stores the value
    in seconds; conversion happens on read and write.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "timer_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_mode = "auto"

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the timer number."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

        limits = device.get("_limits", {}).get(CAP_TIMER_VALUE, {})
        self._attr_native_min_value = limits.get("min", 0) if limits else 0
        self._attr_native_max_value = limits.get("max", 6000) if limits else 6000
        self._attr_native_step = 1

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def native_value(self) -> float | None:
        """Return the timer duration in seconds."""
        state = self._get_device_state()
        val = state.get(CAP_TIMER_VALUE)
        if val is not None:
            return float(val)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the timer duration in seconds."""
        await self._async_send_command(
            [{"id": CAP_TIMER_VALUE, "value": int(value)}]
        )

    @property
    def available(self) -> bool:
        """Entity is available when the timer is modifiable."""
        state = self._get_device_state()
        return bool(state.get(CAP_TIMER_MODIFIABLE, False))

    async def _async_send_command(self, params: list[dict[str, Any]]) -> None:
        """Send a setValue command via the hub."""
        data = self.hass.data[DOMAIN][self._entry_id]
        hub = data["hub"]
        try:
            await hub.async_send_command(self._device_id, params)
        except SiriusAuthError:
            data.get("reauth", lambda: None)()