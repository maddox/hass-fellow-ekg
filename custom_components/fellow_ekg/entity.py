from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FellowEKGCoordinator


class FellowEKGEntity(CoordinatorEntity[FellowEKGCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FellowEKGCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name="Fellow EKG Pro",
            manufacturer="Fellow",
            model="Stagg EKG Pro",
            sw_version=coordinator.firmware.version,
            configuration_url=f"http://{entry.data[CONF_HOST]}/",
        )
