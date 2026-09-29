# Sirius Rangehood

Home Assistant custom component for WiFi-enabled Sirius rangehoods (cappa,
falmec, and other brands using the Sirius IoT platform).

Connects to the Sirius cloud server via:

- **HTTPS REST API** — authentication, device discovery, command execution
- **MQTTS** — real-time status updates via a persistent TLS connection

## Features

| Platform | Description |
|----------|-------------|
| **Fan** | 5 speeds (off / low / med / high / boost) with percentage control |
| **Light** | Brightness (10–100%) and colour temperature (2700K–6000K) |
| **Switch** | Global on/off for both fan and light |
| **Sensor** | IP address, RSSI, SSID, firmware version, filter countdown, filter worn, boost/timer duration, device metadata |

## Installation

### HACS (recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. Add this repository as a custom repository in HACS:
   - **URL**: `https://github.com/yourusername/sirius_rangehood`
   - **Category**: Integration
3. Search for "Sirius Rangehood" in HACS and install.
4. Restart Home Assistant.

### Manual

1. Copy the `custom_components/sirius_rangehood/` directory into your
   Home Assistant `custom_components/` directory.
2. Restart Home Assistant.

## Configuration

### UI (Config Flow)

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for "Sirius Rangehood".
3. Enter:

   | Field | Default | Description |
   |-------|---------|-------------|
   | Sirius HTTPS Endpoint | `https://sirius.iotpga.it` | Sirius REST API base URL |
   | Sirius MQTTS Endpoint | `mqtts://sirius.iotpga.it:8884` | MQTT broker URL (TLS) |
   | Email | — | Your Sirius cloud account email |
   | Password | — | Your Sirius cloud account password |

4. Login is validated before the entry is created.
5. Discovered devices appear as entities automatically.

### Re-authentication

If the Sirius token expires or is rejected, a reauth flow is triggered
automatically. You will be prompted to update credentials.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  Config Entry                     │
├──────────┬───────────────────────────────────────┤
│  hub.py  │ HTTP API client                       │
│          │  • POST /users/login (JWT auth)        │
│          │  • GET  /devices/  (device discovery)  │
│          │  • POST /{id}/set_value (commands)     │
│          │  • Token refresh before expiry          │
├──────────┼───────────────────────────────────────┤
│ mqtt.py  │ MQTTS client (direct paho-mqtt)       │
│          │  • TLS with expired-cert tolerance     │
│          │  • Subscribes device/status + response │
│          │  • Parses {values: [{id, value}]}     │
│          │  • Thread-safe bridge → HA event loop  │
├──────────┼───────────────────────────────────────┤
│ init.py  │ Coordinator + lifecycle                │
│          │  • DataUpdateCoordinator (300s poll)   │
│          │  • MQTT push updates merged via bridge │
│          │  • /devices/ poll (3600s) for new devs │
│          │  • Auto-reload on new device discovery │
├──────────┼───────────────────────────────────────┤
│ Entities │ fan.py, light.py, switch.py, sensor.py │
│          │  • CoordinatorEntity pattern           │
│          │  • Reauth on SiriusAuthError           │
└──────────┴───────────────────────────────────────┘
```

### Thread Safety

MQTT messages arrive on a paho background thread. All state mutations are
bridged to the HA event loop via `hass.loop.call_soon_threadsafe()` before
touching `coordinator.data` or calling `async_set_updated_data()`.

### Fan Model

- Speed 0 = off; speed 1–4 = low / medium / high / boost
- HA percentage: 0% → off, 25/50/75/100% → low/med/high/boost
- `async_set_percentage` nearest-matches to the closest speed
- `speed_count = 5` (0–4) — HA's built-in speed slider

### Light Model

- Kelvin-based colour temperature (2700K warm → 6000K cool)
- Brightness range 10–100% mapped to HA's 0–255 scale
- `ColorMode.COLOR_TEMP` — no RGB support

### Certificate Tolerance

The Sirius MQTTS broker presents a valid certificate that has expired. The
component creates a custom SSL context that **only** skips the expiry
check — all other validation (chain of trust, hostname) still applies. See
`mqtt.py:_create_ssl_context()`.

## Topics

MQTT subscription topics (auto-subscribed per device):

```
root/codermine/devices/{device_id}/status
root/codermine/devices/{device_id}/response/#
```

QoS 1. Payload format:

```json
{
  "deviceId": "...",
  "values": [
    {"id": "device.onOff", "value": 1.0},
    {"id": "device.fanSpeed", "value": 3}
  ]
}
```

## Services

No custom services are defined — use standard `fan.*`, `light.*`, and
`switch.*` services from Home Assistant.

## Troubleshooting

| Symptom | Likely Cause |
|---------|-------------|
| "Invalid authentication" | Check credentials in Sirius mobile app first |
| "No devices found" | Login succeeded but no rangehood is linked to the account |
| Entity states don't update | MQTT may be disconnected; check HA logs for MQTT errors |
| Reauth triggered | JWT expired; credentials should auto-refresh |
| Certificate errors | If the Sirius server certificate changes, the custom TLS context in `mqtt.py` may need updating |

Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.sirius_rangehood: debug
```

## Development

### Requirements

- Home Assistant 2026.3.0+
- Python 3.12+
- `paho-mqtt>=2.1.0`

### Static checks

```bash
python -m py_compile custom_components/sirius_rangehood/*.py
```

### Tests

```bash
pytest tests/
```

## License

MIT

## Architecture

Detailed architecture and design decisions are documented in
[ARCHITECTURE.md](/ARCHITECTURE.md) at the repository root. Key topics:

- **ADR-1**: Why direct paho-mqtt instead of HA's MQTT integration
- **ADR-2**: Thread-safe MQTT callback bridge via `call_soon_threadsafe`
- **ADR-3**: Coordinator as single source of truth
- **ADR-4**: HTTP for commands, MQTT for live state
- **ADR-5**: Fan speed model (0-4) and percentage mapping
- **ADR-6**: Proactive JWT token refresh
- **ADR-7**: Auto-discovery of new devices
- **ADR-8**: Reauth flow on authentication failure