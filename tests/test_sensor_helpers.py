from __future__ import annotations

from datetime import UTC, datetime

from custom_components.ollama_cloud_usage.api import (
    BalanceReport,
    ModelUsage,
    OllamaUsageData,
    UsageWindow,
)
from custom_components.ollama_cloud_usage.sensor import (
    _available_keys,
    _balance_value,
    _window_cache_hit_ratio,
    _window_model_spend_breakdown,
    _window_other_requests,
)


def test_window_other_requests_is_none_without_remainder():
    assert _window_other_requests(None) is None
    assert _window_other_requests(UsageWindow(label="session")) is None
    assert (
        _window_other_requests(UsageWindow(label="session", remainder_request_count=7))
        == 7
    )


def test_window_model_spend_breakdown_is_none_without_costs():
    window = UsageWindow(
        label="session",
        models=[ModelUsage(name="a", request_count=3)],
    )

    assert _window_model_spend_breakdown(None) is None
    assert _window_model_spend_breakdown(window) is None


def test_window_cache_hit_ratio_is_none_without_tokens():
    assert _window_cache_hit_ratio(None) is None
    assert _window_cache_hit_ratio(UsageWindow(label="session")) is None


def test_balance_value_is_none_without_balance():
    assert _balance_value(None, "included_balance_usd") is None


def test_available_keys_without_balance():
    data = OllamaUsageData(session=UsageWindow(label="session", request_count=1))

    keys = _available_keys(data)

    assert "session_requests" in keys
    assert "session_remaining" not in keys
    assert "included_balance" not in keys


def test_available_keys_ignores_non_own_entities():
    assert _available_keys(OllamaUsageData()) == set()


def test_available_keys_includes_remainder_and_spend():
    window = UsageWindow(
        label="session",
        request_count=5,
        usage_usd=1.25,
        remainder_request_count=3,
        models=[ModelUsage(name="a", request_count=5, usage_usd=1.25)],
    )
    data = OllamaUsageData(
        session=window,
        balance=BalanceReport(
            session_remaining_percent=50.0,
            session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
            purchased_balance_usd=1.0,
        ),
    )

    keys = _available_keys(data)

    assert "session_spend" in keys
    assert "session_model_spend_breakdown" in keys
    assert "session_other_model_requests" in keys
    assert "session_remaining" in keys
    assert "purchased_balance" in keys


def test_every_sensor_value_function_is_callable():
    from custom_components.ollama_cloud_usage.sensor import (
        SENSOR_DESCRIPTIONS,
        _available_keys,
    )

    data = OllamaUsageData(
        session=UsageWindow(
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
            models=[ModelUsage(name="a", request_count=12, usage_usd=0.5)],
            remainder_request_count=3,
        ),
        weekly=UsageWindow(
            label="weekly",
            request_count=180,
            usage_usd=2.5,
            input_tokens=1000,
            cached_input_tokens=400,
            output_tokens=200,
            remaining_percent=40.0,
            period_type="weekly",
            starting_at=datetime(2026, 11, 16, tzinfo=UTC),
            ending_at=datetime(2026, 11, 23, tzinfo=UTC),
            resets_at=datetime(2026, 11, 23, tzinfo=UTC),
            models=[ModelUsage(name="a", request_count=180, usage_usd=2.5)],
            remainder_request_count=7,
        ),
        activity=UsageWindow(
            label="last_4_weeks",
            request_count=900,
            usage_usd=12.5,
            input_tokens=10000,
            cached_input_tokens=4000,
            output_tokens=2000,
            period_type="last_4_weeks",
            starting_at=datetime(2026, 10, 26, tzinfo=UTC),
            ending_at=datetime(2026, 11, 23, tzinfo=UTC),
            models=[ModelUsage(name="a", request_count=900, usage_usd=12.5)],
            remainder_request_count=11,
        ),
        balance=BalanceReport(
            included_balance_usd=72.5,
            included_allowance_usd=100.0,
            included_period_start=datetime(2026, 11, 1, tzinfo=UTC),
            included_period_end=datetime(2026, 12, 1, tzinfo=UTC),
            purchased_balance_usd=25.0,
            session_remaining_percent=72.5,
            session_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
            weekly_remaining_percent=40.0,
            weekly_resets_at=datetime(2026, 11, 23, tzinfo=UTC),
        ),
    )

    active = _available_keys(data)
    covered = 0
    for description in SENSOR_DESCRIPTIONS:
        if description.key not in active:
            continue
        value = description.value_fn(data)
        assert value is not None, description.key
        covered += 1

    assert covered == len(SENSOR_DESCRIPTIONS)
