"""Guarantees that the integration can never change anything on the heat pump."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.const import Platform

from custom_components.kermi_xcenter import PLATFORMS, READ_PLATFORMS, WRITE_PLATFORMS
from custom_components.kermi_xcenter.api import (
    ENDPOINT_ALLOWLIST,
    KermiClient,
    KermiReadOnlyError,
)
from custom_components.kermi_xcenter.datapoints import WRITABLE

PACKAGE = Path(__file__).parent.parent / "custom_components" / "kermi_xcenter"
SOURCES = {p: p.read_text("utf-8") for p in PACKAGE.rglob("*") if p.suffix in (".py", ".json")}

EXPECTED_ALLOWLIST = {
    "Security/Login": "POST",
    "Security/Logout": "POST",
    "Device/GetAllDevices": "GET",
    "Datapoint/GetConfigsByDeviceType": "POST",
    "Datapoint/ReadValues": "POST",
}


def _exploding_session() -> MagicMock:
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request.side_effect = AssertionError("network I/O must not happen")
    session.post.side_effect = AssertionError("network I/O must not happen")
    session.get.side_effect = AssertionError("network I/O must not happen")
    return session


def test_allowlist_is_exactly_the_read_endpoints() -> None:
    assert dict(ENDPOINT_ALLOWLIST) == EXPECTED_ALLOWLIST
    with pytest.raises(TypeError):
        ENDPOINT_ALLOWLIST["Datapoint/WriteValues"] = "POST"  # type: ignore[index]


@pytest.mark.parametrize(
    "endpoint",
    [
        "Datapoint/WriteValues",
        "Datapoint/writevalues",
        "Device/SetDevice",
        "Security/ChangePassword",
        "Datapoint/ReadValues/../WriteValues",
        "",
    ],
)
async def test_request_rejects_non_allowlisted_endpoint_before_io(endpoint: str) -> None:
    session = _exploding_session()
    client = KermiClient("192.0.2.1", "pw", session)
    client._logged_in = True  # skip login so nothing else could hit the network
    with pytest.raises(KermiReadOnlyError):
        await client._request(endpoint, {"DatapointValues": []})
    session.request.assert_not_called()


async def test_send_rejects_wrong_method_before_io() -> None:
    session = _exploding_session()
    client = KermiClient("192.0.2.1", "pw", session)
    with pytest.raises(KermiReadOnlyError):
        await client._send("PUT", "Datapoint/ReadValues", {})
    with pytest.raises(KermiReadOnlyError):
        await client._send("POST", "Device/GetAllDevices", {})
    session.request.assert_not_called()


def _enclosing_functions(tree: ast.AST) -> dict[ast.AST, str]:
    """Map every node to the qualified name of the function it is in."""
    owner: dict[ast.AST, str] = {}

    def visit(node: ast.AST, name: str) -> None:
        for child in ast.iter_child_nodes(node):
            child_name = name
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                child_name = f"{name}.{child.name}" if name else child.name
            owner[child] = child_name
            visit(child, child_name)

    visit(tree, "")
    return owner


def test_write_endpoint_only_in_guarded_function() -> None:
    """WriteValues appears exactly once: inside KermiClient.write_value."""
    hits = [
        (p, t.lower().count("writevalues"))
        for p, t in SOURCES.items()
        if "writevalues" in t.lower()
    ]
    assert [(p.name, n) for p, n in hits] == [("api.py", 1)]
    tree = ast.parse((PACKAGE / "api.py").read_text("utf-8"))
    owner = _enclosing_functions(tree)
    places = [
        owner[node]
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "WriteValues" in node.value
    ]
    assert places == ["KermiClient.write_value"]


def test_alternative_allowlist_only_passed_by_write_value() -> None:
    """Only the guarded write function may hand _request a different allowlist."""
    for path, text in SOURCES.items():
        if path.suffix != ".py":
            continue
        tree = ast.parse(text)
        owner = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(k.arg == "allowed" for k in node.keywords):
                assert (path.name, owner[node]) == ("api.py", "KermiClient.write_value")


def test_only_one_place_does_http() -> None:
    """The session is only used in api.py, via request() and close()."""
    session_calls = re.compile(r"session\.(\w+)\(")
    found = {
        path.name: session_calls.findall(text)
        for path, text in SOURCES.items()
        if path.suffix == ".py" and session_calls.search(text)
    }
    assert found == {"api.py": ["request", "close"]}
    for path, text in SOURCES.items():
        for forbidden in (
            "import requests",
            "import httpx",
            "urllib",
            "aiohttp.request(",
            "ws_connect",
            "socket",
        ):
            assert forbidden not in text, (path, forbidden)


def test_platforms() -> None:
    assert PLATFORMS == READ_PLATFORMS == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert WRITE_PLATFORMS == [Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
    platform_names = {p.value for p in Platform}
    modules = {p.stem for p in PACKAGE.glob("*.py")}
    assert modules & platform_names == {"sensor", "binary_sensor", "button", "number", "select"}


def test_writable_datapoints_are_exactly_the_first_set() -> None:
    assert set(WRITABLE) == {
        "ww_one_time_charge",
        "ww_one_time_setpoint",
        "ww_setpoint_constant",
        "hz_energy_mode",
    }
    assert WRITABLE["ww_one_time_setpoint"].safe_min == 40
    assert WRITABLE["ww_one_time_setpoint"].safe_max == 55
    assert WRITABLE["ww_setpoint_constant"].safe_min == 40
    assert WRITABLE["ww_setpoint_constant"].safe_max == 55
    assert WRITABLE["ww_one_time_charge"].allowed_values == {True}
    assert 0 not in WRITABLE["hz_energy_mode"].allowed_values


def test_no_services_registered() -> None:
    for path, text in SOURCES.items():
        assert "services.async_register" not in text, path
        assert "async_register_entity_service" not in text, path
        assert "services.yaml" not in text, path
    assert not (PACKAGE / "services.yaml").exists()


def test_manifest() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text("utf-8"))
    assert manifest["domain"] == "kermi_xcenter"
    assert manifest["name"] == "Kermi x-center (lokal)"
    assert manifest["version"] == "0.1.2"
    assert manifest["iot_class"] == "local_polling"
    assert manifest["requirements"] == []
    assert manifest["config_flow"] is True
