"""Shared entity base for Sirius Rangehood entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PROP_DEVICE_NAME, PROP_FW_CODE, PROP_FW_VERSION, SiriusAuthError
from .const import DOMAIN


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


class SiriusEntity(CoordinatorEntity):
    """Base class for Sirius Rangehood entities."""

    _attr_has_entity_name = True

    def _get_device_state(self) -> dict[str, Any]:
        """Return latest device state from the coordinator."""
        return self.coordinator.data.get(self._device_id, {})  # type: ignore[attr-defined]

    async def _async_send_command(self, params: list[dict[str, Any]]) -> None:
        """Send a setValue command via the hub."""
        data = self.hass.data[DOMAIN][self._entry_id]  # type: ignore[attr-defined]
        hub = data["hub"]
        try:
            await hub.async_send_command(self._device_id, params)  # type: ignore[attr-defined]
        except SiriusAuthError:
            data.get("reauth", lambda: None)()

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return diagnostic attributes."""
        return {"device_uid": self._device_id} if hasattr(self, "_device_id") else None  # type: ignore[attr-defined]
