from pathlib import Path

import pytest

from custom_components.ollama_cloud_usage.scraper import (
    OllamaParseError,
    parse_usage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_usage_extracts_values():
    html = (FIXTURES / "settings.html").read_text()
    data = parse_usage(html)

    assert data.session_percent == 12.5
    assert data.session_resets_in == "3 hours"
    assert data.weekly_percent == 45.0
    assert data.weekly_resets_in == "2 days"
    assert "llama3:8b, 42 requests" in (data.model_note or "")
    assert "qwen2.5:7b" in (data.model_note or "")

    # Legacy model fields should not leak into monthly.
    assert data.monthly_percent is None
    assert data.monthly_resets_in is None
    assert data.tier is None


def test_parse_usage_raises_on_missing_meters():
    with pytest.raises(OllamaParseError):
        parse_usage("<html><body></body></html>")


def test_parse_usage_monthly_model():
    html = (FIXTURES / "settings_monthly.html").read_text()
    data = parse_usage(html)

    assert data.has_monthly is True
    assert data.has_legacy is False
    assert data.monthly_percent == 44.3
    assert data.monthly_resets_in == "3 weeks"
    assert data.monthly_resets_at == "2026-10-01T21:51:07Z"
    assert data.tier == "free"

    # Legacy fields are None on the new model.
    assert data.session_percent is None
    assert data.session_resets_in is None
    assert data.weekly_percent is None
    assert data.weekly_resets_in is None

    # Model note is sourced from the monthly meter's segments.
    assert "gemma4:31b, 331 requests" in (data.model_note or "")


def test_parse_usage_legacy_weekly_saturates_session():
    html = """
    <html><body>
      <div><span>Session usage</span><span>40%</span></div>
      <div data-usage-meter=""></div>
      <div>Resets in 5 hours.</div>

      <div><span>Weekly usage</span><span>100%</span></div>
      <div data-usage-meter=""></div>
      <div>Resets in 1 day.</div>
    </body></html>
    """
    data = parse_usage(html)
    assert data.session_percent == 100.0
    assert data.session_resets_in == "1 day"
    assert data.weekly_percent == 100.0


def test_parse_usage_monthly_without_tier_badge():
    html = """
    <html><body>
      <div><span>Pro usage</span><span>12% used</span></div>
      <div data-usage-meter="">
        <button data-usage-segment="" data-model="llama3:8b" data-requests="3"></button>
      </div>
      <div data-time="2026-10-01T00:00:00Z">Resets in 18 days.</div>
    </body></html>
    """
    data = parse_usage(html)
    assert data.monthly_percent == 12.0
    assert data.monthly_resets_in == "18 days"
    assert data.monthly_resets_at == "2026-10-01T00:00:00Z"
    # No "Included usage" heading in this fixture, so tier is unknown.
    assert data.tier is None


def test_parse_usage_pro_legacy_model():
    html = (FIXTURES / "settings_pro_legacy.html").read_text()
    data = parse_usage(html)

    assert data.has_legacy is True
    assert data.has_monthly is False
    assert data.session_percent == 4.2
    assert data.session_resets_in == "4 hours"
    assert data.weekly_percent == 1.1
    assert data.weekly_resets_in == "3 days"
    assert data.tier == "pro"

    # Monthly fields stay None on the legacy model.
    assert data.monthly_percent is None
    assert data.monthly_resets_in is None

    # Model note lists every model that contributed to the weekly meter.
    note = data.model_note or ""
    assert "gemma4:31b, 8 requests" in note
    assert "deepseek-v4-flash:0731, 2 requests" in note
    assert "minimax-m3, 110 requests" in note


def test_parse_usage_raises_when_no_values_extracted():
    html = """
    <html><body>
      <div data-usage-meter=""></div>
      <div>Resets soon.</div>
    </body></html>
    """
    with pytest.raises(OllamaParseError):
        parse_usage(html)
