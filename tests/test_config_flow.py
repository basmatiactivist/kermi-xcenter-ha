"""Config, reconfigure, reauth and options flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kermi_xcenter.const import (
    CONF_ALLOW_WRITES,
    CONF_CONFIRM_WRITES,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .fake_xcenter import PASSWORD, SERIAL, FakeXCenter

NO_SETUP = "custom_components.kermi_xcenter.async_setup_entry"


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_flow_success(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    with patch(NO_SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: f"http://{xcenter.host}/", CONF_PASSWORD: PASSWORD},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: xcenter.host, CONF_PASSWORD: PASSWORD}
    assert result["result"].unique_id == SERIAL.lower()
    assert xcenter.login_attempts == 1
    assert xcenter.logouts == 1  # validation session is closed again
    assert xcenter.forbidden == []


async def test_user_flow_invalid_auth(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: xcenter.host, CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert xcenter.login_attempts == 1  # exactly one attempt per submit


async def test_user_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    fake = FakeXCenter()
    await fake.start()
    host = fake.host
    await fake.stop()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL.lower(),
        data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD},
    ).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: xcenter.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_host(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL.lower(),
        data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    with patch(NO_SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: xcenter.host}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_HOST: xcenter.host, CONF_PASSWORD: PASSWORD}


async def test_reconfigure_wrong_password(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL.lower(),
        data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: xcenter.host, CONF_PASSWORD: "nope"}
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_other_device(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="some-other-serial",
        data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: PASSWORD},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: xcenter.host, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_HOST] == "10.0.0.1"


async def test_reauth(hass: HomeAssistant, xcenter: FakeXCenter) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL.lower(),
        data={CONF_HOST: xcenter.host, CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(NO_SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: PASSWORD}
        )
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == PASSWORD


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: "p"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 60, CONF_ALLOW_WRITES: False}


async def test_options_enabling_writes_needs_confirmation(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: "p"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert schema_keys[CONF_ALLOW_WRITES].default() is False  # default off
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_ALLOW_WRITES: True}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm_writes"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONFIRM_WRITES: False}
    )
    assert result["errors"] == {"base": "confirm_required"}
    assert CONF_ALLOW_WRITES not in entry.options
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CONFIRM_WRITES: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 30, CONF_ALLOW_WRITES: True}


async def test_options_disabling_writes_needs_no_confirmation(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="x",
        data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: "p"},
        options={CONF_SCAN_INTERVAL: 30, CONF_ALLOW_WRITES: True},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30, CONF_ALLOW_WRITES: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ALLOW_WRITES] is False


async def test_options_flow_rejects_too_fast_polling(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={CONF_HOST: "10.0.0.1", CONF_PASSWORD: "p"}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 5}
        )
    assert entry.options == {}
