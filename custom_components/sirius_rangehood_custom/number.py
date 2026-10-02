# Copyright (c) 2026 Warren Spits
"""Number platform for Sirius Rangehood timer control."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity

from .api import (
    CAP_TIMER_ACTIVE,
    CAP_TIMER_MODIFIABLE,
    CAP_TIMER_VALUE,
)
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
    """Set up the number platform."""
    data = entry.runtime_data
    coordinator = data.coordinator
    devices = data.devices

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodTimer(coordinator, did, device, entry))
    async_add_entities(entities)


class SiriusRangehoodTimer(SiriusEntity, NumberEntity):
    """Timer duration in seconds. Disabled while the countdown is running."""

    _attr_translation_key = "timer_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_mode = "auto"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the timer duration entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer"
        self._attr_device_info = sirius_device_info(device_id, device)

        limits = device.get("_limits", {}).get(CAP_TIMER_VALUE, {})
        self._attr_native_min_value = limits.get("min", 0) if limits else 0
        self._attr_native_max_value = limits.get("max", 6000) if limits else 6000
        self._attr_native_step = 1

    @property
    def native_value(self) -> float | None:
        """Return the configured timer duration in seconds."""
        state = self._get_device_state()
        val = state.get(CAP_TIMER_VALUE)
        if val is not None:
            return float(val)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the timer duration in seconds."""
        await self._async_send_command([{"id": CAP_TIMER_VALUE, "value": int(value)}])

    @property
    def available(self) -> bool:
        """Return True when the timer duration can be changed."""
        state = self._get_device_state()
        return (
            super().available
            and bool(state.get(CAP_TIMER_MODIFIABLE, False))
            and not bool(state.get(CAP_TIMER_ACTIVE, False))
        )
