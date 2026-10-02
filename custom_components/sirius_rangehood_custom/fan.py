# Copyright (c) 2026 Warren Spits
"""Fan platform for Sirius Rangehood."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .api import (
    CAP_FAN_SPEED,
    FAN_SPEED_COUNT,
    FAN_SPEED_LOW,
    FAN_SPEED_OFF,
    PERCENTAGE_TO_SPEED,
    SPEED_TO_PERCENTAGE,
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
    """Set up the fan platform."""
    entities = [SiriusRangehoodFan(c, did, d) for c, did, d in iter_devices(entry)]
    async_add_entities(entities)


class SiriusRangehoodFan(SiriusEntity, FanEntity):
    """Representation of a Sirius Rangehood fan (speeds 0-4)."""

    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = FAN_SPEED_COUNT

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator, device_id, device, unique_suffix="fan")

    @property
    def is_on(self) -> bool | None:
        """Return True when the fan is running (speed greater than 0)."""
        state = self._get_device_state()
        speed = state.get(CAP_FAN_SPEED, FAN_SPEED_OFF)
        return isinstance(speed, (int, float)) and speed > 0

    @property
    def percentage(self) -> int | None:
        """Return the current fan speed as a percentage."""
        state = self._get_device_state()
        speed = state.get(CAP_FAN_SPEED, FAN_SPEED_OFF)
        if isinstance(speed, (int, float)):
            return SPEED_TO_PERCENTAGE.get(int(speed), 0)
        return None

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed from a percentage (nearest of 0/25/50/75/100)."""
        speed = min(PERCENTAGE_TO_SPEED.items(), key=lambda x: abs(x[0] - percentage))[
            1
        ]
        await self._async_send_command([{"id": CAP_FAN_SPEED, "value": speed}])

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Turn the fan on, optionally at a given percentage."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._async_send_command(
                [{"id": CAP_FAN_SPEED, "value": FAN_SPEED_LOW}]
            )

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the fan off."""
        await self._async_send_command([{"id": CAP_FAN_SPEED, "value": FAN_SPEED_OFF}])
