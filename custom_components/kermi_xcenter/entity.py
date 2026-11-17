"""Base entity for the Kermi x-center."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import KermiError, KermiWriteRefusedError
from .const import DOMAIN, MANUFACTURER
from .coordinator import KermiCoordinator
from .datapoints import ROLE_DEVICE_NAMES, Role


@dataclass(frozen=True, kw_only=True)
class KermiEntityDescription(EntityDescription):
    """Common fields of all Kermi entity descriptions."""

    role: Role
    # Datapoint keys this entity needs; the first one is its value by default.
    datapoints: tuple[str, ...]
    value_fn: Callable[[dict[str, Any]], Any] | None = None


def entry_uid(coordinator: KermiCoordinator) -> str:
    """Stable id prefix: the serial (unique_id) or the entry id."""
    entry = coordinator.config_entry
    return entry.unique_id or entry.entry_id


def _version(data: dict[str, Any], prefix: str) -> str | None:
    parts = [data.get(f"{prefix}_sw_{p}") for p in ("major", "minor", "patch")]
    if any(p is None for p in parts):
        return None
    return ".".join(str(p) for p in parts)


def build_device_info(coordinator: KermiCoordinator, role: Role) -> DeviceInfo:
    """Device info for one Kermi device, from the catalogue values."""
    data = coordinator.data or {}
    raw_device = coordinator.role_devices.get(role, {})
    if role is Role.HEAT_PUMP:
        model = data.get("hp_model") or raw_device.get("Name")
        sw_version = _version(data, "hp")
        serial = data.get("hp_serial")
    else:
        prefix = "hz" if role is Role.HEATING else "ww"
        model = f"x-center {data.get(f'{prefix}_model') or 'Buffer System'}"
        sw_version = _version(data, prefix)
        serial = None
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_uid(coordinator)}_{role.value}")},
        name=ROLE_DEVICE_NAMES[role],
        manufacturer=MANUFACTURER,
        model=model,
        model_id=raw_device.get("Name"),
        sw_version=sw_version,
        serial_number=serial,
    )


class KermiEntity(CoordinatorEntity[KermiCoordinator]):
    """A read-only entity backed by one or more x-center datapoints."""

    _attr_has_entity_name = True
    entity_description: KermiEntityDescription

    def __init__(self, coordinator: KermiCoordinator, description: KermiEntityDescription) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{entry_uid(coordinator)}_{description.role.value}_{description.key}"
        )
        self._attr_device_info = build_device_info(coordinator, description.role)

    @property
    def _value(self) -> Any:
        data = self.coordinator.data or {}
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(data)
        return data.get(self.entity_description.datapoints[0])

    @property
    def available(self) -> bool:
        """Unavailable when the x-center reports NaN / not connected."""
        data = self.coordinator.data or {}
        return super().available and all(
            data.get(key) is not None for key in self.entity_description.datapoints
        )


def supported(coordinator: KermiCoordinator, description: KermiEntityDescription) -> bool:
    """Whether all datapoints of a description were found in the catalogue."""
    return all(key in coordinator.resolved for key in description.datapoints)


def raise_write_error(err: KermiError) -> NoReturn:
    """Turn a client error of a control action into a translated HA error."""
    if isinstance(err, KermiWriteRefusedError):
        # Refused by the guard: a user/configuration issue, nothing was sent.
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="write_refused",
            translation_placeholders={"reason": str(err)},
        ) from err
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="write_failed",
        translation_placeholders={"reason": str(err)},
    ) from err
