"""Config flow for the Kermi x-center (local, read-only)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_client
from .api import KermiAuthError, KermiError, is_valid_host, normalize_host
from .const import (
    CONF_ALLOW_WRITES,
    CONF_CONFIRM_WRITES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .identify import async_determine_unique_id

_LOGGER = logging.getLogger(__name__)

_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def async_validate(hass: HomeAssistant, host: str, password: str) -> str:
    """Log in, list devices and return the unique id. Read-only calls only."""
    client = create_client(hass, host, password)
    try:
        await client.login()
        devices = await client.get_all_devices()
        return await async_determine_unique_id(client, devices)
    finally:
        await client.close()


class KermiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the x-center."""

    VERSION = 1

    async def _async_try(self, host: str, password: str, errors: dict[str, str]) -> str | None:
        if not is_valid_host(host):
            errors[CONF_HOST] = "invalid_host"  # nothing is sent anywhere
            return None
        try:
            return await async_validate(self.hass, host, password)
        except KermiAuthError:
            errors["base"] = "invalid_auth"
        except (KermiError, ValueError):
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while validating the x-center")
            errors["base"] = "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for host and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            uid = await self._async_try(host, user_input[CONF_PASSWORD], errors)
            if uid is not None:
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"Kermi x-center ({host})",
                    data={CONF_HOST: host, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host and/or password of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            password = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
            uid = await self._async_try(host, password, errors)
            if uid is not None:
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"Kermi x-center ({host})",
                    data_updates={CONF_HOST: host, CONF_PASSWORD: password},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Optional(CONF_PASSWORD): _PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the password was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            uid = await self._async_try(entry.data[CONF_HOST], user_input[CONF_PASSWORD], errors)
            if uid is not None:
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return KermiOptionsFlow()


class KermiOptionsFlow(OptionsFlow):
    """Options: poll interval and the (default off) write permission."""

    def __init__(self) -> None:
        """Initialise the options flow."""
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            self._pending = {
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_ALLOW_WRITES: user_input.get(CONF_ALLOW_WRITES) is True,
            }
            already = self.config_entry.options.get(CONF_ALLOW_WRITES) is True
            if self._pending[CONF_ALLOW_WRITES] and not already:
                return await self.async_step_confirm_writes()
            return self.async_create_entry(data=self._pending)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_ALLOW_WRITES, default=options.get(CONF_ALLOW_WRITES) is True
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_confirm_writes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Require an explicit confirmation before writes are enabled."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_CONFIRM_WRITES) is True:
                return self.async_create_entry(data=self._pending)
            errors["base"] = "confirm_required"
        return self.async_show_form(
            step_id="confirm_writes",
            data_schema=vol.Schema(
                {vol.Required(CONF_CONFIRM_WRITES, default=False): BooleanSelector()}
            ),
            errors=errors,
        )
