from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.const import (
    CONF_COOKIE,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.ollama_cloud_usage.scraper import OllamaUsageData


async def test_setup_unload_entry(hass: HomeAssistant):
    """Test that setting up and unloading the config entry works."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main Account",
        data={
            CONF_COOKIE: "test_cookie_value",
            CONF_SCAN_INTERVAL: 60,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse"
    ) as mock_fetch:
        mock_fetch.return_value = OllamaUsageData(
            session_percent=15.0,
            session_resets_in="2 hours",
            weekly_percent=45.0,
            weekly_resets_in="3 days",
            model_note="Llama 3 8B",
        )

        # Setup entry
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Check entry runtime data (coordinator)
        assert entry.runtime_data is not None
        assert entry.runtime_data.data.session_percent == 15.0
        assert entry.runtime_data.data.session_resets_in == "2 hours"
        assert entry.runtime_data.data.weekly_percent == 45.0
        assert entry.runtime_data.data.weekly_resets_in == "3 days"
        assert entry.runtime_data.data.model_note == "Llama 3 8B"

        # Unload entry
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
