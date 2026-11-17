"""Binary sensors of the Kermi x-center (read-only)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (  # type: ignore[attr-defined]
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry
from .datapoints import COMPRESSOR_BLOCK_KEYS, Role
from .entity import KermiEntity, KermiEntityDescription, supported

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KermiBinarySensorEntityDescription(KermiEntityDescription, BinarySensorEntityDescription):
    """Describes a Kermi binary sensor."""


def _bin(
    key: str,
    role: Role,
    dp: str,
    device_class: BinarySensorDeviceClass | None = None,
    *,
    enabled: bool = True,
    diag: bool = False,
) -> KermiBinarySensorEntityDescription:
    return KermiBinarySensorEntityDescription(
        key=key,
        translation_key=key,
        role=role,
        datapoints=(dp,),
        device_class=device_class,
        entity_registry_enabled_default=enabled,
        entity_category=EntityCategory.DIAGNOSTIC if diag else None,
    )


RUNNING = BinarySensorDeviceClass.RUNNING
PROBLEM = BinarySensorDeviceClass.PROBLEM

BINARY_SENSORS: tuple[KermiBinarySensorEntityDescription, ...] = (
    _bin("heating_active", Role.HEAT_PUMP, "hp_heating_active", RUNNING),
    _bin("dhw_active", Role.HEAT_PUMP, "hp_dhw_active", RUNNING),
    _bin("cooling_active", Role.HEAT_PUMP, "hp_cooling_active", RUNNING, enabled=False),
    _bin("defrosting", Role.HEAT_PUMP, "hp_defrosting", RUNNING),
    _bin("pv_modulation", Role.HEAT_PUMP, "hp_pv_modulation"),
    _bin("global_alarm", Role.HEAT_PUMP, "hp_global_alarm", PROBLEM),
    _bin("global_warning", Role.HEAT_PUMP, "hp_global_warning", PROBLEM),
    _bin("charging_pump", Role.HEAT_PUMP, "hp_charging_pump_running", RUNNING, enabled=False),
    KermiBinarySensorEntityDescription(
        key="compressor_blocked",
        translation_key="compressor_blocked",
        role=Role.HEAT_PUMP,
        datapoints=COMPRESSOR_BLOCK_KEYS,
        any_datapoint=True,
        value_fn=lambda data: any(data.get(key) for key in COMPRESSOR_BLOCK_KEYS),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _bin("oil_heating", Role.HEAT_PUMP, "hp_oil_heating", RUNNING, enabled=False, diag=True),
    _bin(
        "compressor_start_preparing",
        Role.HEAT_PUMP,
        "hp_compressor_start_preparing",
        enabled=False,
        diag=True,
    ),
    _bin("summer_mode", Role.HEATING, "hz_summer_mode"),
    _bin("one_time_charge", Role.DHW, "ww_one_time_charge", RUNNING),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for all resolved datapoints."""
    coordinator = entry.runtime_data
    async_add_entities(
        KermiBinarySensor(coordinator, desc)
        for desc in BINARY_SENSORS
        if supported(coordinator, desc)
    )


class KermiBinarySensor(KermiEntity, BinarySensorEntity):
    """A read-only x-center binary sensor."""

    entity_description: KermiBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        value = self._value
        return bool(value) if value is not None else None
