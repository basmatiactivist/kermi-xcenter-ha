"""Setup, entities, back-off, unload and diagnostics against the fake x-center."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kermi_xcenter.binary_sensor import BINARY_SENSORS
from custom_components.kermi_xcenter.button import BUTTONS
from custom_components.kermi_xcenter.const import CONF_SCAN_INTERVAL, DOMAIN
from custom_components.kermi_xcenter.diagnostics import async_get_config_entry_diagnostics
from custom_components.kermi_xcenter.number import NUMBERS
from custom_components.kermi_xcenter.select import SELECTS
from custom_components.kermi_xcenter.sensor import SENSORS

from .fake_xcenter import PASSWORD, SERIAL, FakeXCenter

UID = SERIAL.lower()
PACKAGE = Path(__file__).parent.parent / "custom_components" / "kermi_xcenter"


async def _setup(hass: HomeAssistant, fake: FakeXCenter, **options) -> MockConfigEntry:
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


def _state(hass: HomeAssistant, platform: str, uid_suffix: str):
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, f"{UID}_{uid_suffix}")
    assert entity_id, uid_suffix
    return hass.states.get(entity_id)


async def test_setup_and_entities(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = await _setup(hass, xcenter)
    assert entry.state is ConfigEntryState.LOADED
    assert xcenter.forbidden == []
    assert xcenter.login_attempts == 1
    assert max(xcenter.read_sizes) <= 40

    assert float(_state(hass, "sensor", "heat_pump_flow_temp").state) == pytest.approx(31.7)
    assert float(_state(hass, "sensor", "heat_pump_thermal_power").state) == pytest.approx(4.07)
    assert float(_state(hass, "sensor", "heat_pump_cop").state) == pytest.approx(7.690351)
    assert _state(hass, "sensor", "heat_pump_cop_dhw").state == STATE_UNAVAILABLE  # NaN
    assert _state(hass, "sensor", "heat_pump_heat_pump_state").state == "4"
    assert _state(hass, "sensor", "heat_pump_state_since").state == "2026-11-16T18:07:39+00:00"
    assert _state(hass, "sensor", "heat_pump_compressor_starts").state == "324"
    assert _state(hass, "sensor", "heat_pump_software_version").state == "3.8.8"
    assert float(_state(hass, "sensor", "heat_pump_flow_rate").state) == pytest.approx(11.43, 0.01)
    assert float(_state(hass, "sensor", "heating_buffer_temp").state) == pytest.approx(26.3)
    assert float(_state(hass, "sensor", "heating_outdoor_temp").state) == pytest.approx(8.8)
    energy = _state(hass, "sensor", "heating_energy_mode")
    assert energy.state == "normal"
    assert energy.attributes["raw_value"] == 2
    assert float(_state(hass, "sensor", "dhw_dhw_temp").state) == pytest.approx(50.9)
    assert _state(hass, "binary_sensor", "heat_pump_heating_active").state == STATE_ON
    assert _state(hass, "binary_sensor", "heat_pump_dhw_active").state == STATE_OFF
    assert _state(hass, "binary_sensor", "heat_pump_global_alarm").state == STATE_OFF
    assert _state(hass, "binary_sensor", "dhw_one_time_charge").state == STATE_OFF
    assert _state(hass, "binary_sensor", "heating_summer_mode").state == STATE_OFF

    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    assert len(entries) == len(SENSORS) + len(BINARY_SENSORS)
    disabled = {e.unique_id for e in entries if e.disabled_by}
    assert f"{UID}_heat_pump_outdoor_temp_hp" in disabled
    assert f"{UID}_heat_pump_flow_temp" not in disabled
    assert {e.domain for e in entries} == {"sensor", "binary_sensor"}

    dev_reg = dr.async_get(hass)
    hp = dev_reg.async_get_device_by_identifier((DOMAIN, f"{UID}_heat_pump"), entry.entry_id)
    assert hp.name == "Kermi Wärmepumpe"
    assert hp.manufacturer == "Kermi"
    assert hp.model == "xchange dynamic pro S AW E"
    assert hp.sw_version == "3.8.8"
    hz = dev_reg.async_get_device_by_identifier((DOMAIN, f"{UID}_heating"), entry.entry_id)
    assert hz.name == "Kermi Heizen"
    assert hz.sw_version == "1.5.33"
    assert dev_reg.async_get_device_by_identifier((DOMAIN, f"{UID}_dhw"), entry.entry_id).name == (
        "Kermi Warmwasser"
    )
    assert len(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)) == 3


async def test_not_connected_temperature(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    xcenter.set_value("x-change", "B16 - Vorlauftemperatur WP", -999.9)
    await _setup(hass, xcenter)
    assert _state(hass, "sensor", "heat_pump_flow_temp").state == STATE_UNAVAILABLE


# Note: polls are triggered with coordinator.async_refresh() instead of
# async_fire_time_changed, because the latter also fires aiohttp's internal
# timeout handles of the local test server and breaks its connections.


async def test_relogin_during_polling(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = await _setup(hass, xcenter)
    xcenter.expire_sessions()
    xcenter.set_value("x-change", "B16 - Vorlauftemperatur WP", 40.5)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert xcenter.login_attempts == 2
    assert float(_state(hass, "sensor", "heat_pump_flow_temp").state) == 40.5
    assert entry.runtime_data.failures == 0


async def test_backoff_and_recovery(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = await _setup(hass, xcenter, **{CONF_SCAN_INTERVAL: 20})
    coordinator = entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=20)

    xcenter.fail_all = True
    for seconds in [40, 80, 160, 320, 640, 900, 900]:
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.update_interval == timedelta(seconds=seconds)
    assert _state(hass, "sensor", "heat_pump_flow_temp").state == STATE_UNAVAILABLE
    assert xcenter.login_attempts == 1  # failures do not trigger new logins

    xcenter.fail_all = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=20)
    assert coordinator.failures == 0
    assert float(_state(hass, "sensor", "heat_pump_flow_temp").state) == pytest.approx(31.7)


async def test_auth_failure_starts_reauth_and_stops_polling(
    hass: HomeAssistant, xcenter: FakeXCenter
) -> None:
    entry = await _setup(hass, xcenter)
    coordinator = entry.runtime_data
    xcenter.expire_sessions()
    xcenter.password = "changed-on-device"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert xcenter.login_attempts == 2
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)
    # HA does not schedule another poll after an auth failure, so the
    # x-center is not hammered with failing logins (lock-out protection).
    assert coordinator._unsub_refresh is None
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_wrong_password(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    xcenter.password = "other"
    entry = await _setup(hass, xcenter)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert xcenter.login_attempts == 1


async def test_setup_unreachable(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    xcenter.fail_all = True
    entry = await _setup(hass, xcenter)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_logs_out(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = await _setup(hass, xcenter)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert xcenter.logouts == 1
    assert xcenter.forbidden == []


async def test_diagnostics_redacted(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = await _setup(hass, xcenter)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(diag)
    assert PASSWORD not in json.dumps(diag["entry"]["data"])
    assert diag["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert SERIAL not in text
    assert UID not in text
    for dev in xcenter.devices:
        assert dev["DeviceId"] not in text
        assert dev["DeviceId"].lower() not in text
    assert diag["values"]["hp_flow_temp"] == pytest.approx(31.7)
    assert diag["values"]["hp_serial"] == "**REDACTED**"
    assert xcenter.host not in text
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert "10.11.12.13" not in text  # unknown device fields are dropped
    assert {key for dev in diag["devices"] for key in dev} <= {"Name", "DeviceType", "DeviceId"}


def test_translations_complete() -> None:
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((PACKAGE / name).read_text("utf-8"))
        for desc in SENSORS:
            assert desc.translation_key in data["entity"]["sensor"], (name, desc.key)
        for desc in BINARY_SENSORS:
            assert desc.translation_key in data["entity"]["binary_sensor"], (name, desc.key)
        for platform, descs in (("button", BUTTONS), ("number", NUMBERS), ("select", SELECTS)):
            for desc in descs:
                assert desc.translation_key in data["entity"][platform], (name, desc.key)
        assert set(data["entity"]["select"]["energy_mode_control"]["state"]) == set(
            SELECTS[0].options
        )
        assert "confirm_writes" in data["options"]["step"]
        for path in PACKAGE.glob("*.py"):
            for key in re.findall(r'translation_key="([a-z_]+)"', path.read_text("utf-8")):
                if "translation_domain" in path.read_text("utf-8"):
                    in_entities = any(key in v for v in data["entity"].values())
                    assert key in data["exceptions"] or in_entities, (name, path.name, key)
        states = data["entity"]["sensor"]["energy_mode"]["state"]
        assert set(states) == {"off", "eco", "normal", "comfort", "custom"}
    de = json.loads((PACKAGE / "translations/de.json").read_text("utf-8"))
    assert de["entity"]["sensor"]["energy_mode"]["state"]["comfort"] == "Komfort"
    assert de["entity"]["sensor"]["flow_temp"]["name"] == "Vorlauftemperatur (B16)"
