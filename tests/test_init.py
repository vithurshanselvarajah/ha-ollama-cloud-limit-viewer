from custom_components.ollama_cloud_usage import _detect_mode
from custom_components.ollama_cloud_usage.scraper import OllamaUsageData


def test_detect_mode_legacy_only():
    data = OllamaUsageData(
        session_percent=10.0,
        session_resets_in="1 hour",
        weekly_percent=20.0,
        weekly_resets_in="1 day",
    )
    assert _detect_mode(data) == "legacy"


def test_detect_mode_monthly_only():
    data = OllamaUsageData(
        monthly_percent=44.3,
        monthly_resets_in="3 weeks",
        tier="free",
        model_note="gemma4:31b, 331 requests",
    )
    assert _detect_mode(data) == "monthly"


def test_detect_mode_mixed_returns_none():
    data = OllamaUsageData(
        session_percent=10.0,
        weekly_percent=20.0,
        monthly_percent=44.3,
    )
    assert _detect_mode(data) is None


def test_detect_mode_empty_returns_none():
    assert _detect_mode(OllamaUsageData()) is None
