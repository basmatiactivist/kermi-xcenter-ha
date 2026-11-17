"""Shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from .fake_xcenter import FakeXCenter

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    return


@pytest.fixture
async def xcenter(socket_enabled) -> AsyncGenerator[FakeXCenter]:
    """A running fake x-center on 127.0.0.1.

    pytest-socket keeps every host except 127.0.0.1 blocked, so no test can
    reach a real x-center.
    """
    fake = FakeXCenter()
    await fake.start()
    yield fake
    await fake.stop()
