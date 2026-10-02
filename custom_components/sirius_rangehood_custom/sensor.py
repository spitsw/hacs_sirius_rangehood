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
from .const import DOMAIN
from .entity import SiriusEntity, sirius_device_info

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=PROP_IP_ADDRESS,
        translation_key="ip_address",
        name="IP Address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_RSSI,
        translation_key="rssi",
        name="RSSI",
        icon="mdi:wifi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_SSID,
        translation_key="ssid",
        name="SSID",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_FW_VERSION,
        translation_key="firmware_version",
        name="Firmware Version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_DEVICE_REF,
        translation_key="device_ref",
        name="Device Ref",
        icon="mdi:tag-text",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_DEVICE_TYPE,
        translation_key="device_type",
        name="Device Type",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_DEVICE_CLASS,
        translation_key="device_class",
        name="Device Class",
        icon="mdi:shape",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_FW_CODE,
        translation_key="firmware_code",
        name="Firmware Code",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=PROP_SECURE_ID,
        translation_key="secure_id",
        name="Secure ID",
        icon="mdi:shield-key",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    devices = data["devices"]

    entities = []
    for device in devices:
        did = device.get("uid", str(device["id"]))
        entities.extend(
            SiriusRangehoodSensor(coordinator, did, device, entry, desc)
            for desc in SENSOR_DESCRIPTIONS
        )
        entities.append(SiriusRangehoodFilterCountdown(coordinator, did, device, entry))
        if CAP_TIMER_ENABLE in device.get("_limits", {}):
            entities.append(
                SiriusRangehoodTimerOffTime(coordinator, did, device, entry)
            )
    async_add_entities(entities)


class SiriusRangehoodSensor(SiriusEntity, SensorEntity):
    """Generic diagnostic sensor for a Sirius device."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = sirius_device_info(device_id, device)

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
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the filter countdown sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_{CAP_FILTER_VALUE}"
        self._attr_device_info = sirius_device_info(device_id, device)

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
    _attr_device_class = "timestamp"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the timer turn-off-time sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer_off"
        self._attr_device_info = sirius_device_info(device_id, device)

    @property
    def native_value(self) -> datetime | None:
        """Return the moment the timer will turn the device off."""
        state = self._get_device_state()
        active = state.get(CAP_TIMER_ACTIVE)
        remaining = state.get(CAP_TIMER_VALUE)
        if active and remaining is not None:
            return datetime.now(UTC) + timedelta(seconds=float(remaining))
        return None
