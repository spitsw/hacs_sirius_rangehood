# Copyright (c) 2026 Warren Spits
"""Number platform for Sirius Rangehood timer control."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode

from .api import (
    CAP_TIMER_ACTIVE,
    CAP_TIMER_MODIFIABLE,
    CAP_TIMER_VALUE,
)
from .entity import SiriusEntity, iter_devices

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SiriusRangehoodCoordinator
    from .data import SiriusRangehoodConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SiriusRangehoodConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    entities = [SiriusRangehoodTimer(c, did, d) for c, did, d in iter_devices(entry)]
    async_add_entities(entities)


class SiriusRangehoodTimer(SiriusEntity, NumberEntity):
    """Timer duration in seconds. Disabled while the countdown is running."""

    _attr_translation_key = "timer_duration"
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.AUTO

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the timer duration entity."""
        super().__init__(coordinator, device_id, device, unique_suffix="timer")

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
