from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.ollama_cloud_usage.api import (
    OllamaParseError,
    UsageReport,
    build_activity_window,
    build_legacy_session_window,
    build_legacy_weekly_window,
    parse_balance,
    parse_usage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _usage_report(name: str) -> UsageReport:
    return parse_usage(_load(name))


def test_parse_usage_reads_totals_and_buckets():
    report = _usage_report("api_usage_30d.json")

    assert report.range == "30d"
    assert report.granularity == "day"
    assert report.totals.request_count > 0
    assert len(report.buckets) == 31
    assert report.buckets[-1].partial is True
    assert report.buckets[0].partial is False
    assert report.starting_at < report.ending_at


def test_parse_usage_reads_model_groups():
    report = _usage_report("api_usage_24h.json")

    assert report.granularity == "hour"
    assert len(report.buckets) == 25
    models = {model.name for bucket in report.buckets for model in bucket.models}
    assert "minimax-m3.1-flash" in models


def test_parse_usage_totals_group_counts_match_bucket_sum():
    report = _usage_report("api_usage_30d.json")

    assert sum(bucket.request_count for bucket in report.buckets) == (
        report.totals.request_count
    )


def test_parse_usage_raises_without_totals():
    with pytest.raises(OllamaParseError):
        parse_usage({"range": "7d", "granularity": "day", "buckets": []})


def test_parse_usage_raises_on_unknown_granularity():
    with pytest.raises(OllamaParseError):
        parse_usage(
            {
                "range": "7d",
                "granularity": "week",
                "from": "2026-01-01T00:00:00Z",
                "until": "2026-01-08T00:00:00Z",
                "totals": {"request_count": 0},
                "buckets": [],
            }
        )


def test_parse_usage_raises_on_non_object():
    with pytest.raises(OllamaParseError):
        parse_usage(["nope"])


def test_parse_usage_raises_on_bad_timestamp():
    with pytest.raises(OllamaParseError):
        parse_usage(
            {
                "range": "7d",
                "granularity": "day",
                "from": "not-a-date",
                "until": "2026-01-08T00:00:00Z",
                "totals": {"request_count": 0},
                "buckets": [],
            }
        )


def test_parse_usage_raises_on_bad_request_count():
    with pytest.raises(OllamaParseError):
        parse_usage(
            {
                "range": "7d",
                "granularity": "day",
                "from": "2026-01-01T00:00:00Z",
                "until": "2026-01-08T00:00:00Z",
                "totals": {"request_count": "many"},
                "buckets": [],
            }
        )


def test_parse_balance_legacy_plan():
    report = parse_balance(_load("api_balance_legacy.json"))

    assert report.is_legacy_plan is True
    assert report.is_credit_plan is False
    assert report.session_remaining_percent == pytest.approx(78.56)
    assert report.session_resets_at == datetime(2026, 11, 23, tzinfo=UTC)
    assert report.weekly_remaining_percent == pytest.approx(71.2)
    assert report.purchased_balance_usd == pytest.approx(0)


def test_parse_balance_credit_plan():
    report = parse_balance(
        {
            "included": {
                "balance_usd": 72.5,
                "allowance_usd": 100,
                "period": {
                    "from": "2026-09-15T09:30:00Z",
                    "until": "2026-10-15T09:30:00Z",
                },
            },
            "purchased": {"balance_usd": 25},
        }
    )

    assert report.is_credit_plan is True
    assert report.is_legacy_plan is False
    assert report.included_balance_usd == pytest.approx(72.5)
    assert report.included_allowance_usd == pytest.approx(100)
    assert report.included_period_start == datetime(2026, 9, 15, 9, 30, tzinfo=UTC)
    assert report.included_period_end == datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
    assert report.purchased_balance_usd == pytest.approx(25)


def test_parse_balance_raises_without_usable_payload():
    with pytest.raises(OllamaParseError):
        parse_balance({"included": {}, "purchased": {}})


def test_parse_balance_raises_on_non_object():
    with pytest.raises(OllamaParseError):
        parse_balance("nope")


def test_parse_balance_raises_on_bad_remaining_percent():
    with pytest.raises(OllamaParseError):
        parse_balance(
            {
                "included": {
                    "session": {
                        "remaining_percent": "lots",
                        "resets_at": "2026-01-01T00:00:00Z",
                    }
                }
            }
        )


def test_build_activity_window_covers_28_days():
    report = _usage_report("api_usage_30d.json")
    window = build_activity_window(report)

    assert window.period_type == "last_4_weeks"
    assert window.starting_at.hour == 0
    assert window.starting_at.minute == 0
    assert window.starting_at == report.ending_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=28)
    assert window.request_count > 0
    assert window.models
    assert window.total_requests == sum(m.request_count for m in window.models)


def test_build_legacy_session_window_uses_balance_reset():
    hourly = _usage_report("api_usage_24h.json")
    balance = parse_balance(_load("api_balance_legacy.json"))
    window = build_legacy_session_window(hourly, balance)

    assert window is not None
    assert window.period_type == "session"
    assert window.remaining_percent == balance.session_remaining_percent
    assert window.resets_at == balance.session_resets_at
    assert window.ending_at == balance.session_resets_at
    assert window.starting_at == balance.session_resets_at - timedelta(hours=7)


def test_build_legacy_weekly_window_uses_balance_reset():
    report = _usage_report("api_usage_30d.json")
    balance = parse_balance(_load("api_balance_legacy.json"))
    window = build_legacy_weekly_window(report, balance)

    assert window is not None
    assert window.period_type == "weekly"
    assert window.remaining_percent == balance.weekly_remaining_percent
    assert window.resets_at == balance.weekly_resets_at
    assert window.starting_at == balance.weekly_resets_at - timedelta(days=7)


def test_build_legacy_session_window_without_session_limit():
    hourly = _usage_report("api_usage_24h.json")
    daily = _usage_report("api_usage_30d.json")
    balance = parse_balance(
        {
            "included": {
                "balance_usd": 10,
                "allowance_usd": 100,
                "period": {
                    "from": "2026-09-15T09:30:00Z",
                    "until": "2026-10-15T09:30:00Z",
                },
            },
            "purchased": {"balance_usd": 0},
        }
    )

    assert build_legacy_session_window(hourly, balance) is None
    assert build_legacy_weekly_window(daily, balance) is None


def test_every_sensor_is_documented_in_readme():
    import json
    from pathlib import Path

    root = Path(__file__).parent.parent
    readme = (root / "README.md").read_text()
    strings = json.loads(
        (root / "custom_components" / "ollama_cloud_usage" / "strings.json").read_text()
    )

    undocumented = [key for key in strings["entity"]["sensor"] if key not in readme]
    assert not undocumented
