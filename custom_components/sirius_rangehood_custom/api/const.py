"""Constants for the Sirius Rangehood API layer."""

# API endpoints
API_LOGIN = "/users/login"
API_DEVICES = "/devices/"
API_SET_VALUE = "/devices/{device_id}/set_value"

# Property IDs (from properties[]) — static configuration data
PROP_DEVICE_NAME = "property.device_name"
PROP_DEVICE_REF = "property.device.ref"
PROP_DEVICE_TYPE = "property.device.type"
PROP_DEVICE_CLASS = "property.device_class"
PROP_FW_CODE = "property.device.fw.code"
PROP_FW_VERSION = "property.device.fw.version"
PROP_SECURE_ID = "property.device.secureId"
PROP_RSSI = "property.device.network.rssi"
PROP_SSID = "property.device.network.ssid"
PROP_IP_ADDRESS = "property.device.network.address"

# Capability UIDs (from capabilities[].capabilityUid) — live operational data
CAP_POWER = "device.onOff"
CAP_FAN_SPEED = "device.fanSpeed"
CAP_BOOST_VALUE = "device.boostValue"
CAP_LIGHT_ONOFF = "device.lightOnOff"
CAP_TIMER_VALUE = "device.timerValue"
CAP_FILTER_WORN = "device.filter1.worn"
CAP_FILTER_VALUE = "device.filter1Value"
CAP_TIMER_ACTIVE = "device.timer.active"
CAP_TIMER_ENABLE = "device.timer.enable"
CAP_BI_POWER_ENABLED = "device.biPowerEnabled"
CAP_LIGHT_BRIGHTNESS = "device.lightBrightness"
CAP_TIMER_MODIFIABLE = "device.timer.modifiable"
CAP_LIGHT_COLOR_TEMP = "device.lightColorTemperature"

# Live capability keys — these MUST NOT be overwritten by periodic API polls
# (only MQTT should update these)
LIVE_CAPABILITY_KEYS = frozenset({
    CAP_POWER,
    CAP_FAN_SPEED,
    CAP_BOOST_VALUE,
    CAP_LIGHT_ONOFF,
    CAP_TIMER_VALUE,
    CAP_FILTER_WORN,
    CAP_FILTER_VALUE,
    CAP_TIMER_ACTIVE,
    CAP_TIMER_ENABLE,
    CAP_BI_POWER_ENABLED,
    CAP_LIGHT_BRIGHTNESS,
    CAP_TIMER_MODIFIABLE,
    CAP_LIGHT_COLOR_TEMP,
})

# Fan speed: API uses 0-4 (off, low, med, high, boost)
FAN_SPEED_OFF = 0
FAN_SPEED_LOW = 1
FAN_SPEED_MEDIUM = 2
FAN_SPEED_HIGH = 3
FAN_SPEED_BOOST = 4
FAN_SPEED_COUNT = 5

# Percentage mapping for 5 speeds
SPEED_TO_PERCENTAGE = {
    FAN_SPEED_OFF: 0,
    FAN_SPEED_LOW: 25,
    FAN_SPEED_MEDIUM: 50,
    FAN_SPEED_HIGH: 75,
    FAN_SPEED_BOOST: 100,
}
PERCENTAGE_TO_SPEED = {v: k for k, v in SPEED_TO_PERCENTAGE.items()}

# Light brightness: API range 10-100 percent
LIGHT_BRIGHTNESS_MIN = 10
LIGHT_BRIGHTNESS_MAX = 100

# Light colour temperature: API returns/sets Kelvin directly
LIGHT_COLOR_TEMP_KELVIN_MIN = 2700
LIGHT_COLOR_TEMP_KELVIN_MAX = 6000

# API request timeout
API_TIMEOUT = 10

# Default server endpoint
DEFAULT_SIRIUS_ENDPOINT = "https://sirius.iotpga.it"
DEFAULT_SIRIUS_MQTTS_ENDPOINT = "mqtts://sirius.iotpga.it:8884"

# Heartbeat interval — sends getStatus to trigger MQTT refresh (seconds)
GET_STATUS_INTERVAL = 300

# How often to poll /devices/ for static property changes (seconds)
DEVICES_POLL_INTERVAL = 3600