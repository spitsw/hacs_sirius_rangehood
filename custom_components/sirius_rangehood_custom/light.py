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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    CAP_LIGHT_BRIGHTNESS,
    CAP_LIGHT_COLOR_TEMP,
    CAP_LIGHT_ONOFF,
    LIGHT_BRIGHTNESS_MAX,
    LIGHT_BRIGHTNESS_MIN,
    LIGHT_COLOR_TEMP_KELVIN_MAX,
    LIGHT_COLOR_TEMP_KELVIN_MIN,
)
from .const import DOMAIN
from .entity import SiriusEntity, sirius_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.append(SiriusRangehoodLight(coordinator, did, device, entry))
    async_add_entities(entities)


class SiriusRangehoodLight(SiriusEntity, LightEntity):
    """Representation of a Sirius Rangehood light."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = frozenset({ColorMode.COLOR_TEMP})
    _attr_min_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MIN
    _attr_max_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MAX

    def __init__(
        self, coordinator, device_id: str, device: dict[str, Any], entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_light"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def is_on(self) -> bool | None:
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_ONOFF)
        return bool(val) if val is not None else None

    @property
    def brightness(self) -> int | None:
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_BRIGHTNESS)
        if val is not None:
            pct = float(val)
            pct = max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, pct))
            normalized = (pct - LIGHT_BRIGHTNESS_MIN) / (LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN)
            return round(normalized * 255)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_COLOR_TEMP)
        if val is not None:
            return round(float(val))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        params = []
        has_attr = False

        if ATTR_BRIGHTNESS in kwargs:
            has_attr = True
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            pct = LIGHT_BRIGHTNESS_MIN + (ha_brightness / 255) * (LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN)
            params.append({"id": CAP_LIGHT_BRIGHTNESS, "value": round(max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, pct)), 1)})
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            has_attr = True
            params.append({"id": CAP_LIGHT_COLOR_TEMP, "value": round(float(kwargs[ATTR_COLOR_TEMP_KELVIN]))})

        # Only send onOff when no brightness/color_temp is provided
        if not has_attr:
            params.append({"id": CAP_LIGHT_ONOFF, "value": 1.0})

        if not params:
            return
        await self._async_send_command(params)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_command([{"id": CAP_LIGHT_ONOFF, "value": 0.0}])