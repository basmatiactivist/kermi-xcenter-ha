"""Selects (control). Only loaded when the option allow_writes is enabled."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import KermiError
from .const import DOMAIN
from .coordinator import KermiConfigEntry
from .datapoints import ENERGY_MODES, WRITABLE, Role
from .entity import KermiEntity, KermiEntityDescription, raise_write_error, supported

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class KermiSelectEntityDescription(KermiEntityDescription, SelectEntityDescription):
    """Describes a Kermi select; ``codes`` maps option -> raw value."""

    codes: dict[str, int]


_ENERGY_CODES = {
    name: code
    for code, name in ENERGY_MODES.items()
    if code in (WRITABLE["hz_energy_mode"].allowed_values or ())
}

SELECTS: tuple[KermiSelectEntityDescription, ...] = (
    KermiSelectEntityDescription(
        key="energy_mode_control",
        translation_key="energy_mode_control",
        role=Role.HEATING,
        datapoints=("hz_energy_mode",),
        options=list(_ENERGY_CODES),
        codes=_ENERGY_CODES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects, only if writes are enabled."""
    coordinator = entry.runtime_data
    if not coordinator.client.writes_enabled:
        return
    async_add_entities(
        KermiSelect(coordinator, desc) for desc in SELECTS if supported(coordinator, desc)
    )


class KermiSelect(KermiEntity, SelectEntity):
    """A control select."""

    entity_description: KermiSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        """Return the current option (None for codes not offered, e.g. off)."""
        raw = self._value
        for option, code in self.entity_description.codes.items():
            if code == raw:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the option through the guarded write path."""
        code = self.entity_description.codes.get(option)
        if code is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_option",
                translation_placeholders={"option": option},
            )
        try:
            await self.coordinator.async_write(self.entity_description.datapoints[0], code)
        except KermiError as err:
            raise_write_error(err)
