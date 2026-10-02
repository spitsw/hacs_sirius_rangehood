# Copyright (c) 2026 Warren Spits
"""Shared entity base for Sirius Rangehood entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PROP_DEVICE_NAME, PROP_FW_CODE, PROP_FW_VERSION, SiriusAuthError
from .const import DOMAIN
from .coordinator import SiriusRangehoodCoordinator

_LOGGER = logging.getLogger(__name__)


def sirius_device_info(device_id: str, device: dict[str, Any]) -> DeviceInfo:
    """Build a DeviceInfo dict for a Sirius device."""
    model = device.get(PROP_DEVICE_NAME) or device.get("description") or "Rangehood"
    fw_version = device.get(PROP_FW_VERSION)
    fw_code = device.get(PROP_FW_CODE)
    if fw_version and fw_code:
        sw_version = f"{fw_version} ({fw_code})"
    elif fw_version:
        sw_version = str(fw_version)
    else:
        sw_version = None
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device.get("name", f"Sirius Rangehood {device_id}"),
        manufacturer="Sirius",
        model=model,
        sw_version=sw_version,
    )


class SiriusEntity(CoordinatorEntity[SiriusRangehoodCoordinator]):
    """Base class for Sirius Rangehood entities."""

    _attr_has_entity_name = True

    _device_id: str

    @property
    def available(self) -> bool:
        """Return True when the coordinator is healthy and MQTT is usable."""
        return super().available and self.coordinator.mqtt_available

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state from the coordinator."""
        return self.coordinator.data.get(self._device_id, {})

    async def _async_send_command(self, params: list[dict[str, Any]]) -> None:
        """Send a setValue command via the hub."""
        try:
            accepted = await self.coordinator.hub.async_send_command(
                self._device_id, params
            )
        except SiriusAuthError:
            self.coordinator.request_reauth()
            return
        if not accepted:
            _LOGGER.warning(
                "Command not acknowledged for %s; the device may still apply it",
                self._device_id,
            )

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return diagnostic attributes."""
        return {"device_uid": self._device_id} if hasattr(self, "_device_id") else None
