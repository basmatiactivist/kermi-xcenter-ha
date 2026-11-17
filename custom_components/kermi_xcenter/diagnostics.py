"""Diagnostics for the Kermi x-center (password, serials and device ids redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import KermiConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    "unique_id",
    "DeviceId",
    "device_id",
    "SerialNumber",
    "Serialnumber",
    "SerialNo",
    "Serial",
    "hp_serial",
    "CustomProperties",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KermiConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    values = {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key, value in (coordinator.data or {}).items()
    }
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "unique_id": entry.unique_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "devices": coordinator.devices,
            "roles": {
                role.value: dev.get("Name") for role, dev in coordinator.role_devices.items()
            },
            "datapoints": {
                key: {
                    "role": rd.spec.role.value,
                    "well_known_name": rd.spec.wkn,
                    "display_name": rd.display_name,
                    "config_id": rd.config_id,
                    "device_id": rd.device_id,
                    "unit": rd.unit,
                }
                for key, rd in coordinator.resolved.items()
            },
            "values": values,
            "consecutive_failures": coordinator.failures,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        TO_REDACT,
    )
