"""Kermi x-center (local) integration.

Read-only by default: only sensor and binary_sensor entities. Control entities
(button/number/select) exist only if the user explicitly enabled the option
``allow_writes``; every write then goes through the guarded
``KermiClient.write_value``. No services are registered.
"""

from __future__ import annotations

import aiohttp
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import KermiClient
from .const import CONF_ALLOW_WRITES
from .coordinator import KermiConfigEntry, KermiCoordinator

READ_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
# Only loaded when the option allow_writes is true.
WRITE_PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
# Kept for compatibility: the platforms of the default (read-only) install.
PLATFORMS = READ_PLATFORMS


def writes_allowed(entry: KermiConfigEntry) -> bool:
    """Whether the user explicitly enabled writes (default: no)."""
    return entry.options.get(CONF_ALLOW_WRITES) is True


def platforms_for(entry: KermiConfigEntry) -> list[Platform]:
    """Platforms to load for this entry."""
    return READ_PLATFORMS + (WRITE_PLATFORMS if writes_allowed(entry) else [])


def create_client(
    hass: HomeAssistant, host: str, password: str, *, writes_enabled: bool = False
) -> KermiClient:
    """Create a client with its own cookie jar (the x-center is addressed by IP)."""
    session = async_create_clientsession(
        hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar(unsafe=True)
    )
    # Sessions created by HA share HA's connector: detach instead of close.
    return KermiClient(
        host,
        password,
        session,
        release_session=session.detach,
        writes_enabled=writes_enabled,
    )


def _remove_write_entities(hass: HomeAssistant, entry: KermiConfigEntry) -> None:
    """With writes off, control entities must not exist, not even disabled."""
    ent_reg = er.async_get(hass)
    write_domains = {p.value for p in WRITE_PLATFORMS}
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.domain in write_domains:
            ent_reg.async_remove(reg_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: KermiConfigEntry) -> bool:
    """Set up the x-center from a config entry."""
    if not writes_allowed(entry):
        _remove_write_entities(hass, entry)
    client = create_client(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD],
        writes_enabled=writes_allowed(entry),
    )
    coordinator = KermiCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _async_logout_on_stop(_event: Event) -> None:
        await client.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_logout_on_stop)
    )
    coordinator.platforms = platforms_for(entry)
    await hass.config_entries.async_forward_entry_setups(entry, coordinator.platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KermiConfigEntry) -> bool:
    """Unload a config entry and log out of the x-center."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, entry.runtime_data.platforms)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: KermiConfigEntry) -> None:
    """Reload when options (scan interval, allow_writes) change."""
    await hass.config_entries.async_reload(entry.entry_id)
