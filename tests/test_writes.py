"""The guarded write path (mock server only; never used on the real unit)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kermi_xcenter.api import (
    KermiClient,
    KermiWriteError,
    KermiWriteRefusedError,
)
from custom_components.kermi_xcenter.const import CONF_ALLOW_WRITES, DOMAIN, WRITE_MIN_INTERVAL
from custom_components.kermi_xcenter.datapoints import (
    ResolvedDatapoint,
    match_role_devices,
    resolve_datapoints,
)

from .fake_xcenter import PASSWORD, SERIAL, FakeXCenter

UID = SERIAL.lower()
NET = "BMS.Shared.DatapointCore.DatapointValue`1[[System.{}, mscorlib]], BMS.Shared"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _resolved(fake: FakeXCenter | None = None) -> dict[str, ResolvedDatapoint]:
    fake = fake or FakeXCenter()
    return resolve_datapoints(match_role_devices(fake.devices), fake.configs)


def _offline_client(*, writes_enabled: bool) -> tuple[KermiClient, MagicMock]:
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request.side_effect = AssertionError("network I/O must not happen")
    client = KermiClient("192.0.2.1", "pw", session, writes_enabled=writes_enabled)
    client._logged_in = True
    return client, session


def _live_client(fake: FakeXCenter, clock: Clock | None = None) -> KermiClient:
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return KermiClient(
        fake.host, PASSWORD, session, timeout=5, writes_enabled=True, clock=clock or Clock()
    )


# --------------------------------------------------------------- guard (a)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ww_one_time_charge", True),
        ("ww_one_time_setpoint", 50),
        ("ww_setpoint_constant", 48),
        ("hz_energy_mode", 3),
    ],
)
async def test_writes_disabled_refuses_before_io(key: str, value, caplog) -> None:
    client, session = _offline_client(writes_enabled=False)
    caplog.set_level(logging.INFO)
    with pytest.raises(KermiWriteRefusedError, match="disabled"):
        await client.write_value(_resolved()[key], value)
    session.request.assert_not_called()
    assert "REFUSED" in caplog.text


def test_default_client_cannot_write() -> None:
    session = MagicMock(spec=aiohttp.ClientSession)
    assert KermiClient("192.0.2.1", "pw", session).writes_enabled is False


# --------------------------------------------------------------- guard (b)


@pytest.mark.parametrize(
    "key",
    ["hz_circuit_setpoint", "hz_buffer_setpoint", "hz_summer_mode", "ww_setpoint", "hp_state"],
)
async def test_non_allowlisted_datapoint_refused(key: str) -> None:
    client, session = _offline_client(writes_enabled=True)
    with pytest.raises(KermiWriteRefusedError, match="not writable"):
        await client.write_value(_resolved()[key], 45)
    session.request.assert_not_called()


# --------------------------------------------------------------- guard (c)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ww_one_time_setpoint", 39.9),
        ("ww_one_time_setpoint", 55.1),
        ("ww_one_time_setpoint", float("nan")),
        ("ww_one_time_setpoint", float("inf")),
        ("ww_one_time_setpoint", "50"),
        ("ww_one_time_setpoint", True),
        ("ww_setpoint_constant", 0),
        ("ww_setpoint_constant", 85),
        ("ww_setpoint_constant", -999.9),
        ("hz_energy_mode", 0),  # off is never allowed
        ("hz_energy_mode", 5),
        ("hz_energy_mode", 2.5),
        ("hz_energy_mode", True),
        ("ww_one_time_charge", False),
        ("ww_one_time_charge", 1),
        ("ww_one_time_charge", "true"),
    ],
)
async def test_out_of_range_refused(key: str, value) -> None:
    client, session = _offline_client(writes_enabled=True)
    with pytest.raises(KermiWriteRefusedError):
        await client.write_value(_resolved()[key], value)
    session.request.assert_not_called()


async def test_missing_catalogue_bounds_refused() -> None:
    fake = FakeXCenter()
    for cfgs in fake.configs.values():
        for cfg in cfgs:
            cfg.pop("MinValue", None)
            cfg.pop("MaxValue", None)
    client, session = _offline_client(writes_enabled=True)
    with pytest.raises(KermiWriteRefusedError, match="MinValue/MaxValue"):
        await client.write_value(_resolved(fake)["ww_setpoint_constant"], 48)
    session.request.assert_not_called()


async def test_tighter_catalogue_bounds_win() -> None:
    fake = FakeXCenter()
    for cfg in fake.configs[95]:
        if cfg["WellKnownName"] == "BufferSystem_TemperatureSetpointTwe":
            cfg["MaxValue"] = 50
    client, session = _offline_client(writes_enabled=True)
    with pytest.raises(KermiWriteRefusedError, match="catalogue range"):
        await client.write_value(_resolved(fake)["ww_setpoint_constant"], 52)
    session.request.assert_not_called()


# --------------------------------------------------------------- guard (d) + I/O


async def test_write_payload_and_rate_limit(xcenter: FakeXCenter, caplog) -> None:
    caplog.set_level(logging.INFO)
    clock = Clock()
    client = _live_client(xcenter, clock)
    resolved = _resolved(xcenter)
    try:
        await client.write_value(resolved["ww_setpoint_constant"], 48)
        assert xcenter.writes[-1] == {
            "$type": NET.format("Single"),
            "DatapointConfigId": resolved["ww_setpoint_constant"].config_id,
            "DeviceId": xcenter.device_id("Trinkwasser").lower(),
            "Value": 48.0,
        }
        # second write of the same datapoint within 5 minutes: refused, nothing sent
        clock.now += WRITE_MIN_INTERVAL - 1
        with pytest.raises(KermiWriteRefusedError, match="rate limit"):
            await client.write_value(resolved["ww_setpoint_constant"], 49)
        assert len(xcenter.writes) == 1
        # other datapoints have their own limit
        await client.write_value(resolved["hz_energy_mode"], 3)
        assert xcenter.writes[-1]["Value"] == 3
        assert xcenter.writes[-1]["$type"] == NET.format("Int32")
        assert xcenter.writes[-1]["DeviceId"] == xcenter.device_id("Heizen").lower()
        await client.write_value(resolved["ww_one_time_charge"], True)
        assert xcenter.writes[-1]["Value"] is True
        assert xcenter.writes[-1]["$type"] == NET.format("Boolean")
        # after the interval the datapoint may be written again
        clock.now += 1
        await client.write_value(resolved["ww_setpoint_constant"], 49)
        assert xcenter.writes[-1]["Value"] == 49.0
    finally:
        await client.close()
    assert len(xcenter.writes) == 4
    assert caplog.text.count("accepted by x-center") == 4
    assert "rate limit" in caplog.text


async def test_rejected_write_still_counts_for_rate_limit(xcenter: FakeXCenter) -> None:
    xcenter.write_status_code = 3
    clock = Clock()
    client = _live_client(xcenter, clock)
    resolved = _resolved(xcenter)
    try:
        with pytest.raises(KermiWriteError):
            await client.write_value(resolved["ww_one_time_setpoint"], 45)
        with pytest.raises(KermiWriteRefusedError, match="rate limit"):
            await client.write_value(resolved["ww_one_time_setpoint"], 45)
    finally:
        await client.close()
    assert len(xcenter.writes) == 1


# --------------------------------------------------------------- HA entities


async def _setup(hass: HomeAssistant, fake: FakeXCenter, *, writes: bool | None):
    options = {} if writes is None else {CONF_ALLOW_WRITES: writes}
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UID,
        data={CONF_HOST: fake.host, CONF_PASSWORD: PASSWORD},
        options=options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _domains(hass: HomeAssistant, entry) -> set[str]:
    return {e.domain for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}


@pytest.mark.parametrize("writes", [None, False])
async def test_no_control_entities_without_allow_writes(
    hass: HomeAssistant, xcenter: FakeXCenter, writes
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UID,
        data={CONF_HOST: xcenter.host, CONF_PASSWORD: PASSWORD},
        options={} if writes is None else {CONF_ALLOW_WRITES: writes},
    )
    entry.add_to_hass(hass)
    # a stale control entity from an earlier "writes on" period must disappear
    er.async_get(hass).async_get_or_create(
        "button",
        DOMAIN,
        f"{UID}_dhw_dhw_one_time_charge_start",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _domains(hass, entry) == {"sensor", "binary_sensor"}
    assert not hass.states.async_entity_ids(("button", "number", "select"))
    assert entry.runtime_data.client.writes_enabled is False
    assert xcenter.writes == []


async def test_control_entities_with_allow_writes(
    hass: HomeAssistant, xcenter: FakeXCenter
) -> None:
    entry = await _setup(hass, xcenter, writes=True)
    assert _domains(hass, entry) == {"sensor", "binary_sensor", "button", "number", "select"}
    ent_reg = er.async_get(hass)

    def eid(domain: str, suffix: str) -> str:
        entity_id = ent_reg.async_get_entity_id(domain, DOMAIN, f"{UID}_{suffix}")
        assert entity_id, suffix
        return entity_id

    button = eid("button", "dhw_dhw_one_time_charge_start")
    one_time = eid("number", "dhw_dhw_one_time_setpoint_control")
    dhw_set = eid("number", "dhw_dhw_setpoint_control")
    mode = eid("select", "heating_energy_mode_control")
    assert len(ent_reg.entities.get_entries_for_config_entry_id(entry.entry_id)) > 4

    assert hass.states.get(dhw_set).state == "53.0"
    assert hass.states.get(dhw_set).attributes["min"] == 40
    assert hass.states.get(dhw_set).attributes["max"] == 55
    assert hass.states.get(mode).state == "normal"
    assert hass.states.get(mode).attributes["options"] == ["eco", "normal", "comfort", "custom"]

    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert xcenter.writes[-1]["Value"] is True

    await hass.services.async_call(
        "select", "select_option", {"entity_id": mode, "option": "comfort"}, blocking=True
    )
    assert xcenter.writes[-1]["Value"] == 3
    await hass.async_block_till_done()
    assert hass.states.get(mode).state == "comfort"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": one_time, "value": 45}, blocking=True
    )
    assert xcenter.writes[-1]["Value"] == 45.0

    # outside the safety range: rejected by HA before our code, nothing sent
    count = len(xcenter.writes)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": dhw_set, "value": 60}, blocking=True
        )
    # rate limit surfaces as an error in the UI
    with pytest.raises(HomeAssistantError, match="rate limit"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": one_time, "value": 46}, blocking=True
        )
    assert len(xcenter.writes) == count

    # switching writes off again removes all control entities
    hass.config_entries.async_update_entry(entry, options={CONF_ALLOW_WRITES: False})
    await hass.async_block_till_done()
    assert _domains(hass, entry) == {"sensor", "binary_sensor"}
    assert xcenter.forbidden == []


async def test_spoofed_datapoint_refused() -> None:
    """A writable key on a hand-made spec (e.g. another GUID) is refused."""
    from dataclasses import replace

    real = _resolved()["ww_setpoint_constant"]
    fake_spec = replace(real.spec, wkn="HeatingCircuit_TemperatureAdjust")
    spoofed = replace(real, spec=fake_spec, config_id="ffffffff-0000-0000-0000-000000000000")
    client, session = _offline_client(writes_enabled=True)
    with pytest.raises(KermiWriteRefusedError, match="not writable"):
        await client.write_value(spoofed, 48)
    session.request.assert_not_called()
