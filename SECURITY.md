# Security Policy

## Supported versions

Only the **latest release** is supported. This integration is distributed via
HACS and versioned off Git tags, so fixes are only provided in the most recent
release. Please upgrade before reporting.

| Version | Supported |
| ------- | --------- |
| Latest release | :white_check_mark: |
| Older releases | :x: |

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues.**

Use GitHub's **private vulnerability reporting**:

1. Open the repository's **Security** tab, or go directly to
   <https://github.com/spitsw/hacs_sirius_rangehood/security/advisories/new>.
2. Click **Report a vulnerability** and fill in the details.

If the "Report a vulnerability" button is unavailable, private reporting has not
been enabled for this repository. In that case, open a minimal public issue
asking the maintainer to enable it, without disclosing any details.

Please include: affected version, Home Assistant version, steps to reproduce,
the impact, and any suggested fix.

### What to expect

This is a small, volunteer-maintained project with no service-level agreement:

- Reports are acknowledged as soon as reasonably possible.
- Valid issues are investigated and, where possible, fixed in a coordinated release.
- You are credited in the release notes/advisory unless you prefer otherwise.
- No bug bounty is offered.

Please allow a reasonable window to fix the issue before any public disclosure.

## Scope

**In scope** (this integration's code):

- Handling of the Sirius account credentials and the cached auth token.
- HTTP/MQTT request and URL/endpoint handling, and TLS configuration.
- Anything that could lead to credential disclosure, code execution, or
  unauthorised device control on the user's Home Assistant instance.

**Out of scope:**

- Vulnerabilities in **Home Assistant core**, **HACS**, or third-party
  dependencies (report those upstream, e.g. `paho-mqtt`, `aiohttp`).
- Issues in the **Sirius cloud service or the rangehood firmware** itself.
- The Sirius MQTT broker's **expired TLS certificate** and the resulting
  disabled certificate verification (see `ARCHITECTURE.md`, ADR-1) — a known
  limitation of the upstream service, not a vulnerability here. Likewise, the
  optional `insecure_tls` setting disables REST TLS verification by explicit
  user choice.
- Misconfiguration of the user's own Home Assistant or network.

## Security-relevant design notes

- The Sirius account **email and password are stored in the Home Assistant
  config entry** (HA's `.storage`), and a bearer token is cached via HA's
  `Store`. Protecting the Home Assistant instance (filesystem, backups, access
  control) is the user's responsibility.
- **TLS:** the REST client verifies certificates unless the user opts into
  `insecure_tls`. The **MQTT** connection uses `CERT_NONE` because the Sirius
  broker certificate has expired (ADR-1).
- **Custom endpoints** may be configured by the user; the integration connects
  only to the endpoint the user supplies.

## Disclaimer

This is an unofficial custom integration and is not affiliated with, endorsed
by, or supported by Sirius or P.G.A. S.R.L.
