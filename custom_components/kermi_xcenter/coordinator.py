"""Data update coordinator for the Kermi x-center."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KermiAuthError, KermiClient, KermiError, KermiWriteRefusedError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MAX_BACKOFF, MIN_SCAN_INTERVAL
from .datapoints import (
    ResolvedDatapoint,
    Role,
    convert_value,
    match_role_devices,
    resolve_datapoints,
)

_LOGGER = logging.getLogger(__name__)

type KermiConfigEntry = ConfigEntry[KermiCoordinator]


class KermiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all resolved datapoints with one (chunked) ReadValues round."""

    config_entry: KermiConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KermiConfigEntry, client: KermiClient) -> None:
        """Initialise the coordinator."""
        seconds = max(
            MIN_SCAN_INTERVAL,
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.base_interval = timedelta(seconds=seconds)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self.base_interval,
        )
        self.client = client
        self.devices: list[dict[str, Any]] = []
        self.role_devices: dict[Role, dict[str, Any]] = {}
        self.resolved: dict[str, ResolvedDatapoint] = {}
        self.failures = 0
        self.platforms: list[Platform] = []
        # Values that never change (model, serial, versions), read once at setup.
        self.static_data: dict[str, Any] = {}
        # Datapoint keys used by entities currently in Home Assistant. Disabled
        # entities are not added, so their datapoints are not polled.
        self._subscriptions: Counter[str] = Counter()

    @callback
    def subscribe(self, keys: Iterable[str]) -> Callable[[], None]:
        """Poll these datapoints while the returned callback has not been called."""
        keys = [key for key in keys if key in self.resolved]
        self._subscriptions.update(keys)

        @callback
        def _unsubscribe() -> None:
            self._subscriptions.subtract(keys)
            self._subscriptions += Counter()  # drop keys that reached zero

        return _unsubscribe

    @property
    def polled_keys(self) -> list[str]:
        """Datapoints read on each poll (all dynamic ones until entities exist)."""
        dynamic = [key for key, rd in self.resolved.items() if not rd.spec.static]
        if not self._subscriptions:
            return dynamic
        return [key for key in dynamic if self._subscriptions[key] > 0]

    async def _async_setup(self) -> None:
        """Resolve datapoints once from the live catalogue."""
        try:
            self.devices = await self.client.get_all_devices()
            self.role_devices = match_role_devices(self.devices)
            configs: dict[int, list[dict[str, Any]]] = {}
            for dev in self.devices:
                dtype = dev.get("DeviceType")
                if isinstance(dtype, int) and dtype and dtype not in configs:
                    configs[dtype] = await self.client.get_configs_by_device_type(dtype)
        except KermiAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except KermiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="catalogue_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.resolved = resolve_datapoints(self.role_devices, configs, all_devices=self.devices)
        if not self.resolved:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="no_datapoints")
        static_keys = {key for key, rd in self.resolved.items() if rd.spec.static}
        self.static_data = await self._read(static_keys)
        _LOGGER.debug(
            "Resolved %d datapoints for roles %s",
            len(self.resolved),
            [r.value for r in self.role_devices],
        )

    async def _read(self, keys: Iterable[str]) -> dict[str, Any]:
        """Read and convert the given datapoints (errors become HA exceptions)."""
        wanted = [self.resolved[key] for key in keys]
        if not wanted:
            return {}
        try:
            raw = await self.client.read_values((rd.config_id, rd.device_id) for rd in wanted)
        except KermiAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except KermiError as err:
            self._back_off()
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        if not raw:
            self._back_off()
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="no_values")
        return {
            rd.spec.key: convert_value(rd.spec, raw.get((rd.config_id, rd.device_id)))
            for rd in wanted
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the datapoints of the entities currently in Home Assistant."""
        values = await self._read(self.polled_keys)
        if self.failures:
            _LOGGER.info("x-center reachable again after %d failed polls", self.failures)
        self.failures = 0
        self.update_interval = self.base_interval
        return {**self.static_data, **values}

    def _back_off(self) -> None:
        """Double the poll interval per consecutive failure, up to MAX_BACKOFF."""
        self.failures += 1
        delay = self.base_interval * (2 ** min(self.failures, 10))
        self.update_interval = min(delay, MAX_BACKOFF)
        _LOGGER.debug("Poll failed %d time(s), next try in %s", self.failures, self.update_interval)

    async def async_write(self, key: str, value: Any) -> None:
        """Write one datapoint through the client's guarded write path."""
        resolved = self.resolved.get(key)
        if resolved is None:
            _LOGGER.info("Write %s=%r REFUSED: datapoint not in live catalogue", key, value)
            raise KermiWriteRefusedError(f"{key} is not in the live catalogue")
        await self.client.write_value(resolved, value)
        await self.async_refresh()  # show the new value right away
