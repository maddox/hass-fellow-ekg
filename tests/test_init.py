from datetime import timedelta
from unittest.mock import patch

import pytest
from custom_components.fellow_ekg.vendor.fellow_ekg import EKGConnectionError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import make_state

SWITCH = "switch.fellow_ekg_pro_heater"
NUMBER = "number.fellow_ekg_pro_auto_off_temperature"


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _tick(hass, seconds: float):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def _switch(hass, service: str):
    await hass.services.async_call("switch", service, {"entity_id": SWITCH}, blocking=True)


async def test_entities(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)

    assert float(hass.states.get("sensor.fellow_ekg_pro_water_temperature").state) == pytest.approx(26.11, abs=0.01)
    assert float(hass.states.get("sensor.fellow_ekg_pro_kettle_target_temperature").state) == pytest.approx(96.11, abs=0.01)
    assert float(hass.states.get("sensor.fellow_ekg_pro_boiling_point").state) == 100.0
    mode = hass.states.get("sensor.fellow_ekg_pro_mode")
    assert mode.state == "Off"
    assert mode.attributes["raw_mode"] == "S_Off"
    assert mode.attributes["nw"] == 0
    assert hass.states.get(SWITCH).state == STATE_OFF
    # Auto-off defaults to the kettle's own target.
    assert float(hass.states.get(NUMBER).state) == 96.1
    mock_client.heat_on.assert_not_called()
    mock_client.heat_off.assert_not_called()


async def test_not_ready_when_unreachable(hass: HomeAssistant, mock_client, config_entry) -> None:
    mock_client.get_firmware_info.side_effect = EKGConnectionError("down")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unavailable_when_polling_fails(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    mock_client.get_state.side_effect = EKGConnectionError("down")
    await _tick(hass, 20)
    assert hass.states.get("sensor.fellow_ekg_pro_water_temperature").state == STATE_UNAVAILABLE


async def test_heater_turns_off_at_target(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call("number", "set_value", {"entity_id": NUMBER, "value": 80}, blocking=True)

    await _switch(hass, "turn_on")
    mock_client.heat_on.assert_awaited_once_with(max_seconds=600)
    assert hass.states.get(SWITCH).state == STATE_ON

    mock_client.get_state.return_value = make_state(temperature=70.0)
    await _tick(hass, 3)
    mock_client.heat_off.assert_not_called()

    mock_client.get_state.return_value = make_state(temperature=80.2)
    await _tick(hass, 6)
    mock_client.heat_off.assert_awaited_once()
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_heater_turns_off_at_time_limit(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _switch(hass, "turn_on")
    with patch("custom_components.fellow_ekg.coordinator.time.monotonic", return_value=10**9):
        await _tick(hass, 3)
    mock_client.heat_off.assert_awaited_once()
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_failed_safety_off_is_retried(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _switch(hass, "turn_on")
    mock_client.get_state.return_value = make_state(temperature=99.0)
    mock_client.heat_off.side_effect = [EKGConnectionError("blip"), None]

    await _tick(hass, 3)
    assert hass.states.get(SWITCH).state == STATE_ON
    await _tick(hass, 6)
    assert mock_client.heat_off.await_count == 2
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_refuses_to_heat_when_already_at_target(hass: HomeAssistant, mock_client, config_entry) -> None:
    mock_client.get_state.return_value = make_state(temperature=97.0)
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError):
        await _switch(hass, "turn_on")
    mock_client.heat_on.assert_not_called()


async def test_manual_turn_off(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _switch(hass, "turn_on")
    await _switch(hass, "turn_off")
    mock_client.heat_off.assert_awaited_once()
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_unload_turns_heater_off(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _switch(hass, "turn_on")
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_client.heat_off.assert_awaited_once()
    mock_client.close.assert_awaited_once()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_unload_keeps_library_timer_if_heat_off_fails(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    await _switch(hass, "turn_on")
    mock_client.heat_off.side_effect = EKGConnectionError("down")
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_client.close.assert_not_called()


async def test_unload_when_idle_does_not_touch_heater(hass: HomeAssistant, mock_client, config_entry) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    mock_client.heat_off.assert_not_called()


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("S_Off", "Off"),
        ("S_HeatHold", "Heat hold"),
        ("S_BOIL", "Boil"),
        ("S_keep_warm", "Keep warm"),
        ("Idle", "Idle"),
        (None, None),
    ],
)
def test_humanize_mode(raw, shown) -> None:
    from custom_components.fellow_ekg.sensor import humanize_mode

    assert humanize_mode(raw) == shown
