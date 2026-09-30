"""Root conftest: register Home Assistant mocks before any imports.

This must run *before* any test file imports custom_components.sirius_rangehood,
so we register all synthetic homeassistant.* modules into sys.modules eagerly.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Register a synthetic 'homeassistant' package so the component can import
# its symbols without a full HA runtime.  Each submodule that the component
# touches gets a MagicMock that provides the needed callables.
# ---------------------------------------------------------------------------
_MOCKED_PACKAGES: set[str] = set()


def _mock_ha_module(dotted_path: str) -> MagicMock:
    """Ensure a synthetic module at *dotted_path* lives in sys.modules,
    returning it (creating it if needed).  Also creates intermediate parent
    packages."""
    parts = dotted_path.split(".")
    for i in range(1, len(parts) + 1):
        prefix = ".".join(parts[:i])
        if prefix not in _MOCKED_PACKAGES:
            mod = MagicMock()
            mod.__path__ = []
            sys.modules[prefix] = mod
            _MOCKED_PACKAGES.add(prefix)
    return sys.modules[dotted_path]


# Every HA symbol the component touches, resolved eagerly
for path in (
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.components.fan",
    "homeassistant.components.light",
    "homeassistant.components.switch",
    "homeassistant.components.sensor",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers",
):
    _mock_ha_module(path)


class _MockSensorEntity:
    """Stand-in for SensorEntity — works as a real base class."""


class _MockSwitchEntity:
    """Stand-in for SwitchEntity — works as a real base class."""


# --- Populate module attributes with the symbols that the component uses ---

ha_const = sys.modules["homeassistant.const"]
ha_const.EntityCategory = MagicMock()
ha_const.EntityCategory.DIAGNOSTIC = "diagnostic"
ha_const.CONF_USERNAME = "username"
ha_const.CONF_PASSWORD = "password"
ha_const.Platform = MagicMock()
ha_const.Platform.FAN = "fan"
ha_const.Platform.LIGHT = "light"
ha_const.Platform.SWITCH = "switch"
ha_const.Platform.SENSOR = "sensor"


class _MockCoordinatorEntity:
    """Stand-in for CoordinatorEntity — works as a real base class."""

    def __init__(self, coordinator=None):
        self.coordinator = coordinator
        self.hass = MagicMock()


class _MockFanEntity:
    """Stand-in for FanEntity — works as a real base class."""


ha_coord = sys.modules["homeassistant.helpers.update_coordinator"]
ha_coord.DataUpdateCoordinator = MagicMock
ha_coord.CoordinatorEntity = _MockCoordinatorEntity

ha_storage = sys.modules["homeassistant.helpers.storage"]
ha_storage.Store = MagicMock


class _MockLightEntity:
    """Stand-in for LightEntity — works as a real base class."""


ha_light = sys.modules["homeassistant.components.light"]
ha_light.ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
ha_light.ATTR_BRIGHTNESS = "brightness"
ha_light.ColorMode = MagicMock()
ha_light.ColorMode.COLOR_TEMP = "color_temp"
ha_light.LightEntity = _MockLightEntity

ha_fan = sys.modules["homeassistant.components.fan"]
ha_fan.FanEntity = _MockFanEntity
ha_fan.FanEntityFeature = MagicMock()
ha_fan.FanEntityFeature.SET_SPEED = 1
ha_fan.FanEntityFeature.TURN_ON = 2
ha_fan.FanEntityFeature.TURN_OFF = 4

ha_sensor = sys.modules["homeassistant.components.sensor"]
ha_sensor.SensorEntity = _MockSensorEntity
ha_sensor.SensorEntityDescription = MagicMock

ha_switch = sys.modules["homeassistant.components.switch"]
ha_switch.SwitchEntity = _MockSwitchEntity

ha_event = sys.modules["homeassistant.helpers.event"]
ha_event.async_call_later = MagicMock()
ha_event.async_track_time_interval = MagicMock()

ha_ep = sys.modules["homeassistant.helpers.entity_platform"]
ha_ep.AddEntitiesCallback = None

ha_def = sys.modules["homeassistant.data_entry_flow"]
ha_def.FlowResult = dict

ha_core = sys.modules["homeassistant.core"]
ha_core.HomeAssistant = MagicMock

# Third-party packages needed by the component
sys.modules["voluptuous"] = MagicMock()
sys.modules["voluptuous"].Schema = MagicMock
sys.modules["voluptuous"].Required = lambda x, **kw: x
sys.modules["voluptuous"].Optional = lambda x, **kw: x

sys.modules["aiohttp"] = MagicMock()

# Third-party packages needed by the component (imported at module level)
sys.modules["paho"] = MagicMock()
sys.modules["paho.mqtt"] = MagicMock()
sys.modules["paho.mqtt.client"] = MagicMock()
sys.modules["paho.mqtt.client"].Client = MagicMock
sys.modules["paho.mqtt.client"].CallbackAPIVersion = MagicMock()
sys.modules["paho.mqtt.client"].CallbackAPIVersion.VERSION1 = 1

# Add the repo root so "custom_components" is importable
sys.path.insert(0, "/home/warren/dev")
