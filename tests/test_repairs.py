from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    BalanceReport,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.const import DOMAIN
from custom_components.ollama_cloud_usage.repairs import (
    ISSUE_TEAM_SCOPE_UNAVAILABLE,
)

API_KEY = "abcdef0123456789abcdef0123456789.0123456789abcdefghijklmnopqrstuvwxyzABCD"


def _data(reported_scope: str) -> OllamaUsageData:
    balance = BalanceReport(
        session_remaining_percent=72.5,
        session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    session = UsageWindow(label="session", request_count=12)
    return OllamaUsageData(session=session, balance=balance, scope=reported_scope)


async def _setup(hass: HomeAssistant, scope: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={
            "account_name": "Main",
            "api_key": API_KEY,
            "scan_interval": 300,
            "scope": scope,
        },
    )
    with patch(
        "custom_components.ollama_cloud_usage.coordinator.fetch_and_parse",
        return_value=_data("self"),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return hass.config_entries.async_entries(DOMAIN)[0]


async def test_issue_raised_when_team_scope_unavailable(hass: HomeAssistant):
    entry = await _setup(hass, "team")

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(
        DOMAIN, f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry.entry_id}"
    )

    assert issue is not None
    assert issue.translation_placeholders == {"account_name": "Main"}


async def test_no_issue_for_personal_scope(hass: HomeAssistant):
    entry = await _setup(hass, "self")

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(
        DOMAIN, f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry.entry_id}"
    )

    assert issue is None


async def test_issue_cleared_when_team_scope_works(hass: HomeAssistant):
    entry = await _setup(hass, "team")

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(
            DOMAIN, f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry.entry_id}"
        )
        is not None
    )

    with patch(
        "custom_components.ollama_cloud_usage.coordinator.fetch_and_parse",
        return_value=_data("team"),
    ):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert (
        registry.async_get_issue(
            DOMAIN, f"{ISSUE_TEAM_SCOPE_UNAVAILABLE}_{entry.entry_id}"
        )
        is None
    )
