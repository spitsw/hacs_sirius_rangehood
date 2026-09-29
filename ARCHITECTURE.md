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

## ADR-7: Discovery via MQTT unknown-UID reload

**Status**: Accepted

**Context**: Sirius devices can appear or disappear at any time (new
rangehood paired, existing one unpaired). The component only discovers
devices once, at setup time.

**Decision**: When an MQTT status message arrives for a UID that is not
in the current `device_states` dict, reload the config entry so the new
entities appear. No periodic `/devices/` poll is needed — with 1–3
devices, discovery is rare, and MQTT is the primary channel for all
device activity.

**Consequences**:
- New devices are detected within seconds (when they first publish via
  MQTT), not up to an hour later.
- Config entry reload is heavyweight but negligible at 1–3 devices.
- No mechanism yet to handle device removal — a removed device must be
  manually deleted from HA.

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

---

## ADR-9: Retry with exponential backoff for HTTP calls

**Status**: Accepted

**Context**: The Sirius server is an external cloud service subject to
network glitches, rate limiting (429), and temporary outages (502/503/504).
The component uses HTTP for both commands (`setValue`) and polling
(`getStatus`). A single transient failure should not cause a visible
failure to the user.

**Decision**: Wrap all HTTP API calls in `_run_with_retry()` — an
async retry loop that catches `asyncio.TimeoutError` and
`aiohttp.ClientError`. It retries up to 3 times with a doubling delay
(2 s, 4 s, 8 s).

The retry only applies to *network-level* failures. Application-level
failures (wrong credentials → `SiriusAuthError`, HTTP 4xx) propagate
immediately without retry.

**Consequences**:
- A brief network blip (1–5 s) will not cause a command to fail.
- A sustained outage eventually fails cleanly — the last exception
  propagates to the caller.
- The MQTT stream is unaffected by HTTP retries (separate connection,
  see ADR-1).
- The coordinator's HTTP `getStatus` heartbeat also benefits, reducing
  false-positive reauth triggers from transient errors.

---

## ADR-10: MQTT reconnect with exponential backoff

**Status**: Accepted

**Context**: paho-mqtt's default reconnect behaviour after a disconnection
is a fixed 1-second delay. During a cloud outage this can produce a
thundering-herd of reconnect attempts against the Sirius broker.

**Decision**: Configure paho-mqtt's built-in `reconnect_delay_set()`
with `min_delay=1, max_delay=120`. The first reconnect attempt happens
after 1 second; after each failure the delay doubles up to a 2-minute
cap. When the broker comes back, the first attempt succeeds at the
current backoff level.

**Consequences**:
- No unnecessary load on the Sirius broker during outages.
- Reconnection is automatic — no custom reconnect logic needed.
- The component continues to work via HTTP polling while MQTT is
  disconnected (coordinator fallback).

---

## ADR-11: MQTT subscriptions — status only, no response topics

**Status**: Accepted

**Context**: The Sirius MQTT broker publishes two message types per device:

- `.../devices/{id}/status` — periodic state snapshots and push updates
  whenever a value changes. Payload contains a flat `values` array with
  `{id, value}` pairs that directly map to device capabilities.

- `.../devices/{id}/response/{uuid}` — simple acknowledgements returned
  after a `setValue` command is processed. Payload contains only a
  timestamp and a status field (e.g. `{"timestamp": ..., "status": "OK"}`).
  No state data.

**Decision**: Only subscribe to `/status`. The `/response/#` topic carries
no information that the component needs — command success is confirmed by
the subsequent status update that the device publishes via MQTT after
processing the command.

**Consequences**:
- Half the subscriptions (one topic per device instead of two).
- No wasted messages, no payload parsing for acks.
- The HTTP `set_value` call may still fail with a dropped connection
  (see ADR-9), but the command is still processed and the status update
  arrives via MQTT.