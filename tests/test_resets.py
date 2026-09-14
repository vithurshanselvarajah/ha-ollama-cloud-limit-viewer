from datetime import UTC, datetime

from custom_components.ollama_cloud_usage.resets import (
    SessionResetTracker,
    WeeklyResetTracker,
)


def utc(y, m, d, hh=0, mm=0, ss=0, us=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, us, tzinfo=UTC)


class TestSessionResetTracker:
    def test_no_anchor_until_observation(self):
        t = SessionResetTracker()
        assert t.has_anchor is False
        assert t.next_reset(utc(2026, 9, 14, 12, 0)) is None

    def test_first_observation_creates_no_anchor(self):
        t = SessionResetTracker()
        t.observe(0.001, utc(2026, 9, 14, 12, 30))
        assert t.has_anchor is False
        assert t.next_reset(utc(2026, 9, 14, 12, 30)) is None

    def test_small_drift_is_not_a_reset(self):
        t = SessionResetTracker()
        t.observe(0.020, utc(2026, 9, 14, 12, 0))
        t.observe(0.021, utc(2026, 9, 14, 12, 30))
        t.observe(0.022, utc(2026, 9, 14, 13, 0))
        assert t.has_anchor is False

    def test_big_drop_sets_anchor_to_current_bucket(self):
        t = SessionResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 30))
        t.observe(0.001, utc(2026, 9, 14, 15, 10))
        assert t.has_anchor is True
        assert t.next_reset(utc(2026, 9, 14, 15, 10)) == utc(2026, 9, 14, 20, 0)

    def test_next_reset_returns_next_bucket_when_inside_one(self):
        t = SessionResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 30))
        t.observe(0.001, utc(2026, 9, 14, 15, 10))
        assert t.next_reset(utc(2026, 9, 14, 16, 0)) == utc(2026, 9, 14, 20, 0)

    def test_next_reset_rolls_forward_across_days(self):
        t = SessionResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 15, 10))
        t.observe(0.001, utc(2026, 9, 14, 15, 11))
        assert t.next_reset(utc(2026, 9, 15, 3, 0)) == utc(2026, 9, 15, 5, 0)

    def test_next_reset_exact_boundary_gives_next_bucket(self):
        t = SessionResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 10, 0))
        t.observe(0.001, utc(2026, 9, 14, 10, 1))
        assert t.next_reset(utc(2026, 9, 14, 15, 0)) == utc(2026, 9, 14, 20, 0)

    def test_subsequent_drop_re_anchors(self):
        t = SessionResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        t.observe(0.001, utc(2026, 9, 14, 15, 10))
        t.observe(0.020, utc(2026, 9, 14, 16, 0))
        t.observe(0.001, utc(2026, 9, 14, 20, 5))
        assert t.next_reset(utc(2026, 9, 14, 20, 30)) == utc(2026, 9, 15, 1, 0)


class TestWeeklyResetTracker:
    def test_no_anchor_until_observation(self):
        t = WeeklyResetTracker()
        assert t.has_anchor is False

    def test_first_observation_creates_no_anchor(self):
        t = WeeklyResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        assert t.has_anchor is False

    def test_big_drop_anchors_to_monday(self):
        t = WeeklyResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        t.observe(0.001, utc(2026, 9, 18, 9, 0))
        assert t.has_anchor is True
        assert t.next_reset(utc(2026, 9, 18, 9, 0)) == utc(2026, 9, 21, 0, 0)

    def test_next_reset_rolls_week_by_week(self):
        t = WeeklyResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        t.observe(0.001, utc(2026, 9, 18, 9, 0))
        assert t.next_reset(utc(2026, 9, 22, 12, 0)) == utc(2026, 9, 28, 0, 0)
        assert t.next_reset(utc(2026, 9, 28, 0, 30)) == utc(2026, 10, 5, 0, 0)

    def test_exact_monday_midnight_rolls_to_next_monday(self):
        t = WeeklyResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        t.observe(0.001, utc(2026, 9, 18, 9, 0))
        assert t.next_reset(utc(2026, 9, 21, 0, 0)) == utc(2026, 9, 28, 0, 0)

    def test_zero_usage_does_not_trigger_reset(self):
        t = WeeklyResetTracker()
        t.observe(0.025, utc(2026, 9, 14, 12, 0))
        t.observe(0.0, utc(2026, 9, 18, 9, 0))
        assert t.has_anchor is True

    def test_watchdog_threshold_is_exactly_half(self):
        t = WeeklyResetTracker()
        t.observe(1.0, utc(2026, 9, 14, 12, 0))
        t.observe(0.5, utc(2026, 9, 18, 9, 0))
        assert t.has_anchor is False
        t2 = WeeklyResetTracker()
        t2.observe(1.0, utc(2026, 9, 14, 12, 0))
        t2.observe(0.49, utc(2026, 9, 18, 9, 0))
        assert t2.has_anchor is True
