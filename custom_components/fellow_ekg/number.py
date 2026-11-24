from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MAX_TARGET, MIN_TARGET
from .coordinator import FellowEKGConfigEntry
from .entity import FellowEKGEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowEKGConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FellowEKGAutoOffTemperature(entry.runtime_data, "auto_off_temperature")])


class FellowEKGAutoOffTemperature(FellowEKGEntity, RestoreNumber):
    """Temperature at which the integration turns the heater switch off.

    This is stored in Home Assistant, not on the kettle. On first setup it
    defaults to the kettle's own target temperature.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TARGET
    _attr_native_max_value = MAX_TARGET
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            value = last.native_value
        elif (kettle_target := self.coordinator.data.target_temperature) is not None:
            value = round(kettle_target, 1)
        else:
            return
        self.coordinator.target_temperature = min(max(value, MIN_TARGET), MAX_TARGET)

    @property
    def native_value(self) -> float:
        return self.coordinator.target_temperature

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_target_temperature(value)
