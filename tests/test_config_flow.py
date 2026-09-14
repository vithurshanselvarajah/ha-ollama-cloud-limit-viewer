from unittest.mock import patch

import pytest
from aiohttp import ClientError
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.ollama_cloud_usage.api import (
    ModelUsage,
    OllamaApiError,
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.const import DOMAIN


def _sample_window() -> UsageWindow:
    return UsageWindow(
        label="session",
        usage_usd=0.001,
        models=[ModelUsage(name="minimax-m3", request_count=1)],
    )


async def test_config_flow_success(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse"
    ) as mock_fetch:
        mock_fetch.return_value = OllamaUsageData(session=_sample_window())

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "account_name": "My Account",
                "api_key": "valid_key.dotpartrest",
                "scan_interval": 120,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result2["title"] == "My Account"
        assert result2["data"] == {
            "account_name": "My Account",
            "api_key": "valid_key.dotpartrest",
            "scan_interval": 120,
        }


@pytest.mark.parametrize(
    ("exception", "expected_error"),
    [
        (OllamaAuthError("Unauthorized"), "invalid_api_key"),
        (OllamaParseError("Parse failed"), "parse_error"),
        (OllamaApiError("Server exploded"), "api_error"),
        (ClientError("Connection failed"), "cannot_connect"),
        (ValueError("Unexpected error"), "unknown"),
    ],
)
async def test_config_flow_errors(hass: HomeAssistant, exception, expected_error):
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
                "api_key": "bad_key",
                "scan_interval": 120,
            },
        )
        await hass.async_block_till_done()

        assert result2["type"] == data_entry_flow.FlowResultType.FORM
        assert result2["errors"] == {"base": expected_error}
