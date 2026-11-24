from dataclasses import replace
from ipaddress import ip_address
from unittest.mock import patch

from custom_components.fellow_ekg.vendor.fellow_ekg import DiscoveredKettle, EKGConnectionError
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.fellow_ekg.const import CONF_MAX_HEAT_MINUTES, DOMAIN

from .conftest import HOST, UNIQUE_ID

KETTLE = DiscoveredKettle("EKG", "EKG-f0-73-3c.local.", HOST, 8888, UNIQUE_ID)
ZEROCONF = ZeroconfServiceInfo(
    ip_address=ip_address(HOST),
    ip_addresses=[ip_address(HOST)],
    hostname="EKG-f0-73-3c.local.",
    name="EKG._ekg._tcp.local.",
    port=8888,
    type="_ekg._tcp.local.",
    properties={},
)


def _patch_discover(kettles):
    return patch("custom_components.fellow_ekg.config_flow.async_discover", return_value=kettles)


async def test_user_flow(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with _patch_discover([KETTLE]), patch("custom_components.fellow_ekg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fellow EKG Pro (73:3c)"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == UNIQUE_ID


async def test_user_flow_without_mdns_uses_host_as_id(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with _patch_discover([]), patch("custom_components.fellow_ekg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["result"].unique_id == HOST


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_client) -> None:
    mock_client.get_firmware_info.side_effect = EKGConnectionError("nope")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_flow(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=ZEROCONF
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch("custom_components.fellow_ekg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == UNIQUE_ID


async def test_zeroconf_updates_host_of_existing_entry(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    new_ip = ip_address("192.168.30.99")
    moved = replace(ZEROCONF, ip_address=new_ip, ip_addresses=[new_ip])
    with patch("custom_components.fellow_ekg.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=moved
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.30.99"


async def test_options_flow(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_MAX_HEAT_MINUTES: 5})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_MAX_HEAT_MINUTES: 5}
