"""Switch platform for Sirius Rangehood global power."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CAP_POWER
from .api import SiriusAuthError
from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodPowerSwitch(coordinator, did, device, entry))

    async_add_entities(entities)


class SiriusRangehoodPowerSwitch(CoordinatorEntity, SwitchEntity):
    """Global power on/off for a Sirius device — controls both fan and light."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the power switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_power"
        self._attr_name = "Global Power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        """Return if the device is powered on."""
        state = self._get_device_state()
        val = state.get(CAP_POWER)
        if val is not None:
            return bool(val)
        return None

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:power" if self.is_on else "mdi:power-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await self._async_send_command([{"id": CAP_POWER, "value": 1.0}])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self._async_send_command([{"id": CAP_POWER, "value": 0.0}])

    async def _async_send_command(self, params: list[dict[str, Any]]) -> None:
        """Send a setValue command via the hub."""
        data = self.hass.data[DOMAIN][self._entry_id]
        hub = data["hub"]
        try:
            await hub.async_send_command(self._device_id, params)
        except SiriusAuthError:
            data.get("reauth", lambda: None)()