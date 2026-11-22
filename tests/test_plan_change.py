from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ollama_cloud_usage.api import (
    BalanceReport,
    ModelUsage,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.const import DOMAIN

API_KEY = "abcdef0123456789abcdef0123456789.0123456789abcdefghijklmnopqrstuvwxyzABCD"


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Main",
        unique_id="main",
        version=3,
        data={
            "account_name": "Main",
            "api_key": API_KEY,
            "scan_interval": 300,
            "scope": "self",
        },
    )


def _legacy_data() -> OllamaUsageData:
    balance = BalanceReport(
        session_remaining_percent=72.5,
        session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        weekly_remaining_percent=40.0,
        weekly_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    return OllamaUsageData(
        session=UsageWindow(label="session", request_count=12, remaining_percent=72.5),
        weekly=UsageWindow(label="weekly", request_count=180, remaining_percent=40.0),
        activity=UsageWindow(label="last_4_weeks", request_count=900),
        balance=balance,
    )


def _credit_data() -> OllamaUsageData:
    balance = BalanceReport(
        included_balance_usd=72.5,
        included_allowance_usd=100.0,
        included_period_start=datetime(2026, 11, 1, tzinfo=UTC),
        included_period_end=datetime(2026, 12, 1, tzinfo=UTC),
        purchased_balance_usd=25.0,
    )
    return OllamaUsageData(
        session=UsageWindow(label="session", request_count=12),
        activity=UsageWindow(
            label="last_4_weeks",
            request_count=900,
            input_tokens=1000,
            cached_input_tokens=400,
            output_tokens=200,
            models=[ModelUsage(name="gemma4:31b", request_count=5, usage_usd=0.01234)],
        ),
        balance=balance,
    )


async def _setup(hass: HomeAssistant, data: OllamaUsageData) -> MockConfigEntry:
    entry = _entry()
    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=data,
    ):
        await hass.config_entries.async_add(entry)
        await hass.async_block_till_done()
    return entry


def _keys(hass: HomeAssistant, entry: MockConfigEntry) -> set[str]:
    registry = er.async_get(hass)
    return {
        registry_entry.unique_id.removeprefix(f"{entry.entry_id}_")
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
    }


async def test_upgrade_to_credit_plan_adds_new_sensors(hass: HomeAssistant):
    entry = await _setup(hass, _legacy_data())

    assert "included_balance" not in _keys(hass, entry)
    assert "weekly_requests" in _keys(hass, entry)
    assert "session_remaining" in _keys(hass, entry)

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_credit_data(),
    ):
        entry.runtime_data.async_set_updated_data(_credit_data())
        await hass.async_block_till_done()

    keys = _keys(hass, entry)
    assert "included_balance" in keys
    assert "included_allowance" in keys
    assert "last_4_weeks_input_tokens" in keys
    assert "last_4_weeks_cache_hit_ratio" in keys
    assert "weekly_requests" not in keys
    assert "session_remaining" not in keys
    assert "weekly_remaining" not in keys


async def test_downgrade_to_legacy_plan_removes_credit_sensors(hass: HomeAssistant):
    entry = await _setup(hass, _credit_data())

    assert "included_balance" in _keys(hass, entry)
    assert "weekly_requests" not in _keys(hass, entry)

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_legacy_data(),
    ):
        entry.runtime_data.async_set_updated_data(_legacy_data())
        await hass.async_block_till_done()

    keys = _keys(hass, entry)
    assert "included_balance" not in keys
    assert "last_4_weeks_input_tokens" not in keys
    assert "weekly_requests" in keys
    assert "session_remaining" in keys


async def test_plan_change_keeps_entity_ids_stable(hass: HomeAssistant):
    entry = await _setup(hass, _legacy_data())

    registry = er.async_get(hass)
    before = {
        registry_entry.unique_id.removeprefix(f"{entry.entry_id}_"): (
            registry_entry.entity_id
        )
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
    }

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_credit_data(),
    ):
        entry.runtime_data.async_set_updated_data(_credit_data())
        await hass.async_block_till_done()

    after = {
        registry_entry.unique_id.removeprefix(f"{entry.entry_id}_"): (
            registry_entry.entity_id
        )
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
    }
    for key in ("session_requests", "last_4_weeks_requests", "purchased_balance"):
        assert after[key] == before[key], f"{key} entity id changed"


async def test_sensors_become_available_after_plan_change(hass: HomeAssistant):
    entry = await _setup(hass, _legacy_data())

    with patch(
        "custom_components.ollama_cloud_usage.fetch_and_parse",
        return_value=_credit_data(),
    ):
        entry.runtime_data.async_set_updated_data(_credit_data())
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id == f"{entry.entry_id}_included_balance":
            state = hass.states.get(registry_entry.entity_id)
            assert state is not None
            assert state.state == "72.5"
            return
    raise AssertionError("included_balance entity not found")
