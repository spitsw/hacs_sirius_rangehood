# Copyright (c) 2026 Warren Spits
"""Runtime data shared across the Sirius Rangehood integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .api import SiriusHub, SiriusMQTT
    from .coordinator import SiriusRangehoodCoordinator


@dataclass
class SiriusRangehoodData:
    """Runtime data held on the config entry while it is loaded."""

    hub: SiriusHub
    mqtt: SiriusMQTT
    coordinator: SiriusRangehoodCoordinator
    devices: list[dict[str, Any]]


type SiriusRangehoodConfigEntry = ConfigEntry[SiriusRangehoodData]
