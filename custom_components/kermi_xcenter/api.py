"""Async client for the Kermi x-center local web API (read-only by default).

READS
-----
Every read goes through :meth:`KermiClient._request`, which looks the endpoint
up in :data:`ENDPOINT_ALLOWLIST` (login/logout, device list, datapoint
catalogue, reading values) and raises :class:`KermiReadOnlyError` *before* any
network I/O for anything else.

WRITES
------
There is exactly one write path: :meth:`KermiClient.write_value`. It holds the
separate write allowlist (a single endpoint) and refuses, before any network
I/O, unless ALL of these hold:

a) writes were enabled for this client (config entry option, default off),
b) the datapoint is in :data:`datapoints.WRITABLE`,
c) the value is inside the live catalogue's MinValue/MaxValue AND inside our
   own tighter safety range,
d) the per-datapoint rate limit (one write per WRITE_MIN_INTERVAL) allows it.

Every attempt, including refusals, is logged at INFO.

This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import re
import time
from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final

import aiohttp

from .const import MAX_RESPONSE_BYTES, READ_CHUNK_SIZE, REQUEST_TIMEOUT, WRITE_MIN_INTERVAL
from .datapoints import DATAPOINTS_BY_KEY, WRITABLE, ResolvedDatapoint

_LOGGER = logging.getLogger(__name__)

# Fixed destination for local (non-portal) access.
DESTINATION_ID: Final = "00000000-0000-0000-0000-000000000000"

EP_LOGIN: Final = "Security/Login"
EP_LOGOUT: Final = "Security/Logout"
EP_ALL_DEVICES: Final = "Device/GetAllDevices"
EP_CONFIGS: Final = "Datapoint/GetConfigsByDeviceType"
EP_READ: Final = "Datapoint/ReadValues"

# The ONLY endpoints this integration may ever call, with their HTTP method.
ENDPOINT_ALLOWLIST: Final[Mapping[str, str]] = MappingProxyType(
    {
        EP_LOGIN: "POST",
        EP_LOGOUT: "POST",
        EP_ALL_DEVICES: "GET",
        EP_CONFIGS: "POST",
        EP_READ: "POST",
    }
)


class KermiError(Exception):
    """Base error of the Kermi client."""


class KermiConnectionError(KermiError):
    """The x-center could not be reached or answered with an error."""


class KermiAuthError(KermiError):
    """The x-center rejected the password."""


class KermiReadOnlyError(KermiError):
    """An endpoint outside the read-only allowlist was requested."""


class KermiWriteRefusedError(KermiError):
    """A write was refused by the guard; nothing was sent."""


class KermiWriteError(KermiError):
    """The x-center did not accept a write."""


def normalize_host(host: str) -> str:
    """Strip scheme, path and whitespace from a user supplied host."""
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host.split("/", 1)[0].strip()


_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def is_valid_host(host: str) -> bool:
    """Accept only a bare hostname or IP address with an optional port.

    Rejects user info (``user@host``), paths, queries, spaces and other
    characters that could change where the password is sent.
    """
    name, port = host, None
    if host.startswith("["):  # [IPv6]:port
        end = host.find("]")
        if end == -1:
            return False
        name, rest = host[1:end], host[end + 1 :]
        if rest:
            if not rest.startswith(":"):
                return False
            port = rest[1:]
        try:
            ipaddress.IPv6Address(name)
        except ValueError:
            return False
    else:
        if host.count(":") == 1:
            name, port = host.split(":")
        if not _HOSTNAME.match(name):
            return False
    return port is None or (port.isdigit() and 0 < int(port) < 65536)


def _unwrap(body: Any) -> Any:
    """Return ResponseData of a wrapped x-center answer, checking StatusCode."""
    if isinstance(body, dict) and "ResponseData" in body:
        status = body.get("StatusCode", 0)
        if status not in (0, None):
            raise KermiConnectionError(
                f"x-center returned StatusCode {status}: {body.get('DisplayText')}"
            )
        return body["ResponseData"]
    return body


class KermiClient:
    """Async, read-only client for one x-center."""

    def __init__(
        self,
        host: str,
        password: str,
        session: aiohttp.ClientSession,
        *,
        timeout: float = REQUEST_TIMEOUT,
        release_session: Callable[[], None] | None = None,
        writes_enabled: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialise the client.

        The session must have its own cookie jar created with
        ``aiohttp.CookieJar(unsafe=True)``, because the x-center is addressed
        by IP and keeps its login in a cookie. :meth:`close` releases the
        session with ``release_session`` (Home Assistant sessions must be
        detached, not closed) or closes it if none is given.

        ``writes_enabled`` mirrors the config entry option ``allow_writes``;
        it is fixed for the lifetime of the client (the entry reloads when the
        option changes).
        """
        self._host = normalize_host(host)
        self._password = password
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._logged_in = False
        self._login_lock = asyncio.Lock()
        self._release_session = release_session
        self._writes_enabled = writes_enabled
        self._clock = clock
        self._last_write: dict[str, float] = {}

    @property
    def host(self) -> str:
        """Return the normalised host."""
        return self._host

    def _url(self, endpoint: str) -> str:
        return f"http://{self._host}/api/{endpoint}/{DESTINATION_ID}"

    # ------------------------------------------------------------------ core

    @property
    def writes_enabled(self) -> bool:
        """Whether this client may write at all."""
        return self._writes_enabled

    async def _request(
        self,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
        *,
        allowed: Mapping[str, str] = ENDPOINT_ALLOWLIST,
    ) -> Any:
        """Perform one allowlisted request and return the decoded JSON body.

        Raises KermiReadOnlyError before any I/O for a non-allowlisted endpoint.
        On HTTP 401 the client logs in once more and retries the request once.
        Only write_value passes a different ``allowed`` mapping.
        """
        method = allowed.get(endpoint)
        if method is None:
            raise KermiReadOnlyError(f"Endpoint {endpoint!r} is not allowed (read-only)")

        is_auth_call = endpoint in (EP_LOGIN, EP_LOGOUT)
        if not is_auth_call and not self._logged_in:
            await self._login()

        status, body = await self._send(method, endpoint, payload, allowed)
        if status == 401 and not is_auth_call:
            _LOGGER.debug("Session expired on %s, logging in again", endpoint)
            self._logged_in = False
            await self._login()
            status, body = await self._send(method, endpoint, payload, allowed)
            if status == 401:
                raise KermiConnectionError(f"{endpoint}: still 401 after re-login")
        if endpoint == EP_LOGIN and status in (401, 403):
            raise KermiAuthError("Login rejected by x-center")
        if status >= 400:
            raise KermiConnectionError(f"{endpoint}: HTTP {status}")
        return body

    async def _send(
        self,
        method: str,
        endpoint: str,
        payload: Mapping[str, Any] | None,
        allowed: Mapping[str, str] = ENDPOINT_ALLOWLIST,
    ) -> tuple[int, Any]:
        """Send exactly one HTTP request. Only called by _request."""
        if allowed.get(endpoint) != method:  # defence in depth
            raise KermiReadOnlyError(f"{method} {endpoint!r} is not allowed (read-only)")
        try:
            async with self._session.request(
                method,
                self._url(endpoint),
                json=dict(payload) if method == "POST" and payload is not None else None,
                timeout=self._timeout,
                # Never follow redirects: the password must only go to the
                # host the user configured.
                allow_redirects=False,
                # A fresh connection per request: polls are rare, and stale
                # keep-alive connections after a back-off would fail.
                headers={"Connection": "close"},
            ) as resp:
                if resp.status >= 400:
                    return resp.status, None
                if resp.status >= 300:
                    raise KermiConnectionError(f"{endpoint}: unexpected redirect")
                if (resp.content_length or 0) > MAX_RESPONSE_BYTES:
                    raise KermiConnectionError(f"{endpoint}: response too large")
                # Read the whole body in chunks (a single read() may return
                # only part of it), enforcing the size limit while reading.
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    buf.extend(chunk)
                    if len(buf) > MAX_RESPONSE_BYTES:
                        raise KermiConnectionError(f"{endpoint}: response too large")
                raw = bytes(buf)
                # stdlib json on purpose: the x-center sends bare NaN literals,
                # which strict decoders (e.g. orjson used by HA) reject.
                # JSON is UTF-8 (RFC 8259); tolerate a byte order mark.
                text = raw.decode("utf-8-sig", errors="replace")
                try:
                    body = json.loads(text) if text.strip() else None
                except ValueError as err:
                    raise KermiConnectionError(f"{endpoint}: invalid JSON") from err
                return resp.status, body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KermiConnectionError(f"{endpoint}: {err!r}") from err

    # ------------------------------------------------------------- auth

    async def _login(self) -> None:
        """Log in once; concurrent callers share the same attempt."""
        async with self._login_lock:
            if self._logged_in:
                return
            body = await self._request(EP_LOGIN, {"Password": self._password})
            valid = None
            if isinstance(body, dict):
                valid = body.get("isValid")
                data = body.get("ResponseData")
                if valid is None and isinstance(data, dict):
                    valid = data.get("isValid")
            if valid is None:
                raise KermiConnectionError("Login answer has no isValid: not an x-center?")
            if not valid:
                raise KermiAuthError("Login rejected by x-center")
            self._logged_in = True
            _LOGGER.debug("Logged in to x-center %s", self._host)

    async def login(self) -> None:
        """Log in (no-op if a session is already established)."""
        await self._login()

    async def logout(self) -> None:
        """Log out; errors are ignored because this runs on unload."""
        if not self._logged_in:
            return
        self._logged_in = False
        try:
            await self._request(EP_LOGOUT, {})
        except KermiError as err:
            _LOGGER.debug("Logout failed (ignored): %s", err)

    async def close(self) -> None:
        """Log out and release the HTTP session owned by this client."""
        await self.logout()
        if self._session.closed:
            return
        if self._release_session is not None:
            self._release_session()
        else:
            await self._session.close()

    # ------------------------------------------------------------- writes

    def _refuse(self, key: str, value: Any, reason: str) -> KermiWriteRefusedError:
        _LOGGER.info("Write %s=%r REFUSED: %s", key, value, reason)
        return KermiWriteRefusedError(f"Write {key}={value!r} refused: {reason}")

    @staticmethod
    def _write_refusal(rd: ResolvedDatapoint, value: Any) -> str | None:
        """Return why a write violates guard (b) or (c), or None if it is fine."""
        spec = WRITABLE.get(rd.spec.key)
        # (b) datapoint on the writable allowlist
        if spec is None or DATAPOINTS_BY_KEY.get(rd.spec.key) is not rd.spec:
            return "datapoint is not writable"
        if not rd.is_primary_match:
            # Found via a classic-firmware alternative: never verified, never written.
            return "datapoint matched via classic firmware name (read-only)"
        # (c) value inside our own safety envelope ...
        if spec.allowed_values is not None and (
            isinstance(value, bool) != spec.is_bool or value not in spec.allowed_values
        ):
            return f"value not in {sorted(spec.allowed_values)}"
        if spec.safe_min is not None or spec.safe_max is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return "value is not a number"
            number = float(value)
            if math.isnan(number) or math.isinf(number):
                return "value is not finite"
            if spec.safe_min is not None and number < spec.safe_min:
                return f"below safety minimum {spec.safe_min}"
            if spec.safe_max is not None and number > spec.safe_max:
                return f"above safety maximum {spec.safe_max}"
            if spec.is_int and not number.is_integer():
                return "value must be an integer"
        # ... and inside the live catalogue's bounds
        if spec.needs_catalogue_bounds:
            if rd.min_value is None or rd.max_value is None:
                return "catalogue has no MinValue/MaxValue"
            if not rd.min_value <= float(value) <= rd.max_value:
                return f"outside catalogue range {rd.min_value}..{rd.max_value}"
        return None

    async def write_value(self, rd: ResolvedDatapoint, value: Any) -> None:
        """Write one value. THE ONLY WRITE PATH of the whole integration.

        Refuses before any network I/O unless all guards (a)-(d) hold, see the
        module docstring.
        """
        write_allowlist: Mapping[str, str] = MappingProxyType({"Datapoint/WriteValues": "POST"})
        key = rd.spec.key
        _LOGGER.info("Write %s=%r requested", key, value)

        # (a) writes enabled in the config entry options
        if not self._writes_enabled:
            raise self._refuse(key, value, "writes are disabled (option allow_writes)")

        # (b) writable allowlist and (c) value range, see _write_refusal
        if (reason := self._write_refusal(rd, value)) is not None:
            raise self._refuse(key, value, reason)
        spec = WRITABLE[key]

        # (d) rate limit per datapoint
        now = self._clock()
        last = self._last_write.get(key)
        if last is not None and now - last < WRITE_MIN_INTERVAL:
            wait = WRITE_MIN_INTERVAL - (now - last)
            raise self._refuse(key, value, f"rate limit, next write allowed in {wait:.0f} s")
        self._last_write[key] = now  # an attempt counts, even if it fails below

        sent: Any = value
        if spec.is_int:
            sent = int(value)
        elif spec.is_float:
            sent = float(value)
        payload = {
            "DatapointValues": [
                {
                    "$type": spec.type_name,
                    "DatapointConfigId": rd.config_id,
                    "DeviceId": rd.device_id,
                    "Value": sent,
                }
            ]
        }
        _LOGGER.info("Write %s=%r: sending to x-center", key, sent)
        endpoint = next(iter(write_allowlist))
        body = await self._request(endpoint, payload, allowed=write_allowlist)
        if not isinstance(body, dict) or body.get("StatusCode") != 0:
            status = body.get("StatusCode") if isinstance(body, dict) else None
            text = body.get("DisplayText") if isinstance(body, dict) else None
            _LOGGER.info("Write %s=%r FAILED: StatusCode %s %s", key, sent, status, text)
            raise KermiWriteError(f"x-center rejected write {key}: {status} {text}")
        _LOGGER.info("Write %s=%r: accepted by x-center", key, sent)

    # ------------------------------------------------------------- reads

    async def get_all_devices(self) -> list[dict[str, Any]]:
        """Return the device list of the x-center."""
        data = _unwrap(await self._request(EP_ALL_DEVICES))
        if not isinstance(data, list):
            raise KermiConnectionError("GetAllDevices: unexpected answer")
        return [d for d in data if isinstance(d, dict)]

    async def get_configs_by_device_type(self, device_type: int) -> list[dict[str, Any]]:
        """Return the datapoint catalogue of one device type."""
        data = _unwrap(await self._request(EP_CONFIGS, {"DeviceType": device_type}))
        if not isinstance(data, list):
            raise KermiConnectionError("GetConfigsByDeviceType: unexpected answer")
        return [d for d in data if isinstance(d, dict)]

    async def read_values(
        self, datapoints: Iterable[tuple[str, str]]
    ) -> dict[tuple[str, str], Any]:
        """Read raw values for (DatapointConfigId, DeviceId) pairs.

        Reads per device in chunks of at most READ_CHUNK_SIZE, so a config id
        never appears twice in one request (both buffer modules share the same
        config ids). The result is keyed by lower-cased (config id, device id);
        datapoints the x-center did not return are absent.
        """
        by_device: dict[str, list[str]] = {}
        for cid, did in datapoints:
            cids = by_device.setdefault(did.lower(), [])
            if cid.lower() not in cids:
                cids.append(cid.lower())

        result: dict[tuple[str, str], Any] = {}
        for did, cids in by_device.items():
            for start in range(0, len(cids), READ_CHUNK_SIZE):
                chunk = cids[start : start + READ_CHUNK_SIZE]
                payload = {
                    "DatapointValues": [
                        {"DatapointConfigId": cid, "DeviceId": did} for cid in chunk
                    ]
                }
                items = _unwrap(await self._request(EP_READ, payload)) or []
                if not items:
                    _LOGGER.debug("ReadValues returned no items for %d datapoints", len(chunk))
                wanted = set(chunk)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    cid = str(item.get("DatapointConfigId", "")).lower()
                    item_did = str(item.get("DeviceId") or did).lower()
                    if cid in wanted and item_did == did:
                        result[(cid, did)] = item.get("Value")
        return result
