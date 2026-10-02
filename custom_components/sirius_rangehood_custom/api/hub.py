# Copyright (c) 2026 Warren Spits
"""HTTP API client for the Sirius server."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

from .const import (
    API_DEVICES,
    API_LOGIN,
    API_SET_VALUE,
    API_TIMEOUT,
    PROP_FW_VERSION,
    VERSION,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from homeassistant.helpers.storage import Store

_USER_AGENT = f"HomeAssistant-CustomIntegration-spitsw/{VERSION}"
_DEVICE_TYPE = "home_assistant"

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds

_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401

_NETWORK_ERRORS = (TimeoutError, aiohttp.ClientError)

_CLIENT_TIMEOUT = aiohttp.ClientTimeout(total=API_TIMEOUT)


def _auth_headers(token: str) -> dict[str, str]:
    """Return standard headers for Sirius API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": _USER_AGENT,
    }


async def _run_with_retry[T](
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    retries: int = _MAX_RETRIES,
) -> T:
    """
    Await a coroutine, retrying on timeout and transient HTTP errors.

    *coro_factory* is a zero-argument callable that returns a coroutine.
    The first call receives the original timeout; retries use
    *timeout + (2 ** attempt)* seconds to allow longer recovery.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except _NETWORK_ERRORS as exc:
            last_exc = exc
            _LOGGER.debug(
                "HTTP request failed (attempt %d/%d): %s", attempt + 1, retries, exc
            )
            if attempt < retries - 1:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2**attempt))
    if last_exc is None:
        msg = "retries must be at least 1"
        raise ValueError(msg)
    raise last_exc


class SiriusHub:
    """Manages authentication and HTTP API calls to the Sirius server."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        sirius_endpoint: str = "",
        username: str = "",
        password: str = "",
    ) -> None:
        """Initialize the hub with the shared Home Assistant HTTP session."""
        self._session = session
        self._sirius_endpoint = sirius_endpoint.rstrip("/")
        self._username = username
        self._password = password
        self._store: Store | None = None
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._lock = asyncio.Lock()

    @property
    def endpoint(self) -> str:
        """Return the configured Sirius REST endpoint."""
        return self._sirius_endpoint

    @property
    def token_expiry(self) -> datetime | None:
        """Return the current token expiry, if a token is held."""
        return self._token_expiry

    async def async_ensure_token(self, *, retry: bool = True) -> str:
        """Return a valid token, refreshing or logging in if needed."""
        async with self._lock:
            if (
                self._token
                and self._token_expiry
                and self._token_expiry > datetime.now(UTC)
            ):
                return self._token
            return await self._async_login(retry=retry)

    def attach_store(self, store: Store) -> None:
        """Attach a HA Store for token persistence."""
        self._store = store

    def restore_token(self, token: str | None, expiry_iso: str | None) -> None:
        """Restore a previously persisted token (used after setup from store)."""
        self._token = token
        expiry: datetime | None = None
        if expiry_iso:
            try:
                expiry = datetime.fromisoformat(expiry_iso)
            except ValueError:
                expiry = None
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        self._token_expiry = expiry

    async def _async_login(self, *, retry: bool = True) -> str:
        """Authenticate and store the token."""
        url = f"{self._sirius_endpoint}{API_LOGIN}"
        payload = {
            "email": self._username,
            "password": self._password,
        }
        try:
            async with await _run_with_retry(
                lambda: self._session.post(
                    url,
                    json=payload,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=_CLIENT_TIMEOUT,
                ),
                retries=_MAX_RETRIES if retry else 1,
            ) as resp:
                data = await resp.json()
                if resp.status != _HTTP_OK or not data.get("JWT"):
                    _LOGGER.error("Login failed (HTTP %d)", resp.status)
                    msg = f"Login failed: {data}"
                    raise SiriusAuthError(msg)  # noqa: TRY301
                token: str = data["JWT"]
                self._token = token
                self._token_expiry = datetime.now(UTC) + timedelta(
                    seconds=data.get("expires", 3600)
                )
                if self._store:
                    await self._store.async_save(
                        {"token": token, "expiry": self._token_expiry.isoformat()}
                    )
                _LOGGER.info(
                    "Sirius auth token refreshed, expires at %s",
                    self._token_expiry.isoformat(),
                )
                return token
        except SiriusAuthError:
            raise  # never retry a credential rejection
        except _NETWORK_ERRORS:
            _LOGGER.exception(
                "Login request failed%s", " after retries" if retry else ""
            )
            raise

    async def async_discover_devices(
        self, *, retry: bool = True
    ) -> list[dict[str, Any]]:
        """
        Fetch all devices from the Sirius server and flatten their data.

        When *retry* is False (config flow), a single attempt is made;
        the caller can resubmit on failure.
        """
        token = await self.async_ensure_token(retry=retry)
        url = f"{self._sirius_endpoint}{API_DEVICES}"
        headers = _auth_headers(token)

        def http_call() -> Any:
            return self._session.get(url, headers=headers, timeout=_CLIENT_TIMEOUT)

        try:
            async with await _run_with_retry(
                http_call, retries=_MAX_RETRIES if retry else 1
            ) as resp:
                data = await resp.json()
                if resp.status == _HTTP_UNAUTHORIZED:
                    self._token = None
                    self._token_expiry = None
                    msg = "JWT rejected by /devices/"
                    raise SiriusAuthError(msg)  # noqa: TRY301
                if resp.status != _HTTP_OK:
                    _LOGGER.error("Failed to discover devices (HTTP %d)", resp.status)
                    return []
                raw_devices = (
                    data if isinstance(data, list) else data.get("devices", [])
                )
                result = [self._flatten_device(d) for d in raw_devices]
                _LOGGER.debug("Discovered %d device(s)", len(result))
                for d in result:
                    _LOGGER.debug(
                        "  %s: name=%r, model=%r, fw=%r",
                        d.get("uid"),
                        d.get("name"),
                        d.get("description"),
                        d.get(PROP_FW_VERSION),
                    )
                return result
        except SiriusAuthError:
            raise
        except _NETWORK_ERRORS:
            _LOGGER.exception(
                "Device discovery failed%s", " after retries" if retry else ""
            )
            raise

    def _flatten_device(self, device: dict[str, Any]) -> dict[str, Any]:
        """Flatten properties[] and capabilities[] into a single dict per device."""
        flat: dict[str, Any] = {
            "id": device["id"],
            "uid": device.get("uid", ""),
            "name": device.get("description", f"Rangehood {device['id']}"),
            "description": device.get("description", ""),
        }

        for prop in device.get("properties", []):
            flat[prop["id"]] = prop["value"]

        limits: dict[str, dict[str, float]] = {}
        for cap in device.get("capabilities", []):
            uid = cap["capabilityUid"]
            # Do NOT store flat[uid] = cap["value"]: the capabilities array
            # carries default/placeholder values, not live device state.
            # Live state arrives via MQTT after a getStatus command.
            limits[uid] = {
                "min": float(cap.get("minValue", 0)),
                "max": float(cap.get("maxValue", 100)),
            }

        flat["_limits"] = limits

        return flat

    async def async_get_status(self, device_id: str) -> bool:
        """
        Send a getStatus command. Device status arrives asynchronously via MQTT.

        Returns True when the request reached the server.
        """
        request_id = str(uuid.uuid4())
        _LOGGER.debug("getStatus for device %s (requestId=%s)", device_id, request_id)
        payload = {
            "command": "getStatus",
            "deviceType": _DEVICE_TYPE,
            "parameters": [],
            "requestId": request_id,
        }
        return await self._post_set_value(device_id, payload)

    async def async_send_command(
        self, device_id: str, parameters: list[dict[str, Any]]
    ) -> bool:
        """
        Send a setValue command. Device auto-publishes updated status via MQTT.

        Returns True when the request reached the server.
        """
        request_id = str(uuid.uuid4())
        _LOGGER.debug(
            "setValue for device %s: %s (requestId=%s)",
            device_id,
            parameters,
            request_id,
        )
        payload = {
            "command": "setValue",
            "deviceType": _DEVICE_TYPE,
            "parameters": parameters,
            "requestId": request_id,
        }
        return await self._post_set_value(device_id, payload)

    async def _post_set_value(self, device_id: str, payload: dict[str, Any]) -> bool:
        """Low-level POST to /devices/{id}/set_value. True when accepted (HTTP 200)."""
        token = await self.async_ensure_token()
        url = f"{self._sirius_endpoint}{API_SET_VALUE.format(device_id=device_id)}"
        headers = _auth_headers(token)
        try:
            async with await _run_with_retry(
                lambda: self._session.post(
                    url, json=payload, headers=headers, timeout=_CLIENT_TIMEOUT
                )
            ) as resp:
                if resp.status == _HTTP_UNAUTHORIZED:
                    self._token = None
                    self._token_expiry = None
                    msg = "JWT rejected by set_value"
                    raise SiriusAuthError(msg)  # noqa: TRY301

                if resp.status != _HTTP_OK:
                    _LOGGER.error(
                        "set_value failed for device %s (HTTP %d)",
                        device_id,
                        resp.status,
                    )
                    return False
                _LOGGER.debug("set_value succeeded for device %s", device_id)
                return True
        except SiriusAuthError:
            raise
        except TimeoutError:
            _LOGGER.exception("set_value timed out for %s after retries", device_id)
            return False
        except aiohttp.ClientError:
            _LOGGER.warning(
                "set_value connection lost for %s after retries "
                "(command may have been processed; check for MQTT status update)",
                device_id,
            )
            return False


class SiriusAuthError(Exception):
    """Raised when authentication with the Sirius server fails."""
