"""Resolution of datapoints from the real (anonymised) catalogue and value conversion."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.kermi_xcenter.datapoints import (
    DATAPOINTS,
    DATAPOINTS_BY_KEY,
    ENERGY_MODES,
    Role,
    convert_value,
    match_role_devices,
    resolve_datapoints,
)

from .fake_xcenter import FakeXCenter


@pytest.fixture
def fake() -> FakeXCenter:
    return FakeXCenter()


def test_roles_matched(fake: FakeXCenter) -> None:
    roles = match_role_devices(fake.devices)
    assert roles[Role.HEAT_PUMP]["Name"] == "x-change dynamic pro (40)"
    assert roles[Role.HEATING]["Name"] == "Heizen (50)"
    assert roles[Role.DHW]["Name"] == "Trinkwassererwärmung (51)"


def test_every_datapoint_resolves(fake: FakeXCenter) -> None:
    resolved = resolve_datapoints(match_role_devices(fake.devices), fake.configs)
    classic_only = {
        dp.key for dp in DATAPOINTS if (dp.wkn or "").startswith("HP_") and not dp.display_name
    }
    assert classic_only == {
        "hp_energy_electric_total",
        "hp_energy_heat_total",
        "hp_energy_electric_heating",
        "hp_energy_electric_dhw",
        "hp_scop",
        "hp_cop_heating_avg",
    }
    assert set(resolved) == {dp.key for dp in DATAPOINTS} - classic_only
    assert all(rd.is_primary_match for rd in resolved.values())
    assert len({dp.key for dp in DATAPOINTS}) == len(DATAPOINTS)
    for key, rd in resolved.items():
        assert (rd.config_id, rd.device_id) in fake.values, key
        if rd.spec.display_name:  # WKN and DisplayName must point at the same datapoint
            assert rd.display_name == rd.spec.display_name, key
    assert resolved["ww_temp"].device_id == fake.device_id("Trinkwasser").lower()
    assert resolved["hz_buffer_temp"].device_id == fake.device_id("Heizen").lower()
    # buffer modules share config ids, but not device ids
    assert resolved["ww_sw_major"].config_id == resolved["hz_sw_major"].config_id


def test_resolution_by_display_name_only(fake: FakeXCenter) -> None:
    for cfg in fake.configs[97]:
        cfg["WellKnownName"] = None
    resolved = resolve_datapoints(match_role_devices(fake.devices), fake.configs)
    assert resolved["hp_flow_temp"].display_name == "B16 - Vorlauftemperatur WP"
    assert resolved["hp_heating_active"].display_name == "Heizen"


def test_missing_device_skips_role(fake: FakeXCenter) -> None:
    devices = [d for d in fake.devices if "Trinkwasser" not in d["Name"]]
    resolved = resolve_datapoints(match_role_devices(devices), fake.configs)
    assert not any(rd.spec.role is Role.DHW for rd in resolved.values())
    assert "hp_cop" in resolved


def _values(fake: FakeXCenter) -> dict:
    resolved = resolve_datapoints(match_role_devices(fake.devices), fake.configs)
    return {
        key: convert_value(rd.spec, fake.values[(rd.config_id, rd.device_id)])
        for key, rd in resolved.items()
    }


def test_values_from_catalogue(fake: FakeXCenter) -> None:
    v = _values(fake)
    assert v["hp_flow_temp"] == pytest.approx(31.7)
    assert v["hp_cop"] == pytest.approx(7.690351)
    assert v["hp_cop_dhw"] is None  # NaN
    assert v["hp_compressor_starts"] == 324
    assert v["hp_heating_active"] is True
    assert v["hp_dhw_active"] is False
    assert v["hp_state"] == 4
    assert v["hp_state_since"] == datetime(2026, 11, 16, 18, 7, 39, 99350, tzinfo=UTC)
    assert v["hp_model"] == "xchange dynamic pro S AW E"
    assert v["hz_energy_mode"] == 2
    assert ENERGY_MODES[v["hz_energy_mode"]] == "normal"
    assert v["ww_temp"] == pytest.approx(50.9)
    assert v["ww_one_time_charge"] is False
    assert v["hz_summer_mode"] is False


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("hp_flow_temp", -999.9, None),
        ("hp_flow_temp", -999.89999, None),
        ("hp_flow_temp", -12.5, -12.5),
        ("hp_cop", float("nan"), None),
        ("hp_cop", "NaN", None),
        ("hp_cop", float("inf"), None),
        ("hp_cop", "3.5", 3.5),
        ("hp_cop", None, None),
        ("hp_spread", -999.9, -999.9),  # not a temperature sensor
        ("hp_compressor_starts", 324.0, 324),
        ("hp_heating_active", 1, True),
        ("hp_heating_active", "false", False),
        ("hp_heating_active", "garbage", None),
        ("hp_model", "  ", None),
        ("hp_state_since", "0001-01-01T00:00:00", None),
        ("hp_state_since", "not a date", None),
    ],
)
def test_convert_value(key: str, raw, expected) -> None:
    assert convert_value(DATAPOINTS_BY_KEY[key], raw) == expected


def _classic_fake() -> tuple[list[dict], dict[int, list[dict]]]:
    """A synthetic classic-firmware unit: one device, HP_* WellKnownNames."""
    names = {
        "HP_HeatpumpState": "a",
        "HP_HeatOutput": "b",
        "HP_AktuelleMotorleistungKW": "c",
        "HP_TotalCOP": "d",
        "HP_TWETempIst": "e",
        "HP_TWESollEinmal": "f",
        "HP_StrommengeGesamt": "g",
        "HP_WaermemengeGesamt": "h",
        "HP_EnergyModeHk1": "i",
        "Aussentemperatur": "j",
    }
    configs = [
        {
            "DatapointConfigId": f"0000000{cid}-0000-0000-0000-000000000000",
            "WellKnownName": wkn,
            "DisplayName": wkn,
            "MinValue": 0,
            "MaxValue": 85,
        }
        for wkn, cid in names.items()
    ]
    devices = [
        {"DeviceId": "00000000-0000-0000-0000-00000000000a", "DeviceType": 0, "Name": "IFM"},
        {"DeviceId": "00000000-0000-0000-0000-00000000000b", "DeviceType": 61, "Name": "Anlage"},
    ]
    return devices, {61: configs}


def test_classic_firmware_resolution() -> None:
    devices, configs = _classic_fake()
    roles = match_role_devices(devices)
    assert roles == {}  # neither names nor DeviceType 97 match
    resolved = resolve_datapoints(roles, configs, all_devices=devices)
    assert {
        "hp_state",
        "hp_thermal_power",
        "hp_electrical_power",
        "hp_cop",
        "ww_temp",
        "ww_one_time_setpoint",
        "hp_energy_electric_total",
        "hp_energy_heat_total",
        "hz_energy_mode",
        "hz_outdoor_temp",
    } == set(resolved)
    assert resolved["ww_temp"].matched_wkn == "HP_TWETempIst"
    assert not resolved["ww_temp"].is_primary_match
    assert resolved["hp_energy_heat_total"].is_primary_match  # classic-only spec
    assert all(rd.device_id.endswith("b") for rd in resolved.values())


def test_rubin_role_devices_are_not_searched_across() -> None:
    """With all roles present, DisplayName matches never jump to another device."""
    fake = FakeXCenter()
    resolved = resolve_datapoints(
        match_role_devices(fake.devices), fake.configs, all_devices=fake.devices
    )
    assert resolved["ww_temp"].device_id == fake.device_id("Trinkwasser").lower()
    assert resolved["hz_buffer_temp"].device_id == fake.device_id("Heizen").lower()
