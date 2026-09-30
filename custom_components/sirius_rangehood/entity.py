"""Shared entity base for Sirius Rangehood entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PROP_FW_VERSION
from .const import DOMAIN


def sirius_device_info(device_id: str, device: dict[str, Any]) -> DeviceInfo:
    """Build a DeviceInfo dict for a Sirius device."""
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device.get("name", f"Sirius Rangehood {device_id}"),
        manufacturer="Sirius",
        model=device.get("description", "Rangehood"),
        sw_version=device.get(PROP_FW_VERSION),
    )


class SiriusEntity(CoordinatorEntity):
    """Base class for Sirius Rangehood entities with common helpers.

    Subclasses must set ``_device_id`` and ``_entry_id`` in their
    ``__init__``.
    """

    _attr_has_entity_name = True

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state from the coordinator."""
        return self.coordinator.data.get(self._device_id, {})  # type: ignore[attr-defined]