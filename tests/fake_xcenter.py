"""A local fake of the x-center web API, built from the anonymised catalogue.

It only ever listens on 127.0.0.1. Any request to an endpoint the integration
must not use is recorded in ``forbidden`` and answered with 404.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer

CATALOG = json.loads((Path(__file__).parent / "fixtures_catalog.json").read_text("utf-8"))
DEST = "00000000-0000-0000-0000-000000000000"
SERIAL = "TESTSERIAL123"
PASSWORD = "1234"

WRITE_ENDPOINT = "Datapoint/" + "WriteValues"
# Bounds the real catalogue presumably reports (field names unverified).
BOUNDS = {
    "BufferSystem_TemperatureSetpointTwe": (0, 85),
    "BufferSystem_OneTimeTweSetpoint": (0, 85),
    "HeatingCircuit_EnergyMode": (0, 4),
}

KNOWN = {
    WRITE_ENDPOINT,
    "Security/Login",
    "Security/Logout",
    "Device/GetAllDevices",
    "Datapoint/GetConfigsByDeviceType",
    "Datapoint/ReadValues",
}


def _wrap(data: Any) -> dict[str, Any]:
    return {"ResponseData": data, "StatusCode": 0, "DisplayText": None}


class FakeXCenter:
    """In-memory fake x-center."""

    def __init__(self, *, password: str = PASSWORD, device_serial: str | None = None) -> None:
        self.password = password
        self.tokens: set[str] = set()
        self.requests: list[tuple[str, str]] = []
        self.forbidden: list[tuple[str, str]] = []
        self.read_sizes: list[int] = []
        self.read_keys: list[set[tuple[str, str]]] = []
        self.login_attempts = 0
        self.logouts = 0
        self.fail_all = False
        self.status_code = 0
        self.write_status_code = 0
        self.writes: list[dict[str, Any]] = []
        self.redirect_login = False
        self.chunked = False  # send bodies in small pieces, like a slow network
        self.huge_device_list = False
        self.devices: list[dict[str, Any]] = []
        self.configs: dict[int, list[dict[str, Any]]] = {}
        self.values: dict[tuple[str, str], Any] = {}
        for dev in CATALOG["devices"]:
            entry = {
                "DeviceId": dev["id"],
                "DeviceType": dev["type"],
                "Name": dev["name"],
                # an extra field that must never end up in diagnostics
                "IpAddress": "10.11.12.13",
            }
            if device_serial and dev["type"] == 0:
                entry["SerialNumber"] = device_serial
            self.devices.append(entry)
            cfgs = []
            for dp in dev.get("dp", []):
                cfgs.append(
                    {
                        "DatapointConfigId": dp["id"],
                        "WellKnownName": dp["w"],
                        "DisplayName": dp["n"],
                        "Unit": dp["u"],
                        "Hidden": dp["h"],
                        "UserLevelRead": dp["ul"],
                        "PossibleValueKey": dp["pv"],
                    }
                )
                if dp["w"] in BOUNDS:
                    cfgs[-1]["MinValue"], cfgs[-1]["MaxValue"] = BOUNDS[dp["w"]]
                value = dp["v"]
                if value == "NaN":
                    value = float("nan")  # the real API sends a bare NaN literal
                if dp["n"] == "Seriennummer" and dev["type"] == 97:
                    value = SERIAL
                self.values[(dp["id"].lower(), dev["id"].lower())] = value
            if cfgs:
                self.configs[dev["type"]] = cfgs
        self.server: TestServer | None = None

    # ------------------------------------------------------------ helpers
    def device_id(self, needle: str) -> str:
        return next(d["DeviceId"] for d in self.devices if needle in d["Name"])

    def set_value(self, device_needle: str, display_name: str, value: Any) -> None:
        did = self.device_id(device_needle)
        dtype = next(d["DeviceType"] for d in self.devices if d["DeviceId"] == did)
        cid = next(
            c["DatapointConfigId"] for c in self.configs[dtype] if c["DisplayName"] == display_name
        )
        self.values[(cid.lower(), did.lower())] = value

    def expire_sessions(self) -> None:
        self.tokens.clear()

    @property
    def host(self) -> str:
        assert self.server is not None
        return f"127.0.0.1:{self.server.port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._route)
        self.server = TestServer(app, host="127.0.0.1")
        await self.server.start_server()

    async def stop(self) -> None:
        if self.server is not None:
            await self.server.close()

    # ------------------------------------------------------------ handler
    def _json(self, data: Any, status: int = 200) -> web.Response:
        return web.Response(text=json.dumps(data), status=status, content_type="application/json")

    async def _route(self, request: web.Request) -> web.StreamResponse:
        resp = await self._handle(request)
        if not self.chunked or resp.body is None or resp.status != 200:
            return resp
        body = bytes(resp.body)
        stream = web.StreamResponse(status=resp.status, headers=resp.headers)
        stream.content_type = "application/json"
        for name, morsel in resp.cookies.items():
            stream.set_cookie(name, morsel.value)
        stream.enable_chunked_encoding()
        await stream.prepare(request)
        for start in range(0, len(body), 37):
            await stream.write(body[start : start + 37])
            await asyncio.sleep(0)
            await asyncio.sleep(0.001)
        await stream.write_eof()
        return stream

    async def _handle(self, request: web.Request) -> web.Response:
        path = request.path
        self.requests.append((request.method, path))
        await request.read()  # consume the body before any early answer
        endpoint = None
        if path.startswith("/api/") and path.endswith("/" + DEST):
            endpoint = path[len("/api/") : -len(DEST) - 1]
        if path == "/elsewhere":
            self.forbidden.append((request.method, path))
            return self._json({"isValid": True})
        if endpoint not in KNOWN:
            self.forbidden.append((request.method, path))
            return web.Response(status=404)
        if self.fail_all:
            return web.Response(status=500)
        if endpoint == "Security/Login" and self.redirect_login:
            raise web.HTTPTemporaryRedirect("/elsewhere")
        if endpoint == "Security/Login":
            self.login_attempts += 1
            body = await request.json()
            if body.get("Password") != self.password:
                return self._json({"isValid": False})
            token = secrets.token_hex(8)
            self.tokens.add(token)
            resp = self._json({"isValid": True})
            resp.set_cookie("session", token)
            return resp
        if request.cookies.get("session") not in self.tokens:
            return web.Response(status=401)
        if endpoint == "Security/Logout":
            self.logouts += 1
            self.tokens.discard(request.cookies.get("session"))
            return self._json(_wrap(None))
        if endpoint == "Device/GetAllDevices":
            if request.method != "GET":
                return web.Response(status=405)
            if self.huge_device_list:
                return self._json(_wrap([{"Name": "x" * 1024}] * 3000))
            return self._json(_wrap(self.devices) | {"StatusCode": self.status_code})
        body = await request.json()
        if endpoint == "Datapoint/GetConfigsByDeviceType":
            return self._json(_wrap(self.configs.get(body["DeviceType"], [])))
        if endpoint == WRITE_ENDPOINT:
            for item in body["DatapointValues"]:
                self.writes.append(item)
                if self.write_status_code == 0:
                    key = (item["DatapointConfigId"].lower(), item["DeviceId"].lower())
                    self.values[key] = item["Value"]
            return self._json({"ResponseData": None, "StatusCode": self.write_status_code})
        # ReadValues
        wanted = body["DatapointValues"]
        self.read_sizes.append(len(wanted))
        self.read_keys.append(
            {(w["DatapointConfigId"].lower(), w["DeviceId"].lower()) for w in wanted}
        )
        if len(wanted) > 40:
            return self._json(_wrap([]))
        items = []
        for w in wanted:
            key = (w["DatapointConfigId"].lower(), w["DeviceId"].lower())
            if key not in self.values:
                return self._json(_wrap([]))  # unknown GUID empties the answer
            items.append(
                {
                    "DatapointConfigId": w["DatapointConfigId"],
                    "DeviceId": w["DeviceId"],
                    "Value": self.values[key],
                }
            )
        return self._json(_wrap(items) | {"StatusCode": self.status_code})
