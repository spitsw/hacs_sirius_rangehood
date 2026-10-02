# Sirius Rangehood — Cloud Protocol

> **Disclaimer**: This information was derived by observing and monitoring
> the Sirius Android application and does not represent any official
> protocol documentation.

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

The default base URL is `https://sirius.iotpga.it`.

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
        "id": 10000,
        "uid": "PGA-DEVICE001",
        "description": "Rangehood",
        "enable": true,
        "properties": [
            { "id": "property.device.ref", "value": "REF-001" },
            { "id": "property.device.type", "value": "TYPE-A12345" },
            { "id": "property.device_name", "value": "EXAMPLE RANGEHOOD MODEL" },
            { "id": "property.device_class", "value": "0" },
            { "id": "property.device.fw.code", "value": "V02" },
            { "id": "property.device.secureId", "value": "abcd1234ef" },
            { "id": "property.device.fw.version", "value": "2" },
            { "id": "property.device.network.rssi", "value": "-65" },
            { "id": "property.device.network.ssid", "value": "HomeWiFi" },
            { "id": "property.device.network.address", "value": "192.168.1.100" }
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
    "requestId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
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
    "requestId": "aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
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
`mqtts://host:port`. It is **operated by the Sirius cloud server**, not by
the rangehood. The client (Home Assistant) opens a single MQTT connection
to this cloud broker. The rangehood itself does not expose an MQTT
endpoint and is never connected to the client directly; it reports its
state to the Sirius cloud, and the cloud publishes it to the per-device
topics below.

Connections use TLS (MQTTS) with certificate verification — the
certificate chain and hostname are validated, but **expired certificates
are accepted** (the production server has a valid certificate that has
passed its expiry date). The same account email and password are used for
MQTT authentication.

### Topic Structure

The client only subscribes; it never publishes. Every message listed below
is published by the **Sirius cloud broker** on the device's behalf.

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `root/codermine/devices/{uid}/status` | Cloud → Client | Live device state |
| `root/codermine/devices/{uid}/response/{requestId}` | Cloud → Client | Command acknowledgement |

The `{uid}` is the device's `uid` field from the device list
(e.g. `PGA-DEVICE001`), not the numeric `id`.

### Status Topic

**Payload:**

```json
{
    "deviceId": "PGA-DEVICE001",
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

The Sirius cloud automatically publishes the device's full state to this
topic:
- After the device processes a `getStatus` API command
- Automatically after any state change (e.g. user pressed a button on the
  rangehood, or a `setValue` API command was processed)

### Response Topic

Acknowledgement, published by the Sirius cloud, that a command was received
and processed by the device.

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
1. Client ── HTTPS POST /users/login ──► Sirius API ── { JWT, expires }
2. Client ── HTTPS GET /devices/ ──────► Sirius API ── [{ id, uid, props, caps }]
3. Client ── HTTPS POST /devices/{id}/set_value (getStatus) ──► Sirius API
4. Device relays its state to the Sirius cloud, which publishes
   devices/{uid}/status to the client over MQTT.
```

### Command (setValue)

```
1. Client ── HTTPS POST /devices/{id}/set_value (setValue) ──► Sirius API
2. Device processes the command, then relays its new state to the Sirius
   cloud, which publishes devices/{uid}/status to the client over MQTT.
```

After sending a `setValue` command, the device relays its updated state to
the Sirius cloud, which publishes it to the MQTT status topic. No explicit
`getStatus` is needed after commands.

### Heartbeat (periodic)

Every 5 minutes the client sends `getStatus` via the API as a heartbeat.
The device relays its current state to the Sirius cloud, which pushes it
via MQTT. This ensures the client stays synchronised even if an MQTT
message was missed.

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

The API returns/sets colour temperature directly in **Kelvin**. Home
Assistant 2026.3+ uses Kelvin natively via `color_temp_kelvin` — no
conversion needed.

| Metric | Kelvin |
|--------|--------|
| Warm | 2700K |
| Cool | 6000K |