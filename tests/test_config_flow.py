from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
import pytest
from aiohttp import ClientError

from custom_components.ollama_cloud_usage.const import DOMAIN
from custom_components.ollama_cloud_usage.scraper import (
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
)


async def test_config_flow_success(hass: HomeAssistant):
    """Test standard successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse"
    ) as mock_fetch:
        mock_fetch.return_value = OllamaUsageData(
            session_percent=1.5,
            session_resets_in="15 hours",
            weekly_percent=10.0,
            weekly_resets_in="3 days",
            model_note="Llama 3 8B",
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "account_name": "My Account",
                "cookie": "valid_cookie",
                "scan_interval": 120,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result2["title"] == "My Account"
        assert result2["data"] == {
            "account_name": "My Account",
            "cookie": "valid_cookie",
            "scan_interval": 120,
        }


@pytest.mark.parametrize(
    ("exception", "expected_error"),
    [
        (OllamaAuthError("Unauthorized"), "invalid_cookie"),
        (OllamaParseError("Parse failed"), "parse_error"),
        (ClientError("Connection failed"), "cannot_connect"),
        (ValueError("Unexpected error"), "unknown"),
    ],
)
async def test_config_flow_errors(hass: HomeAssistant, exception, expected_error):
    """Test config flow errors during authentication validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse",
        side_effect=exception,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "account_name": "My Account",
                "cookie": "invalid_cookie",
                "scan_interval": 120,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.FlowResultType.FORM
        assert result2["errors"] == {"base": expected_error}
