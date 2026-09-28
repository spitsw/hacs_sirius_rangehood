# Sirius Rangehood — Cloud Protocol

## Overview

The Sirius cloud server exposes two communication channels for controlling and
monitoring WiFi-enabled rangehoods:

| Channel | Transport | Purpose |
|---------|-----------|---------|
| **REST API** | HTTPS | Authentication, device discovery, sending commands |
| **MQTT** | MQTTS (TLS) | Real-time device status updates, command acknowledgements |

## Authentication

### POST `/users/login`

Authenticates with the Sirius server and returns a JWT bearer token.

**Request:**

```json
{
    "email": "<account-email>",
    "password": "<account-password>"
}
```

**Response (success — HTTP 200):**

```json
{
    "JWT": "eyJhbGciOiJIUzI1NiJ9...",
    "expires": 3600
}
```

The `expires` value is the token lifetime in seconds. The token is sent as a
`Authorization: Bearer <JWT>` header on all subsequent API requests.

**Error responses** return a non-200 status with an error body.

---

## REST API

### Base URL

The base URL is user-provided (e.g. `https://api.sirius.example.com`).

### GET `/devices/`

Returns all devices registered to the authenticated account. Used for
discovery on initial setup.

**Headers:**

```
Authorization: Bearer <JWT>
```

**Response (HTTP 200):**

```json
[
    {
        "id": 11662,
        "uid": "PGA-00022667",
        "description": "Rangehood",
        "enable": true,
        "properties": [
            { "id": "property.device.ref", "value": "74870" },
            { "id": "property.device.type", "value": "05989063502" },
            { "id": "property.device_name", "value": "SL926 DL 850 T-SHAPE ARISIT" },
            { "id": "property.device_class", "value": "0" },
            { "id": "property.device.fw.code", "value": "10" },
            { "id": "property.device.secureId", "value": "1cdab1c29b" },
            { "id": "property.device.fw.version", "value": "1" },
            { "id": "property.device.network.rssi", "value": "-79" },
            { "id": "property.device.network.ssid", "value": "ASIO" },
            { "id": "property.device.network.address", "value": "10.8.0.178" }
        ],
        "capabilities": [
            { "capabilityUid": "device.onOff",            "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.fanSpeed",          "capabilityType": "0", "value": 0.0,   "minValue": 0.0,   "maxValue": 4.0 },
            { "capabilityUid": "device.boostValue",        "capabilityType": "0", "value": 300.0, "minValue": 0.0,   "maxValue": 7200.0 },
            { "capabilityUid": "device.lightOnOff",        "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.timerValue",        "capabilityType": "0", "value": 300.0, "minValue": 60.0,  "maxValue": 7200.0 },
            { "capabilityUid": "device.filter1.worn",      "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.filter1Value",      "capabilityType": "0", "value": 360000.0, "minValue": 0.0, "maxValue": 360000.0 },
            { "capabilityUid": "device.timer.active",      "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.timer.enable",      "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.biPowerEnabled",    "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.lightBrightness",   "capabilityType": "0", "value": 50.0,  "minValue": 10.0,  "maxValue": 100.0 },
            { "capabilityUid": "device.timer.modifiable",  "capabilityType": "4", "value": 0.0,   "minValue": 0.0,   "maxValue": 1.0 },
            { "capabilityUid": "device.lightColorTemperature", "capabilityType": "0", "value": 2700.0, "minValue": 2700.0, "maxValue": 6000.0 }
        ]
    }
]
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Numeric device ID (used in API paths) |
| `uid` | string | External human-readable device ID (used in MQTT topics) |
| `description` | string | Device type label |
| `enable` | bool | Whether the device is active on the server |
| `properties[]` | array | Static configuration key-value pairs |
| `capabilities[]` | array | Controllable capability definitions with ranges |

**Note:** The `value` in capability objects from this endpoint represents the
**configured / initial** value, not necessarily the live operational state.
Live values arrive via MQTT (see below).

### POST `/devices/{device_id}/set_value`

Sends a command to a device. The `device_id` is the numeric `id` from the
device list.

**Headers:**

```
Authorization: Bearer <JWT>
```

#### Command Types

**getStatus** — Request the device to publish its full status via MQTT:

```json
{
    "command": "getStatus",
    "deviceType": "smartphone",
    "parameters": [],
    "requestId": "9a41e26e-eaec-4411-aaea-579b8c78b22c"
}
```

**setValue** — Set one or more capabilities on the device:

```json
{
    "command": "setValue",
    "deviceType": "smartphone",
    "parameters": [
        { "id": "device.fanSpeed", "value": 1 }
    ],
    "requestId": "709f6b07-666e-45d8-9679-0681c91906e3"
}
```

Multiple parameters can be included in a single command:

```json
{
    "command": "setValue",
    "deviceType": "smartphone",
    "parameters": [
        { "id": "device.lightOnOff", "value": 1 },
        { "id": "device.lightBrightness", "value": 80 },
        { "id": "device.lightColorTemperature", "value": 4000 }
    ],
    "requestId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

The `requestId` must be a UUIDv4 generated by the client. The `deviceType`
should be `"smartphone"`.

**Response (HTTP 200):**

Returns the API acknowledgement (exact body depends on server).

#### Capability Reference

| Capability UID | Type | Range | Description |
|---------------|------|-------|-------------|
| `device.onOff` | 4 (bool) | 0–1 | Global power (fan + light) |
| `device.fanSpeed` | 0 (int) | 0–4 | Fan speed: 0=off, 1=low, 2=med, 3=high, 4=boost |
| `device.boostValue` | 0 (int) | 0–7200 | Boost timer duration in seconds |
| `device.lightOnOff` | 4 (bool) | 0–1 | Light on/off |
| `device.lightBrightness` | 0 (int) | 10–100 | Light brightness percent |
| `device.lightColorTemperature` | 0 (int) | 2700–6000 | Light colour temperature in Kelvin |
| `device.timerValue` | 0 (int) | 60–7200 | Timer duration in seconds |
| `device.timer.active` | 4 (bool) | 0–1 | Timer currently active |
| `device.timer.enable` | 4 (bool) | 0–1 | Timer enabled |
| `device.timer.modifiable` | 4 (bool) | 0–1 | Timer can be modified |
| `device.filter1.worn` | 4 (bool) | 0–1 | Filter worn indicator |
| `device.filter1Value` | 0 (int) | 0–360000 | Filter remaining life in units |
| `device.biPowerEnabled` | 4 (bool) | 0–1 | Bi-power mode enabled |

Capability type `4` is boolean (0/1). Type `0` is a continuous or discrete
integer.

---

## MQTT

The MQTT broker is a separate endpoint from the REST API, provided as
`mqtts://host:port`. Connections use TLS (MQTTS) with certificate
verification (`ssl.CERT_REQUIRED`). The same account email and password
are used for MQTT authentication.

### Topic Structure

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `root/codermine/devices/{uid}/status` | Device → Client | Live device state |
| `root/codermine/devices/{uid}/response/{requestId}` | Device → Client | Command acknowledgement |

The `{uid}` is the device's `uid` field from the device list
(e.g. `PGA-00022667`), not the numeric `id`.

### Status Topic

**Payload:**

```json
{
    "deviceId": "PGA-00022667",
    "values": [
        { "id": "device.onOff", "value": 0 },
        { "id": "device.biPowerEnabled", "value": 1 },
        { "id": "device.fanSpeed", "value": 0 },
        { "id": "device.lightOnOff", "value": 0 },
        { "id": "device.lightBrightness", "value": 100 },
        { "id": "device.lightColorTemperature", "value": 3294 },
        { "id": "device.timer.enable", "value": 0 },
        { "id": "device.timer.active", "value": 0 },
        { "id": "device.timer.modifiable", "value": 0 },
        { "id": "device.timerValue", "value": 0 },
        { "id": "device.boostValue", "value": 0 },
        { "id": "device.filter1.worn", "value": 0 },
        { "id": "device.filter1Value", "value": 101340 }
    ],
    "timestamp": "2026-09-28T13:37:23"
}
```

The device automatically publishes its full state to this topic:
- After receiving a `getStatus` API command
- Automatically after any state change (e.g. user pressed a button on the
  rangehood, or a `setValue` API command was processed)

### Response Topic

Acknowledgement that a command was received and processed by the device.

**Topic pattern:**

```
root/codermine/devices/{uid}/response/{requestId}
```

The `{requestId}` matches the `requestId` sent in the API command.

**Payload:**

```json
{
    "timestamp": "2026-09-28T13:43:57",
    "status": 0
}
```

`status: 0` indicates success. Non-zero indicates an error.

---

## Data Sources Summary

| Data | Source | Nature | Update Frequency |
|------|--------|--------|-----------------|
| Device metadata (ref, type, class, fw.code, secureId) | `GET /devices/` | Static | Hourly poll (changes rare) |
| Capability ranges (min/max) | `GET /devices/` | Static | Hourly poll |
| Capability configured/initial values | `GET /devices/` | Semi-static | Hourly poll |
| Live capability values | MQTT status topic | Dynamic | Real-time push |
| Network diagnostics (IP, RSSI, SSID) | `GET /devices/` properties | Semi-static | Hourly poll |
| Firmware version | `GET /devices/` properties | Static | Hourly poll |

---

## Interaction Flows

### Startup

```
Client                    Sirius API                   Device (MQTT)
  │                          │                            │
  │──── POST /users/login ───│                            │
  │◄──── { JWT, expires } ───│                            │
  │                          │                            │
  │──── GET /devices/ ───────│                            │
  │◄── [{ id, uid, props, caps }] ────────               │
  │                          │                            │
  │──── POST /devices/{id}/set_value ── getStatus ────────│
  │                          │                            │
  │                          │    MQTT: response/{reqId}  │
  │                          │◄──── {"status": 0} ──────  │
  │                          │                            │
  │                          │    MQTT: status            │
  │                          │◄── {deviceId, values[]} ───│
```

### Command (setValue)

```
Client                    Sirius API                   Device (MQTT)
  │                          │                            │
  │──── POST /devices/{id}/set_value ── setValue ─────────│
  │                          │                            │
  │                          │    MQTT: response/{reqId}  │
  │                          │◄──── {"status": 0} ──────  │
  │                          │                            │
  │                          │    MQTT: status (automatic)│
  │                          │◄── {deviceId, values[]} ───│
```

After sending a `setValue` command, the device automatically publishes its
updated state to the MQTT status topic. No explicit `getStatus` is needed
after commands.

### Heartbeat (periodic)

Every 5 minutes the client sends `getStatus` via the API as a heartbeat.
The device responds by pushing its current state via MQTT. This ensures
the client stays synchronised even if an MQTT message was missed.

---

## Fan Speed Mapping

The API uses integer speed values 0–4. When translating to a percentage
interface (0–100):

| API Speed | Label | Percentage |
|-----------|-------|------------|
| 0 | Off | 0% |
| 1 | Low | 25% |
| 2 | Medium | 50% |
| 3 | High | 75% |
| 4 | Boost | 100% |

## Light Brightness

The API uses a percentage range of 10–100. When translating to the Home
Assistant brightness scale (0–255):

```
ha_brightness = (api_value - 10) / (100 - 10) × 255
```

## Light Colour Temperature

The API returns/sets colour temperature in **Kelvin**. When translating to
mireds (the Home Assistant convention):

```
mireds = 1,000,000 / kelvin
```

| Metric | Kelvin | Mireds |
|--------|--------|--------|
| Warm | 2700K | 370 mireds |
| Cool | 6000K | 166 mireds |