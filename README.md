# Sirius Rangehood

Home Assistant integration for WiFi-enabled Sirius rangehoods.

## Quick Start

1. **Install** — see [Installation](#installation) below, then restart HA.
2. **Add** — go to **Settings → Devices & Services → Add Integration** and search for "Sirius Rangehood".
3. **Log in** — enter your Sirius cloud email and password.

That's it. Your fan controls, light, timer, and sensors appear automatically.

If you use custom server endpoints or need to disable TLS verification,
choose **Configure custom endpoints** after logging in.

---

## What you can do

| Control | What it does |
|---------|-------------|
| **Fan** | 5 speeds (off / low / med / high / boost) |
| **Light** | Brightness and colour temperature (warm → cool) |
| **Timer Duration** | Set countdown in seconds |
| **Timer Active** | Start / stop the countdown |
| **Global Power** | Turn fan and light on/off together |
| **Bi-Power** | Enable extra airflow and powerful extraction (if supported) |

**Sensors** show IP address, WiFi signal strength, firmware version,
filter life, filter worn alert, and estimated turn-off time.

Live values are pushed from the Sirius cloud over MQTT. If that connection
drops, entities become **Unavailable** after about 30 seconds and a
**Repairs** notification ("Sirius Rangehood MQTT connection lost") appears;
both clear automatically once the broker is reachable again.

---

## Installation

### Option 1: HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. Add this repository as a **custom repository** in HACS:
   - URL: `https://github.com/spitsw/hacs_sirius_rangehood`
   - Category: **Integration**
3. Search for "Sirius Rangehood" in HACS and install.
4. Restart Home Assistant.

### Option 2: Manual

Copy the `custom_components/sirius_rangehood_custom/` folder into your
Home Assistant `custom_components/` directory and restart.

---

## Configuration

### First-time setup

1. **Settings → Devices & Services → Add Integration**.
2. Search for `Sirius Rangehood` and select it.
3. Choose an option:
   - **Log in to the Sirius cloud** (recommended) — uses the default server.
   - **Configure custom endpoints (advanced)** — only for a non-standard
     server, or to disable TLS certificate verification.
4. Enter your **Sirius cloud email** and **password**. If you chose custom
   endpoints, your credentials are validated against them.

### Re-configuration

If your credentials change or you need to update endpoints:
- Go to **Settings → Devices & Services → Sirius Rangehood → Configure**.
- You'll be asked to **Log in** or **Change endpoints**; changing endpoints
  never requires a successful login, so a broken server URL can always be
  corrected.

---

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| "Invalid authentication" | Check your password in the Sirius mobile app first |
| "No devices found" | Login worked, but no rangehood is linked to your account |
| Entities show "unknown" | Wait up to 30 seconds — the first status update arrives via MQTT |
| Entities show "Unavailable" | The cloud MQTT broker is unreachable. Check **Settings → System → Repairs** and confirm outbound port 8884 is allowed; it reconnects automatically |
| Entities don't update | Check HA logs for "MQTT" errors. Network or firewall may block port 8884 |
| Re-auth prompt | Token expired — re-enter your password when prompted |

### Debug logging

Enable it from the UI: **Settings → Devices & Services → Sirius Rangehood →
Enable debug logging** — the integration declares a `loggers` entry, so no YAML
is required. To configure it in YAML instead:

```yaml
logger:
  logs:
    custom_components.sirius_rangehood_custom: debug
```

---

## Technical Reference

For developers and advanced users:

- **Architecture decisions** — see [ARCHITECTURE.md](/ARCHITECTURE.md) for
  ADR-1 through ADR-11 covering the design rationale.
- **Protocol details** — MQTT topics, HTTP endpoints, capability IDs are
  documented in [PROTOCOL.md](/PROTOCOL.md).
- **Tests** — `pytest tests/sirius_rangehood_custom/`
- **License** — MIT

---

## Disclaimer

This integration is a custom component and is not affiliated with,
endorsed by, or supported by Sirius, P.G.A. S.R.L., or any of its
affiliates. All product names, logos, and brands are property of
their respective owners.

## Tested Devices

| Model | Status |
|-------|--------|
| SL926 DL 850 T-SHAPE ARISIT | Confirmed working |
