# Architecture & Design Decisions

This document records key architectural decisions (ADRs) for the Sirius
Rangehood integration.

---

## ADR-1: Direct paho-mqtt over HA's MQTT integration

**Status**: Accepted

**Context**: The Sirius MQTTS broker presents a valid TLS certificate that
has expired. Home Assistant's built-in `mqtt` integration does not expose a
hook to customise certificate validation, so it would reject the connection.

**Decision**: Use the `paho-mqtt` library directly with a custom `ssl.SSLContext`
whose `verify_callback` only skips the expiry check (`X509_V_ERR_CERT_HAS_EXPIRED`
= errno 10). All other validation (chain of trust, hostname, issuer) still
applies.

**Consequences**:
- No dependency on HA's MQTT integration — the component is self-contained.
- Must manage its own connection lifecycle (`loop_start`/`loop_stop`).
- If Sirius ever renews their certificate, the custom context will still work
  (the callback returns `preverify_ok` for all non-expiry errors).

---

## ADR-2: Thread-safe MQTT callback bridge

**Status**: Accepted

**Context**: paho-mqtt calls `_on_message` from a background thread. Home
Assistant data structures (`device_states`, `coordinator.data`) must only
be read or written from the HA event loop. A direct call to
`async_set_updated_data` from the paho thread would crash.

**Decision**: Route all MQTT status updates through
`hass.loop.call_soon_threadsafe()`. The paho-thread callback
(`_on_mqtt_status`) schedules `_apply_mqtt_update` on the HA event loop.
`_apply_mqtt_update` mutates `device_states` and calls
`coordinator.async_set_updated_data()` — both from the correct context.

```
paho thread → _on_mqtt_status()
                → call_soon_threadsafe(_apply_mqtt_update, ...)
                    → HA event loop → device_states[did].update(payload)
                        → coordinator.async_set_updated_data(...)
```

**Consequences**:
- No `RuntimeError: Non-thread-safe operation` or data races.
- Slight latency between MQTT message receipt and state update (one
  event-loop iteration), which is negligible for a rangehood.

---

## ADR-3: Coordinator as single source of truth

**Status**: Accepted

**Context**: Device state arrives from two paths — HTTP API polling and MQTT
push messages. Entities need a unified, consistent view of device state
without having to merge two sources themselves.

**Decision**: A `DataUpdateCoordinator` owns the authoritative
`device_states` dict. Both data paths funnel into it:
- **HTTP polling** (every 300 s): `async_update_data` sends `getStatus`
  for each device. The device responds asynchronously via MQTT, so the
  poll primarily serves as a heartbeat to keep MQTT flowing.
- **MQTT push**: Parsed status payloads are merged into the coordinator
  via the thread-safe bridge (ADR-2).

All entities read `coordinator.data.get(device_id)` and are automatically
notified when data changes.

**Consequences**:
- Entities are simple — no per-entity polling or merge logic.
- Single `async_set_updated_data` call per update notifies all entities.
- Coordinator is also used for HA's built-in throttling, logging, and
  error handling.

---

## ADR-4: HTTP for commands, MQTT for live state

**Status**: Accepted

**Context**: The Sirius IoT platform exposes two channels — an HTTPS REST
API and an MQTT broker. Commands (`setValue`) can be sent over either, but
live status updates only arrive over MQTT.

**Decision**:
- **Commands** → HTTPS POST to `/devices/{id}/set_value`. The device
  processes the command and publishes its new state via MQTT.
- **Live state** → MQTT subscription to
  `root/codermine/devices/{id}/status` and `response/#`.
- **Periodic heartbeat** → HTTP `getStatus` (via the coordinator) keeps
  the MQTT data stream alive.

```
User action → FanEntity.async_turn_on()
                → hub.async_send_command()
                    → HTTP POST /set_value {command: "setValue", ...}
Device responds → MQTT status topic
                    → _on_message → call_soon_threadsafe → coordinator
                        → FanEntity updated via CoordinatorEntity
```

**Consequences**:
- Commands are synchronous (HTTP request/response) but state updates are
  asynchronous (MQTT push).
- Entities optimistically update locally after sending a command, then
  converge when the MQTT status arrives.

---

## ADR-5: Fan speed model (0-4)

**Status**: Accepted

**Context**: HA's fan entity expects a `percentage` (0-100) and a
`speed_count`. The Sirius API uses integer speeds 0 (off) through 4
(boost).

**Decision**: Map speeds to percentages linearly:
| Speed | Value | Percentage |
|-------|-------|------------|
| Off | 0 | 0 |
| Low | 1 | 25 |
| Medium | 2 | 50 |
| High | 3 | 75 |
| Boost | 4 | 100 |

`speed_count = 5` (HA counts non-off presets, so this is 4 + 1 for off).

`async_set_percentage` uses nearest-match: `min(PERCENTAGE_TO_SPEED.items(),
key=lambda x: abs(x[0] - percentage))`. Setting 10% lands on speed 0 (off);
setting 37% lands on speed 1 (low); etc.

**Consequences**:
- User sees a 5-step slider in the HA UI.
- Percentage and speed always round-trip cleanly (bijection).

---

## ADR-6: Proactive token refresh

**Status**: Accepted

**Context**: The Sirius JWT has a configurable expiry (default 1 hour). An
expired token causes every API call to first do a login round-trip, which
adds latency.

**Decision**: After setup, schedule `async_ensure_token()` to run 60 seconds
before the token's expiry. This keeps a valid token cached in the hub,
so API calls never wait for a login.

```python
remaining = (token_expiry - datetime.now()).total_seconds() - 60
if remaining > 0:
    async_call_later(hass, remaining, _refresh_token)
```

**Consequences**:
- API calls are fast (no login wait).
- If HA restarts, the token is re-persisted via `Store` and restored on
  next setup.
- On token rejection by the server (e.g. clock drift), the existing 401
  → reauth path still catches it.

---

## ADR-7: Discovery auto-reload

**Status**: Accepted

**Context**: Sirius devices can appear or disappear at any time (new
rangehood paired, existing one unpaired). The component only discovers
devices once, at setup time.

**Decision**: Poll `/devices/` every hour (in addition to the coordinator
heartbeat) and compare discovered device IDs. If new IDs appear, reload
the config entry so the new entities appear. Unknown UIDs arriving over
MQTT also trigger a reload.

**Consequences**:
- New devices appear automatically within 1 hour (or instantly if they
  publish MQTT first).
- Config entry reload is heavyweight — all entities are torn down and
  recreated. At 1-3 devices this is negligible.
- No mechanism yet to handle device removal (the device would need to be
  manually removed from HA).

---

## ADR-8: Reauth on auth failure

**Status**: Accepted

**Context**: When the Sirius password changes or the JWT is rejected,
the user needs to re-enter credentials without losing their existing
configuration.

**Decision**: A central `_trigger_reauth()` helper fires
`hass.config_entries.async_start_reauth(entry_id)` on any
`SiriusAuthError`. The reauth flow (in `config_flow.py`) uses
`async_update_reload_and_abort()` — it updates the existing entry's data
and reloads it, preserving all entity state and device registry entries.

The error is raised by `hub.py` in two places:
1. **Login**: HTTP 200 with no `JWT` field → wrong credentials.
2. **API call**: HTTP 401 → token rejected by server.

**Consequences**:
- User never loses their device registry entries or automations.
- Only auth failures trigger reauth — transient timeouts do not
  (see commit `c8ada64`).