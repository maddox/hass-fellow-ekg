from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .vendor.fellow_ekg import EKGState
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FellowEKGConfigEntry, FellowEKGCoordinator
from .entity import FellowEKGEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FellowEKGSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EKGState], Any]
    attrs_fn: Callable[[EKGState], dict[str, Any]] | None = None


def _temperature(key: str, fn: Callable[[EKGState], float | None], **kwargs: Any) -> FellowEKGSensorDescription:
    return FellowEKGSensorDescription(
        key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=fn,
        **kwargs,
    )


SENSORS: tuple[FellowEKGSensorDescription, ...] = (
    _temperature(
        "water_temperature",
        lambda s: s.temperature,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _temperature("kettle_target_temperature", lambda s: s.target_temperature),
    _temperature(
        "boil_temperature",
        lambda s: s.boil_temperature,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FellowEKGSensorDescription(
        key="mode",
        value_fn=lambda s: humanize_mode(s.mode),
        attrs_fn=lambda s: {
            "raw_mode": s.mode,
            "screen": s.screen,
            "clock": s.clock,
            **s.kettle_flags,
        },
    ),
)

# Firmware mode codes we've observed, with friendly names. Anything else
# falls back to humanize_mode's generic cleanup. The raw code is always
# available as the "raw_mode" attribute, for automations.
KNOWN_MODES: dict[str, str] = {
    "S_Off": "Off",
}


def humanize_mode(mode: str | None) -> str | None:
    """'S_Off' -> 'Off'; unknown codes like 'S_HeatHold' -> 'Heat hold'."""
    if mode is None:
        return None
    if mode in KNOWN_MODES:
        return KNOWN_MODES[mode]
    text = re.sub(r"^S_", "", mode)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).replace("_", " ")
    text = " ".join(text.split()).lower()
    return text[:1].upper() + text[1:] if text else mode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FellowEKGConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(FellowEKGSensor(coordinator, d) for d in SENSORS)


class FellowEKGSensor(FellowEKGEntity, SensorEntity):
    entity_description: FellowEKGSensorDescription

    def __init__(self, coordinator: FellowEKGCoordinator, description: FellowEKGSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
