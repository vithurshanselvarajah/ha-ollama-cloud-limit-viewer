from pathlib import Path

import pytest

from custom_components.ollama_cloud_usage.api import (
    OllamaParseError,
    parse_usage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_usage_full_payload():
    payload = (FIXTURES / "api_usage.json").read_text()
    import json

    data = parse_usage(json.loads(payload))

    assert data.session is not None
    assert data.weekly is not None
    assert data.activity is not None

    assert data.session.usage_usd == pytest.approx(0.001)
    assert data.session.total_requests == 3
    assert [m.name for m in data.session.models] == ["minimax-m3", "gemma4:31b"]
    assert data.session.starting_at is None
    assert data.session.ending_at is None

    assert data.weekly.usage_usd == pytest.approx(0.025)
    assert data.weekly.total_requests == 180

    assert data.activity.usage_usd == pytest.approx(0.0)
    assert data.activity.total_requests == 0
    assert data.activity.period_type == "last_4_weeks"
    assert data.activity.starting_at == "2026-08-24T00:00:00Z"
    assert data.activity.ending_at == "2026-09-14T21:52:52.558286586Z"


def test_parse_usage_only_session_window():
    payload = {
        "limits": {
            "session": {
                "usage": "0.5",
                "models": [{"name": "llama3:8b", "request_count": "7"}],
            }
        }
    }
    data = parse_usage(payload)

    assert data.session is not None
    assert data.session.usage_usd == 0.5
    assert data.session.total_requests == 7
    assert data.weekly is None
    assert data.activity is None


def test_parse_usage_missing_models_field_is_ok():
    payload = {"limits": {"weekly": {"usage": 0.01}}}
    data = parse_usage(payload)
    assert data.weekly is not None
    assert data.weekly.usage_usd == pytest.approx(0.01)
    assert data.weekly.models == []
    assert data.weekly.total_requests == 0


def test_parse_usage_raises_when_no_windows():
    payload = {"limits": {}, "activity": None}
    with pytest.raises(OllamaParseError):
        parse_usage(payload)


def test_parse_usage_raises_on_non_object():
    with pytest.raises(OllamaParseError):
        parse_usage(["nope", "not", "a", "dict"])


def test_parse_usage_raises_on_bad_usage_value():
    payload = {"limits": {"session": {"usage": "not-a-number"}}}
    with pytest.raises(OllamaParseError):
        parse_usage(payload)


def test_parse_usage_raises_on_bad_models_type():
    payload = {"limits": {"session": {"usage": 0.1, "models": "oops"}}}
    with pytest.raises(OllamaParseError):
        parse_usage(payload)


def test_parse_usage_raises_on_model_missing_name():
    payload = {"limits": {"session": {"usage": 0.1, "models": [{"request_count": 3}]}}}
    with pytest.raises(OllamaParseError):
        parse_usage(payload)


def test_parse_usage_raises_on_bad_request_count():
    payload = {
        "limits": {
            "session": {"usage": 0.1, "models": [{"name": "x", "request_count": "x"}]}
        }
    }
    with pytest.raises(OllamaParseError):
        parse_usage(payload)
