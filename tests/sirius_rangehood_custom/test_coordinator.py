"""Tests for the Sirius Rangehood coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sirius_rangehood_custom.coordinator import (
    SiriusRangehoodCoordinator,
)


@pytest.fixture
def fake_hub() -> MagicMock:
    """Return a hub mock whose heartbeat requests always succeed."""
    hub = MagicMock()
    hub.async_get_status = AsyncMock(return_value=True)
    return hub


@pytest.fixture
def fake_entry() -> MagicMock:
    """Return a minimal config-entry stand-in."""
    entry = MagicMock()
    entry.entry_id = "test-entry"
    return entry


async def test_apply_mqtt_update_merges_state(hass, fake_hub, fake_entry) -> None:
    """apply_mqtt_update should merge the payload into the coordinator data."""
    coordinator = SiriusRangehoodCoordinator(
        hass, fake_entry, fake_hub, {"dev1": {"device.onOff": 0}}
    )

    coordinator.apply_mqtt_update("dev1", {"device.onOff": 1})

    assert coordinator.data == {"dev1": {"device.onOff": 1}}


async def test_apply_mqtt_update_ignores_unknown_device(
    hass, fake_hub, fake_entry
) -> None:
    """Updates for unknown devices must be ignored entirely (no dispatch)."""
    coordinator = SiriusRangehoodCoordinator(hass, fake_entry, fake_hub, {"dev1": {}})

    coordinator.apply_mqtt_update("other", {"device.onOff": 1})

    assert coordinator.data is None


async def test_mqtt_availability_uses_grace(hass, fake_hub, fake_entry) -> None:
    """Entities stay available within the grace window, then go unavailable."""
    coordinator = SiriusRangehoodCoordinator(hass, fake_entry, fake_hub, {})
    assert coordinator.mqtt_available is True

    coordinator.set_mqtt_connected(False)
    assert coordinator.mqtt_connected is False
    assert coordinator.mqtt_available is True  # still within the grace period

    # Pretend the grace period elapsed.
    coordinator._mqtt_down_since -= timedelta(seconds=60)
    assert coordinator.mqtt_available is False

    coordinator.set_mqtt_connected(True)
    assert coordinator.mqtt_available is True

    await coordinator.async_shutdown()
