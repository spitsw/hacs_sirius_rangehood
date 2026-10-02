# Copyright (c) 2026 Warren Spits
"""Light platform for Sirius Rangehood."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,  # pyright: ignore[reportPrivateImportUsage]
    LightEntity,
)

from .api import (
    CAP_LIGHT_BRIGHTNESS,
    CAP_LIGHT_COLOR_TEMP,
    CAP_LIGHT_ONOFF,
    LIGHT_BRIGHTNESS_MAX,
    LIGHT_BRIGHTNESS_MIN,
    LIGHT_COLOR_TEMP_KELVIN_MAX,
    LIGHT_COLOR_TEMP_KELVIN_MIN,
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
    """Set up the light platform."""
    entities = [SiriusRangehoodLight(c, did, d) for c, did, d in iter_devices(entry)]
    async_add_entities(entities)


class SiriusRangehoodLight(SiriusEntity, LightEntity):
    """Representation of a Sirius Rangehood light."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.COLOR_TEMP}  # noqa: RUF012
    _attr_min_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MIN
    _attr_max_color_temp_kelvin = LIGHT_COLOR_TEMP_KELVIN_MAX

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator, device_id, device, unique_suffix="light")

    @property
    def is_on(self) -> bool | None:
        """Return True when the light is on."""
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_ONOFF)
        return bool(val) if val is not None else None

    @property
    def brightness(self) -> int | None:
        """Return the light brightness on the Home Assistant 0-255 scale."""
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
        """Return the light colour temperature in Kelvin."""
        state = self._get_device_state()
        val = state.get(CAP_LIGHT_COLOR_TEMP)
        if val is not None:
            return round(float(val))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, applying brightness and colour temperature if given."""
        params = []
        has_attr = False

        if ATTR_BRIGHTNESS in kwargs:
            has_attr = True
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            pct = LIGHT_BRIGHTNESS_MIN + (ha_brightness / 255) * (
                LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN
            )
            params.append(
                {
                    "id": CAP_LIGHT_BRIGHTNESS,
                    "value": round(
                        max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, pct)), 1
                    ),
                }
            )
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            has_attr = True
            params.append(
                {
                    "id": CAP_LIGHT_COLOR_TEMP,
                    "value": round(float(kwargs[ATTR_COLOR_TEMP_KELVIN])),
                }
            )

        # Only send onOff when no brightness/color_temp is provided
        if not has_attr:
            params.append({"id": CAP_LIGHT_ONOFF, "value": 1.0})

        if not params:
            return
        await self._async_send_command(params)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the light off."""
        await self._async_send_command([{"id": CAP_LIGHT_ONOFF, "value": 0.0}])
