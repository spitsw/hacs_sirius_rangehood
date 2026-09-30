"""Light platform for Sirius Rangehood."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    CAP_LIGHT_BRIGHTNESS,
    CAP_LIGHT_COLOR_TEMP,
    CAP_LIGHT_ONOFF,
    LIGHT_BRIGHTNESS_MAX,
    LIGHT_BRIGHTNESS_MIN,
    LIGHT_COLOR_TEMP_KELVIN_MAX,
    LIGHT_COLOR_TEMP_KELVIN_MIN,
    PROP_FW_VERSION,
)
from .api import SiriusAuthError
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the light platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodLight(coordinator, did, device, entry))

    async_add_entities(entities)


class SiriusRangehoodLight(CoordinatorEntity, LightEntity):
    """Representation of a Sirius Rangehood light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MIN
    _attr_max_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MAX

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_light"
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.get("name", f"Sirius Rangehood {device_id}"),
            manufacturer="Sirius",
            model=device.get("description", "Rangehood"),
            sw_version=device.get(PROP_FW_VERSION),
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def is_on(self) -> bool | None:
        """Return if light is on."""
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_ONOFF)
        return bool(val) if val is not None else None

    @property
    def brightness(self) -> int | None:
        """Return brightness (0-255)."""
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_BRIGHTNESS)
        if val is not None:
            pct = float(val)
            pct = max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, pct))
            normalized = (pct - LIGHT_BRIGHTNESS_MIN) / (
                LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN
            )
            return round(normalized * 255)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return colour temperature in Kelvin."""
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_COLOR_TEMP)
        if val is not None:
            return round(float(val))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        params = [{"id": CAP_LIGHT_ONOFF, "value": 1.0}]

        if ATTR_BRIGHTNESS in kwargs:
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            pct = LIGHT_BRIGHTNESS_MIN + (ha_brightness / 255) * (
                LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN
            )
            params.append(
                {
                    "id": CAP_LIGHT_BRIGHTNESS,
                    "value": round(max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, pct)), 1),
                }
            )

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            params.append(
                {"id": CAP_LIGHT_COLOR_TEMP, "value": round(float(kelvin))}
            )

        await self._async_send_command(params)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._async_send_command([{"id": CAP_LIGHT_ONOFF, "value": 0.0}])

    async def _async_send_command(self, params: list[dict[str, Any]]) -> None:
        """Send a setValue command via the hub."""
        data = self.hass.data[DOMAIN][self._entry_id]
        hub = data["hub"]
        try:
            await hub.async_send_command(self._device_id, params)
        except SiriusAuthError:
            data.get("reauth", lambda: None)()