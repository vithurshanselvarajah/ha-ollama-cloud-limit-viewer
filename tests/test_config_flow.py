from __future__ import annotations

from unittest.mock import patch

import pytest
from aiohttp import ClientError
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaParseError,
    OllamaUsageData,
)
from custom_components.ollama_cloud_usage.const import DOMAIN


async def test_config_flow_success(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse"
    ) as mock_fetch:
        mock_fetch.return_value = OllamaUsageData()

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


async def test_config_flow_aborts_for_duplicate_account(hass: HomeAssistant):
    await hass.config_entries.async_add(
        MockConfigEntry(
            domain=DOMAIN,
            title="My Account",
            unique_id="my account",
            version=3,
            data={
                "account_name": "My Account",
                "api_key": "key",
                "scan_interval": 120,
            },
        )
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "account_name": "My Account",
            "api_key": "another_key",
            "scan_interval": 120,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN)[0].data["api_key"] == "key"


async def test_reauth_flow_replaces_api_key(hass: HomeAssistant):
    await hass.config_entries.async_add(
        MockConfigEntry(
            domain=DOMAIN,
            title="My Account",
            unique_id="my account",
            version=3,
            data={
                "account_name": "My Account",
                "api_key": "old_key",
                "scan_interval": 120,
            },
        )
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await entry.start_reauth_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse",
        return_value=OllamaUsageData(),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "new_key"}
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data["api_key"] == "new_key"
    assert entry.data["account_name"] == "My Account"


async def test_reauth_flow_reports_invalid_key(hass: HomeAssistant):
    await hass.config_entries.async_add(
        MockConfigEntry(
            domain=DOMAIN,
            title="My Account",
            unique_id="my account",
            version=3,
            data={
                "account_name": "My Account",
                "api_key": "old_key",
                "scan_interval": 120,
            },
        )
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.ollama_cloud_usage.config_flow.fetch_and_parse",
        side_effect=OllamaAuthError("Unauthorized"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_key": "bad_key"}
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_api_key"}
    assert entry.data["api_key"] == "old_key"


async def test_options_flow_updates_scan_interval(hass: HomeAssistant):
    await hass.config_entries.async_add(
        MockConfigEntry(
            domain=DOMAIN,
            title="My Account",
            unique_id="my account",
            version=3,
            data={
                "account_name": "My Account",
                "api_key": "key",
                "scan_interval": 120,
            },
        )
    )

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 300}
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["data"] == {"scan_interval": 300}
    assert hass.config_entries.async_entries(DOMAIN)[0].options == {
        "scan_interval": 300
    }
