"""Numbers (control). Only loaded when the option allow_writes is enabled."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KermiError
from .coordinator import KermiConfigEntry
from .datapoints import WRITABLE, Role
from .entity import KermiEntity, KermiEntityDescription, raise_write_error, supported

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KermiNumberEntityDescription(KermiEntityDescription, NumberEntityDescription):
    """Describes a Kermi number."""


def _setpoint(key: str, dp: str) -> KermiNumberEntityDescription:
    spec = WRITABLE[dp]
    return KermiNumberEntityDescription(
        key=key,
        translation_key=key,
        role=Role.DHW,
        datapoints=(dp,),
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=spec.safe_min,
        native_max_value=spec.safe_max,
        native_step=1.0,
        mode=NumberMode.BOX,
    )


NUMBERS: tuple[KermiNumberEntityDescription, ...] = (
    _setpoint("dhw_one_time_setpoint_control", "ww_one_time_setpoint"),
    _setpoint("dhw_setpoint_control", "ww_setpoint_constant"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up numbers, only if writes are enabled."""
    coordinator = entry.runtime_data
    if not coordinator.client.writes_enabled:
        return
    async_add_entities(
        KermiNumber(coordinator, desc) for desc in NUMBERS if supported(coordinator, desc)
    )


class KermiNumber(KermiEntity, NumberEntity):
    """A control number."""

    entity_description: KermiNumberEntityDescription

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        value = self._value
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Write the value through the guarded write path."""
        try:
            await self.coordinator.async_write(self.entity_description.datapoints[0], value)
        except KermiError as err:
            raise_write_error(err)
