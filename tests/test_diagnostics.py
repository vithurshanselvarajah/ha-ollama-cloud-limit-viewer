from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    BalanceReport,
    ModelUsage,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.const import DOMAIN
from custom_components.ollama_cloud_usage.diagnostics import (
    async_get_config_entry_diagnostics,
)

API_KEY = "abcdef0123456789abcdef0123456789.0123456789abcdefghijklmnopqrstuvwxyzABCD"


def _data() -> OllamaUsageData:
    balance = BalanceReport(
        session_remaining_percent=72.5,
        session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    session = UsageWindow(
        label="session",
        request_count=12,
        usage_usd=0.5,
        input_tokens=100,
        cached_input_tokens=40,
        output_tokens=20,
        remaining_percent=72.5,
        period_type="session",
        starting_at=datetime(2026, 11, 22, 17, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
        resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        models=[ModelUsage(name="minimax-m3.1-flash", request_count=10, usage_usd=0.4)],
        remainder_request_count=2,
    )
    return OllamaUsageData(session=session, balance=balance, scope="self")


async def test_diagnostics_redacts_api_key(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={"account_name": "Main", "api_key": API_KEY, "scan_interval": 300},
    )
    with patch(
        "custom_components.ollama_cloud_usage.coordinator.fetch_and_parse",
        return_value=_data(),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"]["api_key"] == "**REDACTED**"
    assert API_KEY not in str(diagnostics)


async def test_diagnostics_contains_usage_data(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={"account_name": "Main", "api_key": API_KEY, "scan_interval": 300},
    )
    with patch(
        "custom_components.ollama_cloud_usage.coordinator.fetch_and_parse",
        return_value=_data(),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["scope"] == "self"
    assert diagnostics["last_update_success"] is True
    assert diagnostics["balance"]["purchased_balance_usd"] == 25.0
    assert diagnostics["windows"]["session"]["request_count"] == 12
    assert diagnostics["windows"]["session"]["models"][0]["model"] == (
        "minimax-m3.1-flash"
    )
    assert diagnostics["windows"]["session"]["cache_hit_ratio"] == 40.0
