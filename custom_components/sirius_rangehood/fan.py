"""Fan platform for Sirius Rangehood."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_FAN_SPEED,
    ATTR_FIRMWARE_VERSION,
    DOMAIN,
    FAN_SPEED_COUNT,
    FAN_SPEED_LOW,
    FAN_SPEED_OFF,
    PERCENTAGE_TO_SPEED,
    SPEED_TO_PERCENTAGE,
)

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
        entities.append(SiriusRangehoodFan(coordinator, device["id"], device, entry))

    async_add_entities(entities)


class SiriusRangehoodFan(CoordinatorEntity, FanEntity):
    """Representation of a Sirius Rangehood fan (speeds 0-4: off, low, med, high, boost)."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = FAN_SPEED_COUNT

    def __init__(
        self,
        coordinator,
        device_id: int,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the fan."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_fan"
        self._attr_name = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device.get("name", f"Sirius Rangehood {device_id}"),
            "manufacturer": "Sirius",
            "model": device.get("description", "Rangehood"),
            "sw_version": device.get(ATTR_FIRMWARE_VERSION),
        }

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state from coordinator."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        """Return if fan is on."""
        state = self._get_device_state()
        speed = state.get(ATTR_FAN_SPEED, FAN_SPEED_OFF)
        return isinstance(speed, (int, float)) and speed > 0

    @property
    def percentage(self) -> int | None:
        """Return current speed percentage."""
        state = self._get_device_state()
        speed = state.get(ATTR_FAN_SPEED, FAN_SPEED_OFF)
        if isinstance(speed, (int, float)):
            return SPEED_TO_PERCENTAGE.get(int(speed), 0)
        return None

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed percentage."""
        speed = min(PERCENTAGE_TO_SPEED.items(), key=lambda x: abs(x[0] - percentage))[1]
        await self._async_send_command(ATTR_FAN_SPEED, speed)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on."""
        if percentage:
            await self.async_set_percentage(percentage)
        else:
            await self._async_send_command(ATTR_FAN_SPEED, FAN_SPEED_LOW)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        await self._async_send_command(ATTR_FAN_SPEED, FAN_SPEED_OFF)

    async def _async_send_command(self, capability_id: str, value: int | float) -> None:
        """Send a setValue command for a single capability."""
        data = self.hass.data[DOMAIN][self._entry_id]
        hub = data["hub"]
        await hub.async_send_command(
            self._device_id, [{"id": capability_id, "value": value}],
        )