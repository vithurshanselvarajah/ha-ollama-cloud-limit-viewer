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


def test_parse_usage_raises_on_missing_meters():
    with pytest.raises(OllamaParseError):
        parse_usage("<html><body></body></html>")