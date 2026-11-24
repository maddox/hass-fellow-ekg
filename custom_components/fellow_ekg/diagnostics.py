from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import FellowEKGConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FellowEKGConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "firmware": asdict(coordinator.firmware),
        "heating": coordinator.heating,
        "auto_off_temperature": coordinator.target_temperature,
        # Raw output helps decode modes and flags we haven't seen yet.
        "state_raw": state.raw if state else None,
    }
