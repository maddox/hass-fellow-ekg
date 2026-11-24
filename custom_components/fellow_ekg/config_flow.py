"""Config flow: manual host entry, zeroconf discovery, and options."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import voluptuous as vol
from fellow_ekg import DiscoveredKettle, EKGClient, EKGError, async_discover, kettle_from_service_info
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import CONF_MAX_HEAT_MINUTES, DEFAULT_MAX_HEAT_MINUTES, DOMAIN
from .coordinator import FellowEKGConfigEntry

_LOGGER = logging.getLogger(__name__)


async def _validate(hass: HomeAssistant, host: str) -> None:
    """Raise EKGError unless the host answers like a kettle (read-only)."""
    client = EKGClient(host, async_get_clientsession(hass))
    firmware = await client.get_firmware_info()
    if firmware.version is None:
        raise EKGError(f"{host} did not return an EKG status page")


def _title(kettle: DiscoveredKettle | None, host: str) -> str:
    if kettle and kettle.mac_suffix:
        return f"Fellow EKG Pro ({kettle.mac_suffix[-5:]})"
    return f"Fellow EKG Pro ({host})"


class FellowEKGConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: DiscoveredKettle | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: FellowEKGConfigEntry) -> FellowEKGOptionsFlow:
        return FellowEKGOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                await _validate(self.hass, host)
            except EKGError:
                errors["base"] = "cannot_connect"
            else:
                kettle = await self._lookup_mdns(host)
                await self.async_set_unique_id(kettle.unique_id if kettle else host)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(title=_title(kettle, host), data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def _lookup_mdns(self, host: str) -> DiscoveredKettle | None:
        """Match a manually entered host to its mDNS record for a stable ID."""
        try:
            aiozc = await zeroconf.async_get_async_instance(self.hass)
            kettles = await async_discover(timeout=3, aiozc=aiozc)
        except Exception:  # noqa: BLE001 - discovery is best-effort
            _LOGGER.debug("mDNS lookup failed", exc_info=True)
            return None
        return next((k for k in kettles if k.host == host), None)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        kettle = kettle_from_service_info(
            SimpleNamespace(
                name=discovery_info.name,
                server=discovery_info.hostname,
                port=discovery_info.port,
                parsed_addresses=lambda: [str(ip) for ip in discovery_info.ip_addresses],
            )
        )
        if kettle is None:
            return self.async_abort(reason="no_ipv4")

        await self.async_set_unique_id(kettle.unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: kettle.host})
        try:
            await _validate(self.hass, kettle.host)
        except EKGError:
            return self.async_abort(reason="cannot_connect")

        self._discovered = kettle
        self.context["title_placeholders"] = {"name": _title(kettle, kettle.host)}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        kettle = self._discovered
        if user_input is not None:
            return self.async_create_entry(
                title=_title(kettle, kettle.host), data={CONF_HOST: kettle.host}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"host": kettle.host, "name": _title(kettle, kettle.host)},
        )


class FellowEKGOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_MAX_HEAT_MINUTES, DEFAULT_MAX_HEAT_MINUTES)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAX_HEAT_MINUTES, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=30)
                    )
                }
            ),
        )
