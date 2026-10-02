# AGENTS.md

Guidance for agents working in this repository.

## What this is

A Home Assistant **custom integration** (HACS, `integration_type: device`,
`iot_class: cloud_push`) for WiFi-enabled Sirius rangehoods. It talks to the
Sirius cloud over two channels: an HTTPS REST API (auth, device discovery,
commands) and an MQTTS broker (live state). It is one config entry per Sirius
account, one HA device per discovered rangehood.

The integration is split into two strict layers:

- `custom_components/sirius_rangehood_custom/api/` — all protocol code (HTTP +
  MQTT). **The HA layer never makes direct HTTP/MQTT calls and never imports
  a submodule of `api` — it imports everything from `.api`** (the package
  re-exports its public surface in `api/__init__.py::__all__`). When adding a
  constant or helper, add it to `api/__init__.py` too.
- The rest of `custom_components/sirius_rangehood_custom/` — HA platform
  entities, config flow, coordinator wiring, diagnostics.

## Commands

```bash
# Lint + format check (same as CI; CI uses Python 3.14)
.venv/bin/ruff check .
.venv/bin/ruff format . --check

# Tests (pytest is NOT in requirements*.txt; it is installed via a uv tool)
pytest tests/sirius_rangehood_custom/          # 32 tests, ~0.05s

# Local HA dev instance (port 8124 -> container 8123)
docker compose up
```

CI (`.github/workflows/lint.yaml`) runs `python3 -m ruff check .` and
`python3 -m ruff format . --check`. A second workflow
(`validate.yaml`) runs Hassfest and HACS validation — it checks
`manifest.json`, `strings.json`/translations, and file structure, so keep
those consistent.

## Version control (Jujutsu)

This repo is a **colocated jj + Git** repo (`.jj/` beside `.git/`). Git stays the
canonical remote/PR/CI interface; **mutate only with `jj`**. Mutating raw `git`
(`git add/commit/reset/checkout/rebase/merge/stash`) desyncs the two — read-only
git (`git status/log/diff/show/blame`) is fine.

```bash
jj --no-pager status        # snapshot the working copy, then show it
jj --no-pager diff          # review changes (--stat for a summary)
jj describe -m "<msg>"      # set the message on the current change (@)
jj new -m "<next unit>"     # start a new empty change (one logical unit per change)
jj edit <change-id>         # move @ onto an existing change to amend it
jj log                      # history; @ is the working copy
jj undo                     # revert the last operation (jj op log for older)
jj bookmark create <name> -r @-            # bookmark == git branch on push
jj git push --bookmark <name>
```

- `ui.paginate=never` is set globally and `--no-pager` is still passed per
  command.
- **Never run editor/TUI forms** — bare `jj describe`/`commit`/`squash`,
  interactive `jj split`/`jj squash -i`/`jj resolve`/`jj diffedit`. They hang an
  agent. Use the `-m` and path-based non-interactive forms instead.
- jj snapshots the working copy only when a jj command runs, so run
  `jj status` after edits before relying on the operation log.
- To split a mixed change: `jj split <path> -m "<msg>"`.

## Architecture and data flow

The full rationale is in `ARCHITECTURE.md` (ADR-1 … ADR-11) and the wire
protocol in `PROTOCOL.md`. Read those before changing behavior. The
load-bearing points:

- **Coordinator is the single source of truth.** `DataUpdateCoordinator` owns
  `device_states` (keyed by device **uid**, not numeric id). Entities subclass
  `CoordinatorEntity` (via `SiriusEntity`) and only ever read
  `coordinator.data.get(device_id)`.
- **Commands go out over HTTP, state comes in over MQTT.** `hub.async_send_command()`
  POSTs `setValue`; the device then pushes a `/status` message that updates
  state. Entities do not read the HTTP response for state.
- **The HTTP `getStatus` heartbeat is a functional no-op.** The coordinator's
  `update_method` fires every 300 s purely so a periodic update exists (keeps
  `last_update_success` true and the MQTT stream primed). It never returns
  state. Do not "optimize" it into the state source.
- **Thread safety (ADR-2):** paho-mqtt invokes `_on_message` on a background
  thread. `_on_mqtt_status` must **only** schedule work via
  `hass.loop.call_soon_threadsafe(_apply_mqtt_update, ...)`. Never touch
  `coordinator.data` / `device_states` from the paho thread.
- **Device discovery is setup-time only (ADR-7).** `/devices/` is fetched once
  in `async_setup_entry`. New devices require the user to run **Configure**
  (reconfigure) — there is no polling-for-new-devices path.
- **Reauth (ADR-8):** `SiriusAuthError` from login or a 401 triggers
  `async_start_reauth`; the reauth/reconfigure flow uses
  `async_update_reload_and_abort` to preserve entities and registry entries.

### Platform entity map

`async_setup_entry` in `__init__.py` forwards to `PLATFORMS`. Each platform
file follows the same shape: an `async_setup_entry` that loops
`data["devices"]` and constructs entities from `(coordinator, did, device, entry)`.

| File | Entities |
|------|----------|
| `fan.py` | `SiriusRangehoodFan` — speeds 0-4, mapped to 0/25/50/75/100 % |
| `light.py` | `SiriusRangehoodLight` — brightness (normalized to 10-100 %), Kelvin colour temp |
| `switch.py` | Power, Bi-Power (only if capability present), Timer active |
| `number.py` | Timer duration (min/max from `device["_limits"]`) |
| `sensor.py` | Diagnostic sensors + filter countdown (seconds→hours) + timer off-time |
| `binary_sensor.py` | Filter worn |

## Conventions

- Every module opens with `from __future__ import annotations` and a module
  docstring; `_LOGGER = logging.getLogger(__name__)`.
- Full type hints. HA style: `_attr_*` class attributes over `@property` where
  possible; base classes use `@property` for state derived from the coordinator.
- `_attr_unique_id` is `f"{device_id}_{suffix}"`; `_attr_device_info` comes
  from `sirius_device_info(device_id, device)` in `entity.py`.
- Device state keys are the raw API `property.*` / `device.*` strings defined
  as `PROP_*` / `CAP_*` in `api/const.py`. Prefer those constants over literals.
- User-facing names are localized via `translation_key` (not `name`) for most
  entities; keep `strings.json` and `translations/en.json` in sync.
- `VERSION` lives in two places: `api/const.py` and `manifest.json`.

## Non-obvious gotchas

- **Linting is strict.** The config file was previously misspelled
  (`.ruff.yoml`), so Ruff silently ignored it; it is now corrected to
  `.ruff.toml`, which activates `select = ["ALL"]`. The existing codebase does
  **not** yet satisfy that config — `ruff check .` currently reports ~328
  violations (e.g. `S101`, `ANN201`, `D102`, `CPY001`, `TC002`) and two files
  need reformatting, so `ruff check .` / `ruff format . --check` fail until
  those are fixed or the config's `ignore`/`per-file-ignores` is widened.
- **`tests/conftest.py` hardcodes `sys.path.insert(0, "/home/warren/dev")`.**
  Tests only work from this exact checkout path.
- **Tests do not run a real Home Assistant.** The root `conftest.py`
  registers synthetic `MagicMock` modules for every `homeassistant.*`,
  `voluptuous`, `aiohttp`, and `paho` import the component uses. A test that
  needs a new HA symbol must add it to that mock list first.
- **`_flatten_device` deliberately drops capability values.** The
  `capabilities[].value` fields are placeholder/default values, not live state,
  so only `_limits` (min/max) is kept. Live values arrive via MQTT. A test
  enforces this — do not "restore" capability values into the flat dict.
- **`fan.py` overrides `_async_send_command` with a different signature**
  (`(capability_id, value)`) than `SiriusEntity._async_send_command`
  (`(params: list)`). Other platforms use the base list form. Watch which
  `self._async_send_command` you are calling inside fan code.
- Dead/unused code you may notice: `LIVE_CAPABILITY_KEYS` and
  `DEVICES_POLL_INTERVAL` in `api/const.py` are defined but never used, and
  `hub._flatten_device` has an unreachable duplicate `return flat`.
- TLS verification is intentionally disabled (`CERT_NONE`, hostname check off)
  for the Sirius broker because its certificate is expired (ADR-1). `insecure_tls`
  from the config flow controls the equivalent for the HTTP client.
- The MQTT broker is an external, single-purpose connection managed directly
  with `paho-mqtt` (declared in `manifest.json`), **not** HA's global `mqtt`
  integration — do not move it there (ADR-1).
- Do not edit `.storage` or `__pycache__`; `*.pyc`/`__pycache__/` are ignored
  and not tracked.

## Tests

- Location: `tests/sirius_rangehood_custom/` (mirrors the component path).
- Run the whole suite with `pytest tests/sirius_rangehood_custom/`.
- Existing coverage is unit-level: `test_hub.py` (`_flatten_device`,
  `SiriusAuthError`), `test_mqtt.py` (`_on_message` parsing, topic device-id
  extraction, `subscribe_device`, SSL context shape), `test_const.py`
  (speed/percentage mapping bijection), `test_config_flow.py` (`_validate_urls`).
- There is no coverage of `async_setup_entry` / coordinator wiring; those are
  exercised only against the real HA dev instance via `docker compose`.
