"""The Fellow EKG Pro integration."""

from __future__ import annotations

import logging

from .vendor.fellow_ekg import EKGClient, EKGError
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import FellowEKGConfigEntry, FellowEKGCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: FellowEKGConfigEntry) -> bool:
    client = EKGClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    try:
        firmware = await client.get_firmware_info()
    except EKGError as err:
        raise ConfigEntryNotReady(f"Cannot reach kettle at {entry.data[CONF_HOST]}") from err

    coordinator = FellowEKGCoordinator(hass, entry, client, firmware)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FellowEKGConfigEntry) -> bool:
    coordinator = entry.runtime_data
    if coordinator.heating:
        # Never leave a heater we turned on running without supervision.
        try:
            await coordinator.client.heat_off()
        except EKGError:
            _LOGGER.exception(
                "Could not turn heater off while unloading; the library's "
                "auto-off timer is still armed"
            )
        else:
            coordinator.heating = False
    if not coordinator.heating:
        # Only cancel the library's auto-off timer once the heater is known off.
        await coordinator.client.close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: FellowEKGConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
