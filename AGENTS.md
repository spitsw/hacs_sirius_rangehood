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

# Tests (deps in requirements_dev.txt; needs a Python with build headers,
# e.g. a uv-managed 3.14)
pytest tests/                                  # 45 tests, ~1s

# Type check (pyright needs the HA env to resolve imports)
pyright --pythonpath <python-with-homeassistant>

# Local HA dev instance (port 8124 -> container 8123)
docker compose up
```

CI (`.github/workflows/lint.yaml`) runs `python3 -m ruff check .` and
`python3 -m ruff format . --check`; `.github/workflows/test.yaml` runs
`python3 -m pytest tests/` and `pyright`. `validate.yaml` runs Hassfest and
HACS validation — it checks `manifest.json`, `strings.json`/translations, and
file structure, so keep those consistent.

**Releases are automated with `python-semantic-release` (PSR).** `release.yaml`
runs on every push to `main`: PSR derives the next SemVer from the Conventional
Commit messages, bumps `version` in **both** `pyproject.toml` and
`manifest.json` (see `version_toml`/`version_variables` in `pyproject.toml`),
commits, tags `vX.Y.Z`, and creates the GitHub Release. So **HACS versions off
the git tag, and the manifest version always matches it** — write Conventional
Commit messages (`feat:`, `fix:`, `chore:` …) rather than hand-editing versions
or tagging manually.

**`main` is protected — push changes via a PR, not directly.** jj supports this:
create a bookmark, push it, open a PR (`jj bookmark create <name> -r @` then
`jj git push --bookmark <name> --remote github`). Because PSR pushes its
version-bump commit *to* `main`, the release workflow needs `RELEASE_TOKEN` (a
PAT/GitHub App token that is a branch-protection bypass actor) instead of the
default `GITHUB_TOKEN`.

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

- **Coordinator is the single source of truth.** `SiriusRangehoodCoordinator`
  (`coordinator.py`, a `DataUpdateCoordinator` subclass) owns `device_states`
  (keyed by device **uid**, not numeric id). Both data paths funnel through it:
  MQTT push via `apply_mqtt_update()` and the HTTP `getStatus` heartbeat via its
  `_async_update_data`. Entities subclass `CoordinatorEntity` (via
  `SiriusEntity`) and only ever read `coordinator.data.get(device_id)`.
- **Commands go out over HTTP, state comes in over MQTT.** `hub.async_send_command()`
  POSTs `setValue`; the device then pushes a `/status` message that updates
  state. Entities do not read the HTTP response for state.
- **MQTT connectivity is surfaced.** The coordinator tracks `mqtt_connected`
  (updated thread-safely from the paho callbacks; see below).
  `SiriusEntity.available` reflects it with a 30 s grace, and a
  `mqtt_unavailable` Repairs issue is raised when an outage outlasts the grace.
- **The HTTP `getStatus` heartbeat is a functional no-op.** The coordinator's
  `update_method` fires every 300 s purely so a periodic update exists (keeps
  `last_update_success` true and the MQTT stream primed). It never returns
  state. Do not "optimize" it into the state source.
- **Thread safety (ADR-2):** paho-mqtt invokes `_on_message` / `_on_connect`
  / `_on_disconnect` on a background thread. `_on_mqtt_status` and
  `_on_mqtt_connection` must **only** schedule work via
  `hass.loop.call_soon_threadsafe(coordinator.apply_mqtt_update | .set_mqtt_connected, ...)`.
  Never touch `coordinator.data` / `device_states` from the paho thread.
- **Device discovery is setup-time only (ADR-7).** `/devices/` is fetched once
  in `async_setup_entry`. New devices require the user to run **Configure**
  (reconfigure) — there is no polling-for-new-devices path.
- **Reauth (ADR-8):** `SiriusAuthError` from login or a 401 triggers
  `async_start_reauth`; the reauth/reconfigure flow uses
  `async_update_reload_and_abort` to preserve entities and registry entries.

### Platform entity map

`async_setup_entry` in `__init__.py` forwards to `PLATFORMS` and stores a
`SiriusRangehoodData` dataclass on `entry.runtime_data`. Each platform file
follows the same shape: an `async_setup_entry` that reads `entry.runtime_data`
and constructs entities from `(coordinator, did, device, entry)`.

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

- **Linting is strict.** `.ruff.toml` (corrected from a previously misspelled
  `.ruff.yoml`) activates `select = ["ALL"]`, so source must stay lint-clean:
  `ruff check .` and `ruff format . --check` both pass today and are exactly
  what CI runs. Tests are exempted from the test-hostile rules via
  `[lint.per-file-ignores]` (`S101`, `ANN`, `D`, `CPY001`, `PLR2004`,
  `SLF001`, ...). Keep both commands green when adding code.
- **Tests use the real Home Assistant test harness.** `tests/conftest.py`
  provides an autouse fixture enabling custom integrations, and the suite runs
  under `pytest-homeassistant-custom-component` (the `hass` fixture is real HA).
  The repo root is on `sys.path` via `pythonpath = .` in `pytest.ini`.
- **Type checking is on (`pyright`, basic mode).** `pyrightconfig.json` scopes it
  to `custom_components/` and sets `reportIncompatibleVariableOverride = "none"`
  because HA's stubs type entity properties as `cached_property`, which
  integrations override with `@property`. Run it with a Python that has
  `homeassistant` installed: `pyright --pythonpath <that python>`.
- **`_flatten_device` deliberately drops capability values.** The
  `capabilities[].value` fields are placeholder/default values, not live state,
  so only `_limits` (min/max) is kept. Live values arrive via MQTT. A test
  enforces this — do not "restore" capability values into the flat dict.
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
- Run the whole suite with `pytest tests/`. Uses
  `pytest-homeassistant-custom-component` (declared in `requirements_dev.txt`);
  `pytest.ini` sets `asyncio_mode = auto` and `pythonpath = .`.
- Coverage: `test_hub.py` (`_flatten_device`, token restore), `test_mqtt.py`
  (payload parsing, topic extraction, connection callbacks), `test_const.py`
  (speed/percentage mapping, manifest consistency), `test_config_flow.py`
  (`_validate_urls` plus the user -> menu -> finish flow), `test_coordinator.py`
  (`apply_mqtt_update`, MQTT availability/grace), `test_init.py`
  (setup/unload via `MockConfigEntry`, with `SiriusHub`/`SiriusMQTT` faked).
- The harness pulls in `homeassistant`, one of whose deps compiles a C
  extension, so the test environment needs Python build headers (or a
  uv-managed Python, which ships them).
