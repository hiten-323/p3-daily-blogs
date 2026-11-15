"""Regression tests for 24h/72h/7d measurement staging."""
from __future__ import annotations
import datetime

from content_generator.analytics.insights_fetcher import MEASUREMENT_WINDOWS, _next_due_window


def _post(age_hours: int, snapshots=None):
    now = datetime.datetime(2026, 8, 12, 12, 0, 0)
    published = now - datetime.timedelta(hours=age_hours)
    return {"published_at": published.isoformat(), "measurement_snapshots": snapshots or []}, now


def test_windows_are_ordered_and_terminal() -> None:
    assert MEASUREMENT_WINDOWS == (("early", 2), ("24h", 24), ("72h", 72), ("7d", 168))


def test_24h_is_first_due_window() -> None:
    post, now = _post(30)
    assert _next_due_window(post, now) == ("24h", 24)


def test_72h_follows_24h() -> None:
    post, now = _post(80, [{"window": "24h"}])
    assert _next_due_window(post, now) == ("72h", 72)


def test_7d_is_terminal_learning_window() -> None:
    post, now = _post(200, [{"window": "24h"}, {"window": "72h"}])
    assert _next_due_window(post, now) == ("7d", 168)


def test_completed_windows_are_not_repeated() -> None:
    post, now = _post(200, [
        {"window": "24h"}, {"window": "72h"}, {"window": "7d"}
    ])
    assert _next_due_window(post, now) is None
