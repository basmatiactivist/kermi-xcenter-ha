"""Buttons (control). Only loaded when the option allow_writes is enabled."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KermiError
from .coordinator import KermiConfigEntry
from .datapoints import Role
from .entity import KermiEntity, KermiEntityDescription, raise_write_error, supported

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KermiButtonEntityDescription(KermiEntityDescription, ButtonEntityDescription):
    """Describes a Kermi button; pressing writes ``press_value``."""

    press_value: bool = True


BUTTONS: tuple[KermiButtonEntityDescription, ...] = (
    KermiButtonEntityDescription(
        key="dhw_one_time_charge_start",
        translation_key="dhw_one_time_charge_start",
        role=Role.DHW,
        datapoints=("ww_one_time_charge",),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons, only if writes are enabled."""
    coordinator = entry.runtime_data
    if not coordinator.client.writes_enabled:
        return
    async_add_entities(
        KermiButton(coordinator, desc) for desc in BUTTONS if supported(coordinator, desc)
    )


class KermiButton(KermiEntity, ButtonEntity):
    """A control button."""

    entity_description: KermiButtonEntityDescription

    async def async_press(self) -> None:
        """Write the press value through the guarded write path."""
        try:
            await self.coordinator.async_write(
                self.entity_description.datapoints[0], self.entity_description.press_value
            )
        except KermiError as err:
            raise_write_error(err)
