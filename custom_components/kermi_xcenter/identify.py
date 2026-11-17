"""Determine a stable unique id for an x-center (no Home Assistant imports)."""

from __future__ import annotations

import re
from typing import Any

from .api import KermiClient
from .datapoints import DATAPOINTS_BY_KEY, Role, match_role_devices, resolve_datapoints

_SERIAL_KEYS = ("SerialNumber", "Serialnumber", "SerialNo", "Serial")
_PLACEHOLDERS = {"", "0", "redacted", "unknown", "none", "null"}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", "", str(value))
    if text.lower() in _PLACEHOLDERS:
        return None
    return text


def serial_from_devices(devices: list[dict[str, Any]]) -> str | None:
    """Return the serial from GetAllDevices (interface module first, then heat pump)."""
    ordered = sorted(devices, key=lambda d: (d.get("DeviceType") != 0, d.get("DeviceType") != 97))
    for dev in ordered:
        for key in _SERIAL_KEYS:
            if serial := _clean(dev.get(key)):
                return serial
    return None


async def async_determine_unique_id(client: KermiClient, devices: list[dict[str, Any]]) -> str:
    """Return the serial of the interface/heat pump, or a device id as fallback.

    Uses only allowlisted read endpoints.
    """
    if serial := serial_from_devices(devices):
        return serial.lower()

    role_devices = match_role_devices(devices)
    heat_pump = role_devices.get(Role.HEAT_PUMP)
    if heat_pump is not None and isinstance(heat_pump.get("DeviceType"), int):
        configs = await client.get_configs_by_device_type(heat_pump["DeviceType"])
        spec = DATAPOINTS_BY_KEY["hp_serial"]
        resolved = resolve_datapoints(
            {Role.HEAT_PUMP: heat_pump}, {heat_pump["DeviceType"]: configs}, (spec,)
        )
        if rd := resolved.get(spec.key):
            values = await client.read_values([(rd.config_id, rd.device_id)])
            if serial := _clean(values.get((rd.config_id, rd.device_id))):
                return serial.lower()

    for dev in sorted(devices, key=lambda d: d.get("DeviceType") != 0):
        if dev.get("DeviceId"):
            return str(dev["DeviceId"]).lower()
    raise ValueError("x-center reported no devices")
