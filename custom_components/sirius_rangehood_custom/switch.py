# Copyright (c) 2026 Warren Spits
"""Switch platform for Sirius Rangehood."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity

from .api import (
    CAP_BI_POWER_ENABLED,
    CAP_POWER,
    CAP_TIMER_ACTIVE,
    CAP_TIMER_ENABLE,
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
    """Set up the switch platform."""
    data = entry.runtime_data
    coordinator = data.coordinator
    devices = data.devices

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodPowerSwitch(coordinator, did, device, entry))
        if CAP_BI_POWER_ENABLED in device.get("_limits", {}):
            entities.append(
                SiriusRangehoodBiPowerSwitch(coordinator, did, device, entry)
            )
        if CAP_TIMER_ENABLE in device.get("_limits", {}):
            entities.append(SiriusRangehoodTimerSwitch(coordinator, did, device, entry))
    async_add_entities(entities)


class SiriusRangehoodPowerSwitch(SiriusEntity, SwitchEntity):
    """Global power on/off for a Sirius device."""

    _attr_translation_key = "power"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the global power switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_power"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        """Return True when the device is powered on."""
        state = self._get_device_state()
        val = state.get(CAP_POWER)
        if val is not None:
            return bool(val)
        return None

    @property
    def icon(self) -> str:
        """Return the power icon reflecting the current state."""
        return "mdi:power" if self.is_on else "mdi:power-off"

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Power the device on."""
        await self._async_send_command([{"id": CAP_POWER, "value": 1.0}])

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Power the device off."""
        await self._async_send_command([{"id": CAP_POWER, "value": 0.0}])


class SiriusRangehoodBiPowerSwitch(SiriusEntity, SwitchEntity):
    """Enable extra airflow and powerful extraction."""

    _attr_translation_key = "bi_power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the bi-power switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_bi_power"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        """Return True when bi-power mode is enabled."""
        state = self._get_device_state()
        val = state.get(CAP_BI_POWER_ENABLED)
        if val is not None:
            return bool(val)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Enable bi-power mode."""
        await self._async_send_command([{"id": CAP_BI_POWER_ENABLED, "value": 1.0}])

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable bi-power mode."""
        await self._async_send_command([{"id": CAP_BI_POWER_ENABLED, "value": 0.0}])


class SiriusRangehoodTimerSwitch(SiriusEntity, SwitchEntity):
    """Timer on/off; starts and stops the countdown timer."""

    _attr_translation_key = "timer_active"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the timer active switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer_active"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        """Return True when the countdown timer is running."""
        state = self._get_device_state()
        val = state.get(CAP_TIMER_ACTIVE)
        if val is not None:
            return bool(val)
        return None

    @property
    def available(self) -> bool:
        """Return True when the timer can be started or stopped."""
        state = self._get_device_state()
        return bool(state.get(CAP_TIMER_ENABLE, False)) and bool(
            state.get(CAP_TIMER_VALUE, 0)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Start the countdown timer."""
        await self._async_send_command([{"id": CAP_TIMER_ACTIVE, "value": 1.0}])

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Stop the countdown timer."""
        await self._async_send_command([{"id": CAP_TIMER_ACTIVE, "value": 0.0}])
