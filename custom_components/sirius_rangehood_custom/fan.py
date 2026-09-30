"""Fan platform for Sirius Rangehood."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    CAP_FAN_SPEED,
    FAN_SPEED_COUNT,
    FAN_SPEED_LOW,
    FAN_SPEED_OFF,
    PERCENTAGE_TO_SPEED,
    SPEED_TO_PERCENTAGE,
    SiriusAuthError,
)
from .const import DOMAIN
from .entity import SiriusEntity, sirius_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodFan(coordinator, did, device, entry))
    async_add_entities(entities)


class SiriusRangehoodFan(SiriusEntity, FanEntity):
    """Representation of a Sirius Rangehood fan (speeds 0-4)."""

    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = FAN_SPEED_COUNT

    def __init__(
        self, coordinator, device_id: str, device: dict[str, Any], entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_fan"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        state = self._get_device_state()
        speed = state.get(CAP_FAN_SPEED, FAN_SPEED_OFF)
        return isinstance(speed, (int, float)) and speed > 0

    @property
    def percentage(self) -> int | None:
        state = self._get_device_state()
        speed = state.get(CAP_FAN_SPEED, FAN_SPEED_OFF)
        if isinstance(speed, (int, float)):
            return SPEED_TO_PERCENTAGE.get(int(speed), 0)
        return None

    async def async_set_percentage(self, percentage: int) -> None:
        speed = min(PERCENTAGE_TO_SPEED.items(), key=lambda x: abs(x[0] - percentage))[1]
        await self._async_send_command(CAP_FAN_SPEED, speed)

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._async_send_command(CAP_FAN_SPEED, FAN_SPEED_LOW)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_command(CAP_FAN_SPEED, FAN_SPEED_OFF)

    async def _async_send_command(self, capability_id: str, value: float) -> None:
        data = self.hass.data[DOMAIN][self._entry_id]
        hub = data["hub"]
        try:
            await hub.async_send_command(self._device_id, [{"id": capability_id, "value": value}])
        except SiriusAuthError:
            data.get("reauth", lambda: None)()