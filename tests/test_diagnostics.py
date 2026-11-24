from homeassistant.core import HomeAssistant

from custom_components.fellow_ekg.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["firmware"]["version"] == "1.2.5CL CLI"
    assert diag["heating"] is False
    assert "mode=S_Off" in diag["state_raw"]
