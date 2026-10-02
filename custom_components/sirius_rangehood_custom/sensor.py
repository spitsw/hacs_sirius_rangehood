# Copyright (c) 2026 Warren Spits
"""Sensor platform for Sirius Rangehood diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .api import (
    CAP_FILTER_VALUE,
    CAP_TIMER_ACTIVE,
    CAP_TIMER_ENABLE,
    CAP_TIMER_VALUE,
    PROP_DEVICE_CLASS,
    PROP_DEVICE_REF,
    PROP_DEVICE_TYPE,
    PROP_FW_CODE,
    PROP_FW_VERSION,
    PROP_IP_ADDRESS,
    PROP_RSSI,
    PROP_SECURE_ID,
    PROP_SSID,
)
from .entity import SiriusEntity, iter_devices

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SiriusRangehoodCoordinator
    from .data import SiriusRangehoodConfigEntry

_DIAGNOSTIC_SENSORS: tuple[
    tuple[str, str, str, SensorDeviceClass | None, str | None], ...
] = (
    (PROP_IP_ADDRESS, "ip_address", "mdi:ip-network", None, None),
    (PROP_RSSI, "rssi", "mdi:wifi", SensorDeviceClass.SIGNAL_STRENGTH, "dBm"),
    (PROP_SSID, "ssid", "mdi:wifi-settings", None, None),
    (PROP_FW_VERSION, "firmware_version", "mdi:chip", None, None),
    (PROP_DEVICE_REF, "device_ref", "mdi:tag-text", None, None),
    (PROP_DEVICE_TYPE, "device_type", "mdi:chip", None, None),
    (PROP_DEVICE_CLASS, "device_class", "mdi:shape", None, None),
    (PROP_FW_CODE, "firmware_code", "mdi:counter", None, None),
    (PROP_SECURE_ID, "secure_id", "mdi:shield-key", None, None),
)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = tuple(
    SensorEntityDescription(
        key=key,
        translation_key=translation_key,
        icon=icon,
        device_class=device_class,
        native_unit_of_measurement=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    for key, translation_key, icon, device_class, unit in _DIAGNOSTIC_SENSORS
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SiriusRangehoodConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    entities = []
    for coordinator, did, device in iter_devices(entry):
        entities.extend(
            SiriusRangehoodSensor(coordinator, did, device, desc)
            for desc in SENSOR_DESCRIPTIONS
        )
        entities.append(SiriusRangehoodFilterCountdown(coordinator, did, device))
        if CAP_TIMER_ENABLE in device.get("_limits", {}):
            entities.append(SiriusRangehoodTimerOffTime(coordinator, did, device))
    async_add_entities(entities)


class SiriusRangehoodSensor(SiriusEntity, SensorEntity):
    """Generic diagnostic sensor for a Sirius device."""

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator, device_id, device, unique_suffix=description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the raw device value for the described key."""
        return self._get_device_state().get(self.entity_description.key)


class SiriusRangehoodFilterCountdown(SiriusEntity, SensorEntity):
    """Filter clean countdown displayed in hours (API returns seconds)."""

    _attr_translation_key = "filter_clean_countdown"
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:air-filter"

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the filter countdown sensor."""
        super().__init__(coordinator, device_id, device, unique_suffix=CAP_FILTER_VALUE)

    @property
    def native_value(self) -> float | None:
        """Return the remaining filter life in hours."""
        state = self._get_device_state()
        val = state.get(CAP_FILTER_VALUE)
        if val is not None:
            return round(float(val) / 3600, 1)
        return None


class SiriusRangehoodTimerOffTime(SiriusEntity, SensorEntity):
    """Turn-off time for the countdown timer (timestamp for live countdown)."""

    _attr_translation_key = "timer_off_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the timer turn-off-time sensor."""
        super().__init__(coordinator, device_id, device, unique_suffix="timer_off")

    @property
    def native_value(self) -> datetime | None:
        """Return the moment the timer will turn the device off."""
        state = self._get_device_state()
        active = state.get(CAP_TIMER_ACTIVE)
        remaining = state.get(CAP_TIMER_VALUE)
        if active and remaining is not None:
            return datetime.now(UTC) + timedelta(seconds=float(remaining))
        return None
