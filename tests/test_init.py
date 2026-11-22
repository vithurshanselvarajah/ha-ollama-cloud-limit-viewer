from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    BalanceReport,
    ModelUsage,
    OllamaAuthError,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.const import DOMAIN

API_KEY = "abcdef0123456789abcdef0123456789.0123456789abcdefghijklmnopqrstuvwxyzABCD"


def _entry() -> ConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={"account_name": "Main", "api_key": API_KEY, "scan_interval": 300},
    )


def _legacy_data() -> OllamaUsageData:
    balance = BalanceReport(
        session_remaining_percent=72.5,
        session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        weekly_remaining_percent=40.0,
        weekly_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    session = UsageWindow(
        label="session",
        request_count=12,
        remaining_percent=72.5,
        period_type="session",
        starting_at=datetime(2026, 11, 22, 19, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
        resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        models=[ModelUsage(name="minimax-m3.1-flash", request_count=10)],
    )
    weekly = UsageWindow(
        label="weekly",
        request_count=180,
        remaining_percent=40.0,
        period_type="weekly",
        starting_at=datetime(2026, 11, 16, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
        resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        models=[ModelUsage(name="minimax-m3.1-flash", request_count=176)],
    )
    activity = UsageWindow(
        label="last_4_weeks",
        request_count=900,
        period_type="last_4_weeks",
        starting_at=datetime(2026, 10, 26, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
        models=[ModelUsage(name="minimax-m3.1-flash", request_count=880)],
    )
    return OllamaUsageData(
        session=session, weekly=weekly, activity=activity, balance=balance
    )


def _credit_data() -> OllamaUsageData:
    balance = BalanceReport(
        included_balance_usd=72.5,
        included_allowance_usd=100.0,
        included_period_start=datetime(2026, 11, 1, 9, 30, tzinfo=UTC),
        included_period_end=datetime(2026, 12, 1, 9, 30, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    session = UsageWindow(
        label="session",
        request_count=5,
        period_type="session",
        starting_at=datetime(2026, 11, 22, 19, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
        models=[ModelUsage(name="gemma4:31b", request_count=5)],
    )
    activity = UsageWindow(
        label="last_4_weeks",
        request_count=900,
        period_type="last_4_weeks",
        starting_at=datetime(2026, 10, 26, tzinfo=UTC),
        ending_at=datetime(2026, 11, 23, tzinfo=UTC),
    )
    return OllamaUsageData(session=session, activity=activity, balance=balance)


async def _setup_entry(hass: HomeAssistant, data: OllamaUsageData) -> ConfigEntry:
    entry = _entry()
    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=data,
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, entry: ConfigEntry, key: str) -> str | None:
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id == f"{entry.entry_id}_{key}":
            return hass.states.get(registry_entry.entity_id).state
    return None


def _keys(hass: HomeAssistant, entry: ConfigEntry) -> set[str]:
    registry = er.async_get(hass)
    return {
        registry_entry.unique_id.removeprefix(f"{entry.entry_id}_")
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
    }


async def test_legacy_plan_sensors(hass: HomeAssistant):
    entry = await _setup_entry(hass, _legacy_data())

    keys = _keys(hass, entry)

    assert "session_requests" in keys
    assert "weekly_requests" in keys
    assert "session_remaining" in keys
    assert "weekly_remaining" in keys
    assert "included_balance" not in keys
    assert "included_allowance" not in keys
    assert "session_spend" not in keys
    assert "weekly_spend" not in keys

    assert _state(hass, entry, "session_requests") == "12"
    assert _state(hass, entry, "weekly_requests") == "180"
    assert _state(hass, entry, "session_remaining") == "72.5"
    assert _state(hass, entry, "weekly_remaining") == "40.0"
    assert _state(hass, entry, "session_top_model") == "minimax-m3.1-flash"
    assert _state(hass, entry, "session_model_breakdown") == "minimax-m3.1-flash (10)"
    assert _state(hass, entry, "last_4_weeks_requests") == "900"
    assert _state(hass, entry, "purchased_balance") == "25.0"


async def test_spend_sensors_created_when_cost_is_reported(hass: HomeAssistant):
    data = _legacy_data()
    data.session.usage_usd = 0.0125
    data.weekly.usage_usd = 1.25
    entry = await _setup_entry(hass, data)

    keys = _keys(hass, entry)

    assert "session_spend" in keys
    assert "weekly_spend" in keys
    assert _state(hass, entry, "session_spend") == "0.0125"
    assert _state(hass, entry, "weekly_spend") == "1.25"


async def test_credit_plan_sensors(hass: HomeAssistant):
    entry = await _setup_entry(hass, _credit_data())

    keys = _keys(hass, entry)

    assert "included_balance" in keys
    assert "included_allowance" in keys
    assert "purchased_balance" in keys
    assert "included_period_end" in keys
    assert "weekly_requests" not in keys
    assert "session_remaining" not in keys

    assert _state(hass, entry, "included_balance") == "72.5"
    assert _state(hass, entry, "included_allowance") == "100.0"
    assert _state(hass, entry, "session_requests") == "5"


async def test_sensors_marked_unavailable_after_failed_update(hass: HomeAssistant):
    entry = _entry()

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        side_effect=OllamaAuthError("bad key"),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_stale_entities_are_removed(hass: HomeAssistant):
    entry = _entry()

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_legacy_data(),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_weekly_spend_legacy",
        config_entry=entry,
        suggested_object_id="stale",
    )
    assert stale.entity_id in registry.entities

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_credit_data(),
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert stale.entity_id not in registry.entities
    assert "weekly_requests" not in _keys(hass, entry)


async def test_options_override_scan_interval(hass: HomeAssistant):
    entry = _entry()

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_legacy_data(),
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()

    assert entry.runtime_data.update_interval == timedelta(seconds=300)

    hass.config_entries.async_update_entry(entry, options={"scan_interval": 60})
    await hass.async_block_till_done()

    assert entry.runtime_data.update_interval == timedelta(seconds=60)
