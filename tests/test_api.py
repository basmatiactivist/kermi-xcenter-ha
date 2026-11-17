"""Client tests against the local fake x-center (127.0.0.1 only)."""

from __future__ import annotations

import math

import aiohttp
import pytest

from custom_components.kermi_xcenter.api import (
    KermiAuthError,
    KermiClient,
    KermiConnectionError,
    is_valid_host,
    normalize_host,
)
from custom_components.kermi_xcenter.identify import async_determine_unique_id

from .fake_xcenter import PASSWORD, SERIAL, FakeXCenter


def _client(fake: FakeXCenter, password: str = PASSWORD) -> KermiClient:
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return KermiClient(fake.host, password, session, timeout=5)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.0.2.10", "192.0.2.10"),
        (" http://192.0.2.10/ ", "192.0.2.10"),
        ("https://xcenter.local:8080/api", "xcenter.local:8080"),
    ],
)
def test_normalize_host(raw: str, expected: str) -> None:
    assert normalize_host(raw) == expected


async def test_login_and_devices(xcenter: FakeXCenter) -> None:
    client = _client(xcenter)
    try:
        devices = await client.get_all_devices()  # logs in implicitly
        assert {d["Name"] for d in devices} >= {"Heizen (50)", "x-change dynamic pro (40)"}
        await client.get_all_devices()
        assert xcenter.login_attempts == 1  # no repeated logins
    finally:
        await client.close()
    assert xcenter.logouts == 1
    assert xcenter.forbidden == []


async def test_invalid_password(xcenter: FakeXCenter) -> None:
    client = _client(xcenter, "wrong")
    try:
        with pytest.raises(KermiAuthError):
            await client.login()
        with pytest.raises(KermiAuthError):
            await client.get_all_devices()
    finally:
        await client.close()
    assert xcenter.logouts == 0  # never logged in, so no logout


async def test_relogin_once_after_401(xcenter: FakeXCenter) -> None:
    client = _client(xcenter)
    try:
        await client.get_all_devices()
        xcenter.expire_sessions()
        devices = await client.get_all_devices()
        assert devices
        assert xcenter.login_attempts == 2
    finally:
        await client.close()


async def test_relogin_rejected_raises_auth_error(xcenter: FakeXCenter) -> None:
    client = _client(xcenter)
    try:
        await client.get_all_devices()
        xcenter.expire_sessions()
        xcenter.password = "changed"
        with pytest.raises(KermiAuthError):
            await client.get_all_devices()
        assert xcenter.login_attempts == 2
    finally:
        await client.close()


async def test_chunked_reads_per_device(xcenter: FakeXCenter) -> None:
    hp_id = xcenter.device_id("x-change")
    hz_id = xcenter.device_id("Heizen")
    pairs = [(c["DatapointConfigId"], hp_id) for c in xcenter.configs[97]]
    pairs += [(c["DatapointConfigId"], hz_id) for c in xcenter.configs[95]]
    client = _client(xcenter)
    try:
        values = await client.read_values(pairs)
    finally:
        await client.close()
    assert len(pairs) == 116 + 80
    assert xcenter.read_sizes == [40, 40, 36, 40, 40]
    assert len(values) == len(pairs)
    cop_twe = next(c for c in xcenter.configs[97] if c["DisplayName"] == "aktueller COP Twe")
    assert math.isnan(values[(cop_twe["DatapointConfigId"].lower(), hp_id.lower())])


async def test_status_code_error(xcenter: FakeXCenter) -> None:
    xcenter.status_code = 5
    client = _client(xcenter)
    try:
        with pytest.raises(KermiConnectionError):
            await client.get_all_devices()
    finally:
        await client.close()


async def test_http_error(xcenter: FakeXCenter) -> None:
    client = _client(xcenter)
    try:
        await client.login()
        xcenter.fail_all = True
        with pytest.raises(KermiConnectionError):
            await client.get_all_devices()
    finally:
        await client.close()


async def test_unreachable(socket_enabled) -> None:
    fake = FakeXCenter()
    await fake.start()
    host = fake.host
    await fake.stop()
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    client = KermiClient(host, PASSWORD, session, timeout=2)
    try:
        with pytest.raises(KermiConnectionError):
            await client.login()
    finally:
        await client.close()


async def test_unique_id_from_heat_pump_serial_datapoint(xcenter: FakeXCenter) -> None:
    client = _client(xcenter)
    try:
        uid = await async_determine_unique_id(client, await client.get_all_devices())
    finally:
        await client.close()
    assert uid == SERIAL.lower()


async def test_unique_id_from_device_list(socket_enabled) -> None:
    fake = FakeXCenter(device_serial="IF-0042")
    await fake.start()
    client = _client(fake)
    try:
        uid = await async_determine_unique_id(client, await client.get_all_devices())
    finally:
        await client.close()
        await fake.stop()
    assert uid == "if-0042"
    assert ("POST", "/api/Datapoint/ReadValues/00000000-0000-0000-0000-000000000000") not in (
        fake.requests
    )


async def test_unique_id_falls_back_to_interface_device_id(xcenter: FakeXCenter) -> None:
    xcenter.set_value("x-change", "Seriennummer", "")
    client = _client(xcenter)
    try:
        uid = await async_determine_unique_id(client, await client.get_all_devices())
    finally:
        await client.close()
    assert uid == xcenter.device_id("Interfacemodul").lower()


@pytest.mark.parametrize(
    ("host", "valid"),
    [
        ("192.168.1.50", True),
        ("xcenter.local", True),
        ("xcenter:8080", True),
        ("[fe80::1]:80", True),
        ("user@192.168.1.50", False),
        ("a b", False),
        ("host?x=1", False),
        ("host#frag", False),
        ("host:0", False),
        ("host:70000", False),
        ("[::1", False),
        ("", False),
    ],
)
def test_is_valid_host(host: str, valid: bool) -> None:
    assert is_valid_host(host) is valid


async def test_redirects_are_not_followed(xcenter: FakeXCenter) -> None:
    """The password must never be sent to a redirect target."""
    xcenter.redirect_login = True
    client = _client(xcenter)
    try:
        with pytest.raises(KermiConnectionError, match="redirect"):
            await client.login()
    finally:
        await client.close()
    assert xcenter.forbidden == []  # /elsewhere was never requested


async def test_oversized_response_rejected(xcenter: FakeXCenter) -> None:
    xcenter.huge_device_list = True
    client = _client(xcenter)
    try:
        with pytest.raises(KermiConnectionError, match="too large"):
            await client.get_all_devices()
    finally:
        await client.close()


async def test_body_arriving_in_pieces(xcenter: FakeXCenter) -> None:
    """A real network delivers bodies in several pieces; all must be read."""
    xcenter.chunked = True
    hp_id = xcenter.device_id("x-change")
    client = _client(xcenter)
    try:
        devices = await client.get_all_devices()
        values = await client.read_values(
            [(c["DatapointConfigId"], hp_id) for c in xcenter.configs[97]]
        )
    finally:
        await client.close()
    assert len(devices) == 4
    assert len(values) == 116


async def test_non_xcenter_login_answer_is_not_a_password_error(xcenter: FakeXCenter) -> None:
    """A device that answers without isValid is 'cannot connect', not 'wrong password'."""
    client = _client(xcenter)
    original = xcenter._json

    def no_is_valid(data, status=200):
        if isinstance(data, dict) and "isValid" in data:
            data = {"hello": "world"}
        return original(data, status)

    xcenter._json = no_is_valid
    try:
        with pytest.raises(KermiConnectionError, match="isValid"):
            await client.login()
    finally:
        await client.close()
