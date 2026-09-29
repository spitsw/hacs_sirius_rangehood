"""HTTP API client for the Sirius server."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import Any, TypeVar

import aiohttp

from homeassistant.helpers.storage import Store

from .const import API_DEVICES, API_LOGIN, API_SET_VALUE, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds

_T = TypeVar("_T")


async def _run_with_retry(
    coro_factory: Callable[[], Coroutine[Any, Any, _T]],
    retries: int = _MAX_RETRIES,
) -> _T:
    """Await a coroutine, retrying on timeout and transient HTTP errors.

    *coro_factory* is a zero-argument callable that returns a coroutine.
    The first call receives the original timeout; retries use
    *timeout + (2 ** attempt)* seconds to allow longer recovery.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            last_exc = exc
            _LOGGER.debug("HTTP request failed (attempt %d/%d): %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


class SiriusHub:
    """Manages authentication and HTTP API calls to the Sirius server."""

    def __init__(
        self,
        session: aiohttp.ClientSession | None = None,
        sirius_endpoint: str = "",
        username: str = "",
        password: str = "",
        store: Store | None = None,
        insecure_tls: bool = False,
    ) -> None:
        self._insecure_tls = insecure_tls
        if insecure_tls:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
            )
        else:
            self._session = session or aiohttp.ClientSession()
        self._sirius_endpoint = sirius_endpoint.rstrip("/")
        self._username = username
        self._password = password
        self._store = store
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._lock = asyncio.Lock()

    async def async_ensure_token(self, retry: bool = True) -> str:
        """Return a valid token, refreshing or logging in if needed."""
        async with self._lock:
            if self._token and self._token_expiry and self._token_expiry > datetime.now():
                return self._token
            return await self._async_login(retry=retry)

    def attach_store(self, store: Store) -> None:
        """Attach a HA Store for token persistence."""
        self._store = store

    def restore_token(self, token: str | None, expiry_iso: str | None) -> None:
        """Restore a previously persisted token (used after setup from store)."""
        self._token = token
        if expiry_iso:
            try:
                self._token_expiry = datetime.fromisoformat(expiry_iso)
            except ValueError:
                self._token_expiry = None

    async def _async_login(self, retry: bool = True) -> str:
        """Authenticate and store the token."""
        url = f"{self._sirius_endpoint}{API_LOGIN}"
        payload = {
            "email": self._username,
            "password": self._password,
        }
        try:
            async with await _run_with_retry(
                lambda: self._session.post(url, json=payload, timeout=API_TIMEOUT),
                retries=_MAX_RETRIES if retry else 1,
            ) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("JWT"):
                    _LOGGER.error("Login failed (HTTP %d)", resp.status)
                    raise SiriusAuthError(f"Login failed: {data}")
                self._token = data["JWT"]
                self._token_expiry = datetime.now() + timedelta(
                    seconds=data.get("expires", 3600)
                )
                if self._store:
                    await self._store.async_save(
                        {"token": self._token, "expiry": self._token_expiry.isoformat()}
                    )
                _LOGGER.info("Sirius auth token refreshed, expires at %s", self._token_expiry.isoformat())
                return self._token
        except SiriusAuthError:
            raise  # never retry a credential rejection
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Login request failed%s", " after retries" if retry else "")
            raise

    async def async_discover_devices(self, retry: bool = True) -> list[dict[str, Any]]:
        """Fetch all devices from the Sirius server and flatten their data.

        When *retry* is False (config flow), a single attempt is made —
        the caller can resubmit on failure.
        """
        token = await self.async_ensure_token(retry=retry)
        url = f"{self._sirius_endpoint}{API_DEVICES}"
        headers = {"Authorization": f"Bearer {token}"}
        http_call = lambda: self._session.get(url, headers=headers, timeout=API_TIMEOUT)
        try:
            async with (
                await _run_with_retry(http_call, retries=_MAX_RETRIES if retry else 1)
            ) as resp:
                data = await resp.json()
                if resp.status == 401:
                    self._token = None
                    self._token_expiry = None
                    raise SiriusAuthError("JWT rejected by /devices/")
                if resp.status != 200:
                    _LOGGER.error("Failed to discover devices (HTTP %d)", resp.status)
                    return []
                raw_devices = data if isinstance(data, list) else data.get("devices", [])
                return [self._flatten_device(d) for d in raw_devices]
        except SiriusAuthError:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Device discovery failed%s", " after retries" if retry else "")
            return []

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
            flat[uid] = cap["value"]
            limits[uid] = {
                "min": float(cap.get("minValue", 0)),
                "max": float(cap.get("maxValue", 100)),
            }

        flat["_limits"] = limits

        device_name = flat.get("property.device_name")
        if device_name:
            flat["name"] = device_name

        return flat

    async def async_get_status(self, device_id: str) -> str:
        """Send a getStatus command. Device status arrives asynchronously via MQTT."""
        request_id = str(uuid.uuid4())
        _LOGGER.debug("getStatus for device %s (requestId=%s)", device_id, request_id)
        payload = {
            "command": "getStatus",
            "deviceType": "smartphone",
            "parameters": [],
            "requestId": request_id,
        }
        await self._post_set_value(device_id, payload)
        return request_id

    async def async_send_command(
        self, device_id: str, parameters: list[dict[str, Any]]
    ) -> str:
        """Send a setValue command. Device auto-publishes updated status via MQTT."""
        request_id = str(uuid.uuid4())
        _LOGGER.debug(
            "setValue for device %s: %s (requestId=%s)", device_id, parameters, request_id
        )
        payload = {
            "command": "setValue",
            "deviceType": "smartphone",
            "parameters": parameters,
            "requestId": request_id,
        }
        await self._post_set_value(device_id, payload)
        return request_id

    async def _post_set_value(
        self, device_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Low-level POST to /devices/{id}/set_value."""
        token = await self.async_ensure_token()
        url = f"{self._sirius_endpoint}{API_SET_VALUE.format(device_id=device_id)}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with await _run_with_retry(
                lambda: self._session.post(
                    url, json=payload, headers=headers, timeout=API_TIMEOUT
                )
            ) as resp:
                if resp.status == 401:
                    self._token = None
                    self._token_expiry = None
                    raise SiriusAuthError("JWT rejected by set_value")

                data = None
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    # Server may return a non-JSON response (e.g. empty body
                    # with 2xx) — the command was still processed.
                    pass

                if resp.status != 200:
                    _LOGGER.error("set_value failed for device %s (HTTP %d)", device_id, resp.status)
                else:
                    _LOGGER.debug("set_value succeeded for device %s", device_id)
                return data
        except SiriusAuthError:
            raise
        except asyncio.TimeoutError:
            _LOGGER.error("set_value timed out for %s after retries", device_id)
            return None
        except aiohttp.ClientError:
            _LOGGER.warning(
                "set_value connection lost for %s after retries "
                "(command may have been processed; check for MQTT status update)",
                device_id,
            )
            return None


class SiriusAuthError(Exception):
    """Raised when authentication with the Sirius server fails."""