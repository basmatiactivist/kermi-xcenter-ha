"""Sensors of the Kermi x-center (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry
from .datapoints import ENERGY_MODES, Role
from .entity import KermiEntity, KermiEntityDescription, _version, supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KermiSensorEntityDescription(KermiEntityDescription, SensorEntityDescription):
    """Describes a Kermi sensor."""

    raw_attribute: bool = False


def _temp(
    key: str, role: Role, dp: str, *, setpoint: bool = False, enabled: bool = True
) -> KermiSensorEntityDescription:
    return KermiSensorEntityDescription(
        key=key,
        translation_key=key,
        role=role,
        datapoints=(dp,),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0 if setpoint else 1,
        entity_registry_enabled_default=enabled,
    )


def _power(key: str, dp: str, *, enabled: bool = True) -> KermiSensorEntityDescription:
    return KermiSensorEntityDescription(
        key=key,
        translation_key=key,
        role=Role.HEAT_PUMP,
        datapoints=(dp,),
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
    )


def _cop(key: str, dp: str, *, enabled: bool = True) -> KermiSensorEntityDescription:
    return KermiSensorEntityDescription(
        key=key,
        translation_key=key,
        role=Role.HEAT_PUMP,
        datapoints=(dp,),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
    )


def _hours(key: str, role: Role, dp: str) -> KermiSensorEntityDescription:
    return KermiSensorEntityDescription(
        key=key,
        translation_key=key,
        role=role,
        datapoints=(dp,),
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


def _heater_power(role: Role, dp: str, *, enabled: bool) -> KermiSensorEntityDescription:
    """Electrical power of the external heat generator (heater rod), native W."""
    return KermiSensorEntityDescription(
        key="heater_power",
        translation_key="heater_power",
        role=role,
        datapoints=(dp,),
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=enabled,
    )


def _energy_mode(data: dict[str, Any]) -> str | None:
    raw = data.get("hz_energy_mode")
    return ENERGY_MODES.get(raw) if raw is not None else None


HP, HZ, WW = Role.HEAT_PUMP, Role.HEATING, Role.DHW

SENSORS: tuple[KermiSensorEntityDescription, ...] = (
    # ---------------------------------------------------------- heat pump
    _power("thermal_power", "hp_thermal_power"),
    _power("thermal_power_heating", "hp_thermal_power_heating"),
    _power("thermal_power_dhw", "hp_thermal_power_dhw"),
    _power("electrical_power", "hp_electrical_power"),
    _power("electrical_power_heating", "hp_electrical_power_heating"),
    _power("electrical_power_dhw", "hp_electrical_power_dhw"),
    _cop("cop", "hp_cop"),
    _cop("cop_heating", "hp_cop_heating"),
    _cop("cop_dhw", "hp_cop_dhw"),
    _power("requested_power_heating", "hp_requested_power_heating"),
    _power("requested_power_dhw", "hp_requested_power_dhw"),
    KermiSensorEntityDescription(
        key="heat_pump_state",
        translation_key="heat_pump_state",
        role=HP,
        datapoints=("hp_state",),
    ),
    KermiSensorEntityDescription(
        key="state_since",
        translation_key="state_since",
        role=HP,
        datapoints=("hp_state_since",),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    _temp("flow_temp", HP, "hp_flow_temp"),
    _temp("return_temp", HP, "hp_return_temp"),
    _temp("air_inlet_temp", HP, "hp_air_inlet_temp"),
    _temp("air_outlet_temp", HP, "hp_air_outlet_temp"),
    _temp("outdoor_temp_hp", HP, "hp_outdoor_temp", enabled=False),
    KermiSensorEntityDescription(
        key="spread",
        translation_key="spread",
        role=HP,
        datapoints=("hp_spread",),
        device_class=SensorDeviceClass.TEMPERATURE_DELTA,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    KermiSensorEntityDescription(
        key="flow_rate",
        translation_key="flow_rate",
        role=HP,
        datapoints=("hp_flow_rate",),
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    KermiSensorEntityDescription(
        key="required_flow_rate",
        translation_key="required_flow_rate",
        role=HP,
        datapoints=("hp_required_flow_rate",),
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    KermiSensorEntityDescription(
        key="fan_speed",
        translation_key="fan_speed",
        role=HP,
        datapoints=("hp_fan_speed",),
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    KermiSensorEntityDescription(
        key="charging_pump_power",
        translation_key="charging_pump_power",
        role=HP,
        datapoints=("hp_charging_pump_power",),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    KermiSensorEntityDescription(
        key="compressor_starts",
        translation_key="compressor_starts",
        role=HP,
        datapoints=("hp_compressor_starts",),
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _hours("hours_compressor", HP, "hp_hours_compressor"),
    _hours("hours_fan", HP, "hp_hours_fan"),
    _hours("hours_charging_pump", HP, "hp_hours_charging_pump"),
    KermiSensorEntityDescription(
        key="software_version",
        translation_key="software_version",
        role=HP,
        datapoints=("hp_sw_major", "hp_sw_minor", "hp_sw_patch"),
        value_fn=lambda data: _version(data, "hp"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---------------------------------------------------------- Heizen
    _temp("outdoor_temp", HZ, "hz_outdoor_temp"),
    _temp("outdoor_temp_avg", HZ, "hz_outdoor_temp_avg"),
    _temp("outdoor_temp_season", HZ, "hz_outdoor_temp_season", enabled=False),
    _temp("circuit_temp", HZ, "hz_circuit_temp"),
    _temp("circuit_setpoint", HZ, "hz_circuit_setpoint"),
    _temp("buffer_temp", HZ, "hz_buffer_temp"),
    _temp("buffer_setpoint", HZ, "hz_buffer_setpoint"),
    KermiSensorEntityDescription(
        key="mixer_position",
        translation_key="mixer_position",
        role=HZ,
        datapoints=("hz_mixer_position",),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    KermiSensorEntityDescription(
        key="energy_mode",
        translation_key="energy_mode",
        role=HZ,
        datapoints=("hz_energy_mode",),
        device_class=SensorDeviceClass.ENUM,
        options=list(ENERGY_MODES.values()),
        value_fn=_energy_mode,
        raw_attribute=True,
    ),
    _hours("circuit_pump_hours", HZ, "hz_circuit_pump_hours"),
    _heater_power(HZ, "hz_heater_power", enabled=False),
    _hours("heater_hours", HZ, "hz_heater_hours"),
    # ---------------------------------------------------------- Warmwasser
    _temp("dhw_temp", WW, "ww_temp"),
    _heater_power(WW, "ww_heater_power", enabled=True),
    _hours("heater_hours", WW, "ww_heater_hours"),
    _temp("dhw_setpoint", WW, "ww_setpoint", setpoint=True),
    _temp("dhw_one_time_setpoint", WW, "ww_one_time_setpoint", setpoint=True, enabled=False),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for all resolved datapoints."""
    coordinator = entry.runtime_data
    async_add_entities(
        KermiSensor(coordinator, desc) for desc in SENSORS if supported(coordinator, desc)
    )


class KermiSensor(KermiEntity, SensorEntity):
    """A read-only x-center sensor."""

    entity_description: KermiSensorEntityDescription

    @property
    def native_value(self) -> Any:
        """Return the converted value."""
        return self._value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the raw code for enum sensors (e.g. unknown energy mode)."""
        if not self.entity_description.raw_attribute:
            return None
        return {
            "raw_value": (self.coordinator.data or {}).get(self.entity_description.datapoints[0])
        }
