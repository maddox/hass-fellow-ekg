from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FellowEKGConfigEntry
from .entity import FellowEKGEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowEKGConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FellowEKGHeaterSwitch(entry.runtime_data, "heater")])


class FellowEKGHeaterSwitch(FellowEKGEntity, SwitchEntity):
    """Raw heater control, supervised by the coordinator.

    The kettle doesn't report the heater GPIO, so the state reflects what this
    integration last commanded (``assumed_state``). Turning on heats until the
    "Auto-off temperature" or the time limit set in the integration's options.
    """

    _attr_assumed_state = True

    @property
    def is_on(self) -> bool:
        return self.coordinator.heating

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "auto_off_temperature": self.coordinator.target_temperature,
            "max_heat_seconds": self.coordinator.max_heat_seconds,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_heat_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_heat_off()
