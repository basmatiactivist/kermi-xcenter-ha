"""Datapoints of the x-center and their resolution from the live catalogue.

No GUIDs are hard-coded: at setup the integration loads the catalogue with
Datapoint/GetConfigsByDeviceType and picks each datapoint by
(device name substring, WellKnownName or exact DisplayName). Only datapoints
that were found in the live catalogue are ever requested from ReadValues.

This module has no Home Assistant imports.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class Role(StrEnum):
    """The Kermi devices this integration creates HA devices for."""

    HEAT_PUMP = "heat_pump"
    HEATING = "heating"
    DHW = "dhw"


# How each role is found in Device/GetAllDevices (case-insensitive substring of
# the device Name, plus the expected DeviceType as fallback).
ROLE_MATCH: dict[Role, tuple[tuple[str, ...], int | None]] = {
    Role.HEAT_PUMP: (("x-change",), 97),
    Role.HEATING: (("heizen",), None),
    Role.DHW: (("trinkwasser",), None),
}

ROLE_DEVICE_NAMES: dict[Role, str] = {
    Role.HEAT_PUMP: "Kermi Wärmepumpe",
    Role.HEATING: "Kermi Heizen",
    Role.DHW: "Kermi Warmwasser",
}


class Kind(StrEnum):
    """How a raw value is converted."""

    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STR = "str"
    TIMESTAMP = "timestamp"


@dataclass(frozen=True, kw_only=True)
class Datapoint:
    """One datapoint, identified by WellKnownName and/or exact DisplayName."""

    key: str
    role: Role
    kind: Kind
    wkn: str | None = None
    display_name: str | None = None
    # Treat -999.9 as "sensor not connected".
    temperature: bool = False
    # WellKnownNames of the classic (non-Rubin) firmware, tried after ``wkn``.
    # Experimental and read-only: never used for writes.
    alt_wkns: tuple[str, ...] = ()
    # Value never changes at runtime (model, serial, version): read once at setup.
    static: bool = False


@dataclass(frozen=True)
class ResolvedDatapoint:
    """A datapoint found in the live catalogue."""

    spec: Datapoint
    config_id: str
    device_id: str
    display_name: str | None
    unit: str | None
    # Bounds from the live catalogue (None if the catalogue has none).
    min_value: float | None = None
    max_value: float | None = None
    # The WellKnownName that matched (None when matched by DisplayName).
    matched_wkn: str | None = None

    @property
    def is_primary_match(self) -> bool:
        """True unless the datapoint was found via a classic-firmware alternative."""
        return self.matched_wkn is None or self.matched_wkn == self.spec.wkn


def _dp(
    key: str,
    role: Role,
    kind: Kind,
    wkn: str | None = None,
    name: str | None = None,
    *,
    temp: bool = False,
) -> Datapoint:
    return Datapoint(key=key, role=role, kind=kind, wkn=wkn, display_name=name, temperature=temp)


# (key, WellKnownName, exact DisplayName) of conditions that keep the
# compressor from starting.
COMPRESSOR_BLOCKS: tuple[tuple[str, str | None, str], ...] = (
    (
        "hp_block_min_pause_starts",
        None,
        "Verdichtersperre durch Mindeststandzeit zwischen zwei Verdichterstarts",
    ),
    (
        "hp_block_min_pause_stop",
        None,
        "Verdichtersperre durch Mindeststandzeit zwischen Verdichterstopp und -start",
    ),
    ("hp_block_oil_temp", None, "Sperre Verdichterstart durch niedrige Öltemperatur"),
    (
        "hp_block_defrost_temp",
        "Rubin_CompressorBlockLowTemperaturSecondaryDefrosting",
        "Verdichtersperre durch min. Ladekreistemperaturen Abtauung",
    ),
    ("hp_block_after_defrost", None, "Blockierung nach Abtauung"),
    ("hp_block_controller", None, "Verdichterbetrieb wird durch Einstellung des Reglers blockiert"),
    ("hp_block_max_return", None, "Blockierung WP durch max. Rücklauftemperatur"),
    ("hp_block_min_return", None, "Blockierung WP durch min. Rücklauftemperatur"),
    (
        "hp_block_source_high",
        "Rubin_CompressorBlockHighTemperaturePrimary",
        "hohe EQ Temperatur (Heizen)",
    ),
    (
        "hp_block_source_low",
        "Rubin_CompressorBlockLowTemperaturePrimary",
        "geringe EQ Temperatur (Heizen)",
    ),
    (
        "hp_block_return_high",
        "Rubin_CompressorBlockHighTemperatureSecondary",
        "hohe Rücklauftemperatur WP (Heizen)",
    ),
    (
        "hp_block_return_low",
        "Rubin_CompressorBlockLowTemperatureSecondary",
        "geringe Rücklauftemperatur WP (Heizen)",
    ),
    ("hp_block_pressure_diff_high", None, "hohe Druckdifferenz (Heizen)"),
    ("hp_block_high_pressure_high", None, "hoher Hochdruck (Heizen)"),
    ("hp_block_motor_overload", None, "Überlast Verdichter Motor (Heizen)"),
    ("hp_block_low_pressure_high", None, "hoher Niederdruck (Heizen)"),
    ("hp_block_ratio_low", None, "geringes Verdichtungsverhältnis (Heizen)"),
    ("hp_block_pressure_delta_low", None, "geringes Druckdelta (Heizen)"),
    ("hp_block_high_pressure_low", None, "geringer Hochdruck (Heizen)"),
    ("hp_block_low_pressure_low", None, "geringer Niederdruck (Heizen)"),
    ("hp_block_ratio_high", None, "hohes Verdichtungsverhältnis (Heizen)"),
)
COMPRESSOR_BLOCK_KEYS: tuple[str, ...] = tuple(key for key, _, _ in COMPRESSOR_BLOCKS)

HP, HZ, WW = Role.HEAT_PUMP, Role.HEATING, Role.DHW
F, N, B, S, T = Kind.FLOAT, Kind.INT, Kind.BOOL, Kind.STR, Kind.TIMESTAMP

_BASE_DATAPOINTS: tuple[Datapoint, ...] = (
    # --- heat pump: power / efficiency
    _dp("hp_thermal_power", HP, F, "Rubin_CurrentOutputCapacity", "Aktuelle Leistung"),
    _dp(
        "hp_thermal_power_heating",
        HP,
        F,
        "Rubin_CurrentOutputCapacityHeating",
        "Aktuelle Leistung Heizen",
    ),
    _dp("hp_thermal_power_dhw", HP, F, "Rubin_CurrentOutputCapacityTwe", "aktuelle Leistung Twe"),
    _dp("hp_electrical_power", HP, F, "Rubin_CurrentPowerInverter", "Akt. elektr. Leistung"),
    _dp(
        "hp_electrical_power_heating",
        HP,
        F,
        "Rubin_CurrentPowerInverterHeating",
        "Akt. elektr. Leistung Heizen",
    ),
    _dp(
        "hp_electrical_power_dhw",
        HP,
        F,
        "Rubin_CurrentPowerInverterTwe",
        "akt. elektr. Leistung Twe",
    ),
    _dp("hp_cop", HP, F, "Rubin_CurrentCOP", "Aktueller COP"),
    _dp("hp_cop_heating", HP, F, "Rubin_CurrentCOPHeating", "Aktueller COP Heizen"),
    _dp("hp_cop_dhw", HP, F, "Rubin_CurrentCOPTwe", "aktueller COP Twe"),
    _dp(
        "hp_requested_power_heating",
        HP,
        F,
        "Rubin_RequestedPowerHeating",
        "Leistungsanforderung Heizen",
    ),
    _dp("hp_requested_power_dhw", HP, F, "Rubin_RequestedPowerTwe", "Leistungsanforderung TWE"),
    # --- heat pump: state
    _dp("hp_state", HP, N, "Rubin_CombinedHeatpumpState", "Status Wärmepumpe"),
    _dp("hp_state_since", HP, T, "Rubin_StateSinceUtc", "Status seit"),
    _dp("hp_heating_active", HP, B, "Rubin_IsHeatingState", "Heizen"),
    _dp("hp_dhw_active", HP, B, "Rubin_IsTweState", "TWE"),
    _dp("hp_cooling_active", HP, B, "Rubin_IsCoolingState", "Kühlen"),
    _dp("hp_defrosting", HP, B, "Rubin_IsDefrostingState", "Abtauen"),
    _dp("hp_pv_modulation", HP, B, "Rubin_PvIsActive", "Status PV Modulation"),
    _dp("hp_global_alarm", HP, B, None, "Globaler Alarm"),
    _dp("hp_global_warning", HP, B, None, "Globale Warnung"),
    _dp(
        "hp_charging_pump_running",
        HP,
        B,
        "Rubin_StorageChargingPumpState",
        "Betrieb Speicherladepumpe",
    ),
    # --- heat pump: temperatures / hydraulics / fan
    _dp(
        "hp_flow_temp",
        HP,
        F,
        "Rubin_Link_B16_Vorlauftemperatur_WP",
        "B16 - Vorlauftemperatur WP",
        temp=True,
    ),
    _dp(
        "hp_return_temp",
        HP,
        F,
        "Rubin_Link_B17_Ruecklauftemperatur_WP",
        "B17 - Rücklauftemperatur WP",
        temp=True,
    ),
    _dp("hp_air_inlet_temp", HP, F, None, "B15 - Energiequellen Eintrittstemperatur", temp=True),
    _dp("hp_air_outlet_temp", HP, F, None, "B14 - Energiequellen Austrittstemperatur", temp=True),
    _dp("hp_outdoor_temp", HP, F, None, "BOT - Außentemperaturfühler", temp=True),
    _dp("hp_spread", HP, F, None, "Aktuelle Temperaturspreizung Pufferladekreis"),
    _dp("hp_flow_rate", HP, F, "Rubin_Link_P13_Durchfluss_WP", "P13 - Durchfluss WP"),
    _dp("hp_required_flow_rate", HP, F, None, "Erforderlicher Durchfluss Ladekreis"),
    _dp("hp_fan_speed", HP, F, None, "Erforderliche Lüfterdrehzahl"),
    _dp(
        "hp_charging_pump_power",
        HP,
        F,
        "Rubin_AktuelleLeistungSpeicherladepumpe",
        "Aktuelle Leistung Speicherladepumpe",
    ),
    # --- heat pump: counters / info
    _dp("hp_compressor_starts", HP, N, None, "Anzahl der Verdichterstarts"),
    _dp(
        "hp_hours_compressor",
        HP,
        F,
        "Rubin_OperationHoursCompressor",
        "Betriebsstunden - Verdichter",
    ),
    _dp("hp_hours_fan", HP, F, None, "Betriebsstunden - Lüfter"),
    _dp("hp_hours_charging_pump", HP, F, None, "Betriebsstunden - Speicherladepumpe"),
    _dp("hp_sw_major", HP, N, "Rubin_SWVersion_Major", "Version SW: Major"),
    _dp("hp_sw_minor", HP, N, "Rubin_SWVersion_Minor", "Version SW: Minor"),
    _dp("hp_sw_patch", HP, N, "Rubin_SWVersion_Patch", "Version SW: Patch"),
    _dp("hp_model", HP, S, None, "Name Wärmepumpe"),
    _dp("hp_serial", HP, S, None, "Seriennummer"),
    # --- Heizen (buffer module 50)
    _dp("hz_outdoor_temp", HZ, F, "LuftTemperatur", "Außentemperatur", temp=True),
    _dp(
        "hz_outdoor_temp_avg",
        HZ,
        F,
        "Aussentemperatur_gemittelt",
        "Gemittelte Außentemperatur",
        temp=True,
    ),
    _dp(
        "hz_outdoor_temp_season",
        HZ,
        F,
        "HP_Aussentemperatur_Saison",
        "Saison-Außentemperatur",
        temp=True,
    ),
    _dp(
        "hz_circuit_temp",
        HZ,
        F,
        "HeatingCircuit_TemperatureActualValue",
        "Isttemperatur Heizkreis",
        temp=True,
    ),
    _dp(
        "hz_circuit_setpoint",
        HZ,
        F,
        "HeatingCircuit_TemperatureSetpoint",
        "Solltemperatur Heizkreis",
        temp=True,
    ),
    _dp(
        "hz_buffer_temp",
        HZ,
        F,
        "BufferSystem_HeatingTemperatureActual",
        "Isttemperatur Heizspeicher",
        temp=True,
    ),
    _dp(
        "hz_buffer_setpoint",
        HZ,
        F,
        "BufferSystem_HeatingSetpoint",
        "Solltemperatur Heizspeicher",
        temp=True,
    ),
    _dp("hz_mixer_position", HZ, F, "HeatingCircuit_MixerPosition", "Mischeröffnung"),
    _dp(
        "hz_heater_power",
        HZ,
        F,
        "BufferSystem_HeaterRequestedElectricalPower",
        "aktuelle elektr. Leistung",
    ),
    _dp("hz_heater_hours", HZ, F, None, "Ext. WEZ Laufzeit"),
    _dp("hz_energy_mode", HZ, N, "HeatingCircuit_EnergyMode", "Energiemodus"),
    _dp("hz_summer_mode", HZ, B, "HeatingCircuit_SummerMode", "Sommerbetrieb"),
    _dp(
        "hz_circuit_pump_hours",
        HZ,
        F,
        "HeatingCircuit_OperatingHoursPump",
        "Heizkreispumpe Laufzeit",
    ),
    _dp("hz_sw_major", HZ, N, "PowerModule_SWVersion_Major", "Software-Version Major"),
    _dp("hz_sw_minor", HZ, N, "PowerModule_SWVersion_Minor", "Software-Version Minor"),
    _dp("hz_sw_patch", HZ, N, "PowerModule_SWVersion_Patch", "Software-Version Patch"),
    _dp("hz_model", HZ, S, "DeviceType", "Gerätetyp"),
    # --- Warmwasser (buffer module 51)
    _dp("ww_temp", WW, F, "BufferSystem_TweTemperatureActual", "Isttemperatur TWE", temp=True),
    _dp("ww_setpoint", WW, F, "BufferSystem_TweSetpoint", "Solltemperatur TWE", temp=True),
    _dp(
        "ww_one_time_setpoint",
        WW,
        F,
        "BufferSystem_OneTimeTweSetpoint",
        "Sollwert Einmalladung TWE",
        temp=True,
    ),
    _dp(
        "ww_heater_power",
        WW,
        F,
        "BufferSystem_HeaterRequestedElectricalPower",
        "aktuelle elektr. Leistung",
    ),
    _dp("ww_heater_hours", WW, F, None, "Ext. WEZ Laufzeit"),
    _dp("ww_one_time_charge", WW, B, "BufferSystem_OneTimeTwe", "Einmalladung TWE"),
    _dp(
        "ww_setpoint_constant",
        WW,
        F,
        "BufferSystem_TemperatureSetpointTwe",
        "Konstanter Sollwert TWE",
        temp=True,
    ),
    _dp("ww_sw_major", WW, N, "PowerModule_SWVersion_Major", "Software-Version Major"),
    _dp("ww_sw_minor", WW, N, "PowerModule_SWVersion_Minor", "Software-Version Minor"),
    _dp("ww_sw_patch", WW, N, "PowerModule_SWVersion_Patch", "Software-Version Patch"),
    _dp("ww_model", WW, S, "DeviceType", "Gerätetyp"),
    # --- heat pump: compressor start blocks (heating relevant only; the cooling
    # blocks are permanently active in winter and would only be noise)
    *(_dp(key, HP, B, wkn, name) for key, wkn, name in COMPRESSOR_BLOCKS),
    _dp("hp_oil_heating", HP, B, "Rubin_Oelheizung", "Ölheizung"),
    _dp("hp_compressor_start_preparing", HP, B, None, "Vorbereitung Verdichterstart"),
    _dp("hp_oil_return_countdown", HP, F, None, "Countdown bis zur Ölrückführung"),
    # --- classic firmware only (experimental, read-only)
    _dp("hp_energy_electric_total", HP, F, "HP_StrommengeGesamt"),
    _dp("hp_energy_heat_total", HP, F, "HP_WaermemengeGesamt"),
    _dp("hp_energy_electric_heating", HP, F, "HP_HeatingWaterElectricalEnergy"),
    _dp("hp_energy_electric_dhw", HP, F, "HP_HotWaterElectricalEnergy"),
    _dp("hp_scop", HP, F, "HP_SCOPGesamt"),
    _dp("hp_cop_heating_avg", HP, F, "HP_HeatingWaterAverageCOP"),
)

# WellKnownNames of the classic x-center firmware (HP_*), taken from
# kermi-ha-bridge. Untested here: there was no classic unit to test against.
CLASSIC_WKNS: dict[str, tuple[str, ...]] = {
    "hp_state": ("HP_HeatpumpState",),
    "hp_thermal_power": ("HP_HeatOutput",),
    "hp_electrical_power": ("HP_AktuelleMotorleistungKW",),
    "hp_cop": ("HP_TotalCOP",),
    "hp_cop_heating": ("HP_HeatingWaterCOP",),
    "hp_cop_dhw": ("HP_HotWaterCOP",),
    "hp_flow_temp": ("HP_AuslasstempLadekreis",),
    "hp_return_temp": ("HP_EinlasstempLadekreis",),
    "hz_outdoor_temp": ("VolWo_Temperature_Sensor_S1_Value", "Aussentemperatur"),
    "hz_buffer_temp": ("HP_IstTempHW",),
    "hz_buffer_setpoint": ("HP_HeizwasserSollwertPanel",),
    "hz_circuit_temp": ("HP_MK1IstTemp",),
    "hz_circuit_setpoint": ("HP_MK1SollTempPanel",),
    "hz_energy_mode": ("HP_EnergyModeHk1",),
    "ww_temp": ("HP_TWETempIst",),
    "ww_setpoint": ("HP_TWESoll",),
    "ww_one_time_setpoint": ("HP_TWESollEinmal",),
    "ww_one_time_charge": ("HP_EinmalTWEPanel",),
}

STATIC_KEYS: frozenset[str] = frozenset(
    {
        "hp_sw_major",
        "hp_sw_minor",
        "hp_sw_patch",
        "hp_model",
        "hp_serial",
        "hz_sw_major",
        "hz_sw_minor",
        "hz_sw_patch",
        "hz_model",
        "ww_sw_major",
        "ww_sw_minor",
        "ww_sw_patch",
        "ww_model",
    }
)

DATAPOINTS: tuple[Datapoint, ...] = tuple(
    replace(dp, alt_wkns=CLASSIC_WKNS.get(dp.key, ()), static=dp.key in STATIC_KEYS)
    for dp in _BASE_DATAPOINTS
)

DATAPOINTS_BY_KEY: dict[str, Datapoint] = {dp.key: dp for dp in DATAPOINTS}

# HeatingCircuit_EnergyMode (PossibleValueKey "EnergyMode"). Mapping taken from
# kermi-ha-bridge (derived from the x-center web UI). The catalogue only gives
# the offsets per mode (Eco -2 K, Normal 0 K, Komfort +2 K,
# Benutzerdefiniert -5 K on this unit); it does not contain the numbers.
ENERGY_MODES: dict[int, str] = {
    0: "off",
    1: "eco",
    2: "normal",
    3: "comfort",
    4: "custom",
}

# ------------------------------------------------------------------ writes
#
# The ONLY datapoints that may ever be written, and only when the user has
# enabled writes in the options. Everything else (heating curves, compressor,
# alarms/resets, cooling, installer settings) is deliberately absent.


@dataclass(frozen=True, kw_only=True)
class WritableDatapoint:
    """Safety envelope of one writable datapoint."""

    key: str  # key in DATAPOINTS
    type_name: str  # .NET $type of the value
    safe_min: float | None = None
    safe_max: float | None = None
    allowed_values: frozenset[Any] | None = None
    # Require MinValue/MaxValue from the live catalogue (numeric values).
    needs_catalogue_bounds: bool = True

    @property
    def is_bool(self) -> bool:
        """Whether the value is a .NET Boolean."""
        return "System.Boolean," in self.type_name

    @property
    def is_int(self) -> bool:
        """Whether the value is a .NET Int32."""
        return "System.Int32," in self.type_name

    @property
    def is_float(self) -> bool:
        """Whether the value is a .NET Single."""
        return "System.Single," in self.type_name


_NET_TYPE = "BMS.Shared.DatapointCore.DatapointValue`1[[System.{}, mscorlib]], BMS.Shared"

WRITABLE: dict[str, WritableDatapoint] = {
    w.key: w
    for w in (
        WritableDatapoint(
            key="ww_one_time_charge",
            type_name=_NET_TYPE.format("Boolean"),
            allowed_values=frozenset({True}),  # can only start a charge
            needs_catalogue_bounds=False,
        ),
        WritableDatapoint(
            key="ww_one_time_setpoint",
            type_name=_NET_TYPE.format("Single"),
            safe_min=40.0,
            safe_max=55.0,
        ),
        WritableDatapoint(
            key="ww_setpoint_constant",
            type_name=_NET_TYPE.format("Single"),
            safe_min=40.0,
            safe_max=55.0,
        ),
        WritableDatapoint(
            key="hz_energy_mode",
            type_name=_NET_TYPE.format("Int32"),
            safe_min=1,
            safe_max=4,
            allowed_values=frozenset({1, 2, 3, 4}),  # never 0 = off
        ),
    )
}

# Temperatures at or below this mean "sensor not connected" (-999.9).
_NOT_CONNECTED = -999.0


# ------------------------------------------------------------------ resolve


def match_role_devices(devices: list[dict[str, Any]]) -> dict[Role, dict[str, Any]]:
    """Map each role to its device from Device/GetAllDevices."""
    found: dict[Role, dict[str, Any]] = {}
    for role, (needles, dtype) in ROLE_MATCH.items():
        for dev in devices:
            name = str(dev.get("Name") or "").lower()
            if any(n in name for n in needles) and dev.get("DeviceId"):
                found[role] = dev
                break
        else:
            if dtype is not None:
                for dev in devices:
                    if dev.get("DeviceType") == dtype and dev.get("DeviceId"):
                        found[role] = dev
                        break
    return found


def _find_config(
    configs: list[dict[str, Any]], spec: Datapoint, *, by_name: bool = True
) -> tuple[dict[str, Any], str | None] | None:
    """Find a datapoint: primary WKN, then classic WKNs, then exact DisplayName."""
    for wkn in (spec.wkn, *spec.alt_wkns):
        if not wkn:
            continue
        for cfg in configs:
            if cfg.get("WellKnownName") == wkn and cfg.get("DatapointConfigId"):
                return cfg, wkn
    if by_name and spec.display_name:
        matches = [
            cfg
            for cfg in configs
            if cfg.get("DisplayName") == spec.display_name and cfg.get("DatapointConfigId")
        ]
        visible = [cfg for cfg in matches if not cfg.get("Hidden")]
        if visible or matches:
            return (visible or matches)[0], None
    return None


def _bound(cfg: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _to_float(cfg.get(key))
        if value is not None:
            return value
    return None


def resolve_datapoints(
    role_devices: dict[Role, dict[str, Any]],
    configs_by_type: dict[int, list[dict[str, Any]]],
    specs: tuple[Datapoint, ...] = DATAPOINTS,
    all_devices: list[dict[str, Any]] | None = None,
) -> dict[str, ResolvedDatapoint]:
    """Resolve datapoint specs against the live catalogue.

    If the device of a role was not found (classic firmware has other device
    names), datapoints with WellKnownNames are searched on all other devices,
    by WellKnownName only: DisplayNames are ambiguous across devices.
    """
    others = [
        dev
        for dev in (all_devices or [])
        if dev.get("DeviceType") and dev.get("DeviceId") and dev not in role_devices.values()
    ]
    resolved: dict[str, ResolvedDatapoint] = {}
    for spec in specs:
        dev = role_devices.get(spec.role)
        candidates = [(dev, True)] if dev is not None else [(d, False) for d in others]
        for candidate, by_name in candidates:
            dtype = candidate.get("DeviceType")
            configs = configs_by_type.get(dtype, []) if isinstance(dtype, int) else []
            found = _find_config(configs, spec, by_name=by_name)
            if found is None:
                continue
            cfg, matched = found
            resolved[spec.key] = ResolvedDatapoint(
                spec=spec,
                config_id=str(cfg["DatapointConfigId"]).lower(),
                device_id=str(candidate["DeviceId"]).lower(),
                display_name=cfg.get("DisplayName"),
                unit=cfg.get("Unit"),
                min_value=_bound(cfg, ("MinValue", "Minimum", "Min")),
                max_value=_bound(cfg, ("MaxValue", "Maximum", "Max")),
                matched_wkn=matched,
            )
            break
        else:
            _LOGGER.debug("Datapoint %s not found in catalogue", spec.key)
    return resolved


# ------------------------------------------------------------------ values

_FRACTION = re.compile(r"(\.\d{6})\d+")


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = _FRACTION.sub(r"\1", raw.strip()).replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value.year < 2000:  # .NET DateTime.MinValue and similar placeholders
        return None
    return value


def _to_float(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)  # handles "NaN" and numeric strings
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def convert_value(spec: Datapoint, raw: Any) -> Any:
    """Convert a raw ReadValues value; None means unavailable."""
    if raw is None:
        return None
    if spec.kind is Kind.BOOL:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)) and not (isinstance(raw, float) and math.isnan(raw)):
            return bool(raw)
        if isinstance(raw, str) and raw.strip().lower() in ("true", "false", "1", "0"):
            return raw.strip().lower() in ("true", "1")
        return None
    if spec.kind is Kind.STR:
        text = str(raw).strip()
        return text or None
    if spec.kind is Kind.TIMESTAMP:
        return _parse_timestamp(raw)
    value = _to_float(raw)
    if value is None:
        return None
    if spec.temperature and value <= _NOT_CONNECTED:
        return None
    if spec.kind is Kind.INT:
        return round(value)
    return value
