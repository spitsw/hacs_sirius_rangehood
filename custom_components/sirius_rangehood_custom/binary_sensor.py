# Copyright (c) 2026 Warren Spits
"""Binary sensor platform for Sirius Rangehood filter status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .api import CAP_FILTER_WORN
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
    """Set up the binary sensor platform."""
    entities = [
        SiriusRangehoodFilterWorn(c, did, d) for c, did, d in iter_devices(entry)
    ]
    async_add_entities(entities)


class SiriusRangehoodFilterWorn(SiriusEntity, BinarySensorEntity):
    """Filter worn indicator; on when the filter needs cleaning."""

    _attr_translation_key = "filter_worn"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: SiriusRangehoodCoordinator,
        device_id: str,
        device: dict[str, Any],
    ) -> None:
        """Initialize the filter-worn binary sensor."""
        super().__init__(coordinator, device_id, device, unique_suffix="filter_worn")

    @property
    def is_on(self) -> bool | None:
        """Return True when the filter needs cleaning."""
        state = self._get_device_state()
        val = state.get(CAP_FILTER_WORN)
        if val is not None:
            return bool(val)
        return None

    @property
    def icon(self) -> str:
        """Return the filter icon reflecting the current state."""
        return "mdi:air-filter-alert" if self.is_on else "mdi:air-filter"
