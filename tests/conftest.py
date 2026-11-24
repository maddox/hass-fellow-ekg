"""Fixtures: a mocked kettle client. Nothing here talks to a real device."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.fellow_ekg.vendor.fellow_ekg import FirmwareInfo, parse_state
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fellow_ekg.const import DOMAIN

HOST = "192.168.30.22"
UNIQUE_ID = "f0:73:3c"
FIRMWARE = FirmwareInfo("1.2.5CL CLI", "Dec 10 2025", "05:25:49", "ota_0")


def make_state(temperature: float = 26.11, mode: str = "S_Off"):
    """`state` output in the format captured from a real kettle."""
    return parse_state(
        [
            "scrname=wnd",
            f"mode={mode}",
            f"tempr={temperature:.6f} C",
            "temprB=100.000000 C",
            "temprT=96.111115 C",
            "ketl= ho 0 wd 0 nw 0 ipb 0 bf 0 tr 0",
            "temps=205 F",
            "units=0",
            "clock=16:39",
            "ble conn=0",
        ]
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, mock_async_zeroconf):
    """Load custom integrations and keep HA's zeroconf off the real network."""
    yield


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    client = MagicMock()
    client.get_firmware_info = AsyncMock(return_value=FIRMWARE)
    client.get_state = AsyncMock(return_value=make_state())
    client.heat_on = AsyncMock()
    client.heat_off = AsyncMock()
    client.close = AsyncMock()
    with (
        patch("custom_components.fellow_ekg.EKGClient", return_value=client),
        patch("custom_components.fellow_ekg.config_flow.EKGClient", return_value=client),
    ):
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST}, unique_id=UNIQUE_ID)
