"""Sensor platform for Sirius Rangehood diagnostics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    CAP_BOOST_VALUE,
    CAP_FILTER_VALUE,
    CAP_FILTER_WORN,
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

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # -- Diagnostics from MQTT / live data --
    SensorEntityDescription(
        key=CAP_FILTER_VALUE,
        translation_key="filter_clean_countdown",
        name="Filter Clean Countdown",
        icon="mdi:air-filter",
    ),
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
        key=CAP_FILTER_WORN,
        translation_key="filter_worn",
        name="Filter Worn",
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=CAP_BOOST_VALUE,
        translation_key="boost_value",
        name="Boost Duration",
        icon="mdi:clock-fast",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=CAP_TIMER_VALUE,
        translation_key="timer_value",
        name="Timer Duration",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # -- Diagnostics from /devices/ endpoint (static / configured values) --
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
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                SiriusRangehoodSensor(
                    coordinator, did, device, entry, description
                )
            )

        if CAP_TIMER_ENABLE in device.get("_limits", {}):
            entities.append(
                SiriusRangehoodTimerOffTime(coordinator, did, device, entry)
            )

    async_add_entities(entities)


class SiriusRangehoodSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sirius Rangehood diagnostic sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        state = self._get_device_state()
        return state.get(self.entity_description.key)


class SiriusRangehoodTimerOffTime(CoordinatorEntity, SensorEntity):
    """Calculated turn-off time for the timer.

    Shows the absolute time when the rangehood will auto-shutoff.
    Dashboards render this as a live countdown automatically.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "timer_off_time"
    _attr_device_class = "timestamp"

    def __init__(
        self,
        coordinator,
        device_id: str,
        device: dict[str, Any],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the turn-off time sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{device_id}_timer_off"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def native_value(self) -> datetime | None:
        """Return the calculated turn-off time as a UTC timestamp."""
        state = self._get_device_state()
        active = state.get(CAP_TIMER_ACTIVE)
        remaining = state.get(CAP_TIMER_VALUE)
        if active and remaining is not None:
            return datetime.now(timezone.utc) + timedelta(seconds=float(remaining))
        return None