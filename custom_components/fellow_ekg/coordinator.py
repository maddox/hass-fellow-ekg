"""Polling coordinator and heater supervision."""

from __future__ import annotations

import logging
import time

from .vendor.fellow_ekg import EKGClient, EKGError, EKGState, FirmwareInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_MAX_HEAT_MINUTES,
    DEFAULT_MAX_HEAT_MINUTES,
    DEFAULT_TARGET,
    DOMAIN,
    HEATING_INTERVAL,
    IDLE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type FellowEKGConfigEntry = ConfigEntry[FellowEKGCoordinator]


class FellowEKGCoordinator(DataUpdateCoordinator[EKGState]):
    """Polls ``state`` and turns the heater off at the target or time limit.

    The library's ``heaton`` drives the heater GPIO directly and likely skips
    the kettle's own temperature control, so this coordinator is the
    integration's safety loop: it polls every 2 s while heating and sends
    ``heatoff`` when the water reaches ``target_temperature`` or the time
    limit passes. The library's own auto-off timer is a second safety net.
    """

    config_entry: FellowEKGConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FellowEKGConfigEntry,
        client: EKGClient,
        firmware: FirmwareInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=IDLE_INTERVAL,
        )
        self.client = client
        self.firmware = firmware
        self.heating = False
        self.target_temperature = DEFAULT_TARGET
        self._heat_deadline: float | None = None

    @property
    def max_heat_seconds(self) -> int:
        minutes = self.config_entry.options.get(CONF_MAX_HEAT_MINUTES, DEFAULT_MAX_HEAT_MINUTES)
        return int(minutes * 60)

    async def _async_update_data(self) -> EKGState:
        try:
            state = await self.client.get_state()
        except EKGError as err:
            raise UpdateFailed(f"Error reading kettle state: {err}") from err
        if self.heating:
            await self._enforce_limits(state)
        return state

    async def _enforce_limits(self, state: EKGState) -> None:
        if self._heat_deadline is not None and time.monotonic() >= self._heat_deadline:
            await self._safety_off("time limit of %s s reached", self.max_heat_seconds)
        elif state.temperature is not None and state.temperature >= self.target_temperature:
            await self._safety_off(
                "target %.1f °C reached (%.1f °C)", self.target_temperature, state.temperature
            )

    async def _safety_off(self, reason: str, *args: object) -> None:
        _LOGGER.info("Turning heater off: " + reason, *args)
        try:
            await self.client.heat_off()
        except EKGError:
            # Leave heating=True so the next poll (2 s) tries again.
            _LOGGER.exception("Failed to turn heater off; will retry")
            return
        self._mark_off()

    def _mark_off(self) -> None:
        self.heating = False
        self._heat_deadline = None
        self.update_interval = IDLE_INTERVAL

    async def async_heat_on(self) -> None:
        state = self.data
        if (
            state is not None
            and state.temperature is not None
            and state.temperature >= self.target_temperature
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="already_at_target",
                translation_placeholders={
                    "temperature": f"{state.temperature:.1f}",
                    "target": f"{self.target_temperature:.1f}",
                },
            )
        try:
            await self.client.heat_on(max_seconds=self.max_heat_seconds)
        except EKGError as err:
            raise HomeAssistantError(f"Failed to turn heater on: {err}") from err
        self.heating = True
        self._heat_deadline = time.monotonic() + self.max_heat_seconds
        self.update_interval = HEATING_INTERVAL
        self.async_update_listeners()
        await self.async_request_refresh()

    async def async_heat_off(self) -> None:
        try:
            await self.client.heat_off()
        except EKGError as err:
            raise HomeAssistantError(f"Failed to turn heater off: {err}") from err
        self._mark_off()
        self.async_update_listeners()
        await self.async_request_refresh()

    def set_target_temperature(self, value: float) -> None:
        self.target_temperature = value
        self.async_update_listeners()
