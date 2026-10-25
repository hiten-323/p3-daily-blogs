"""Regression tests for the evidence-backed cross-platform learning loop."""
from __future__ import annotations

import datetime as dt
import json

from content_generator.analytics import platform_learning
from content_generator.core import learning_engine
from content_generator.prompts.growth_engine import platforms


def test_reconcile_only_verified_ledger_records(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    ledger_path = tmp_path / "publishing_ledger.json"
    posts_path.write_text(json.dumps([{
        "media_id": "old_1", "asset_id": "threads_day1", "platform": "",
        "published_at": "2026-01-01T00:00:00", "measurement_snapshots": [],
    }]), encoding="utf-8")
    ledger_path.write_text(json.dumps({"records": {
        "live": {
            "status": "VERIFIED_LIVE", "platform": "youtube", "remote_id": "yt_1",
            "url": "https://youtube.com/shorts/yt_1", "verified_at": "2026-10-20T00:00:00+00:00",
            "day_number": 10, "content_id": "c1",
        },
        "failed": {"status": "FAILED", "platform": "facebook", "remote_id": "fb_1"},
    }}), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setattr(platform_learning, "LEDGER_PATH", ledger_path)

    result = platform_learning.reconcile_verified_publications()
    rows = json.loads(posts_path.read_text(encoding="utf-8"))
    assert result["added"] == 1
    assert result["skipped_unverified"] == 1
    assert next(p for p in rows if p["media_id"] == "old_1")["platform"] == "threads"
    added = next(p for p in rows if p["media_id"] == "yt_1")
    assert added["platform"] == "youtube"
    assert added["publication_status"] == "VERIFIED_LIVE"
    assert added["permalink"] == "https://youtube.com/shorts/yt_1"


def test_youtube_native_metrics_are_real_api_values(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(platform_learning, "_request_json", lambda *a, **k: {
        "items": [{"statistics": {"viewCount": "120", "likeCount": "9", "commentCount": "2"}}]
    })
    assert platform_learning._fetch_youtube("video123") == {
        "views": 120, "likes": 9, "comments": 2,
    }


def test_cross_platform_observations_progress_to_one_learning_sample(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    now = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    published = (now - dt.timedelta(hours=200)).isoformat()
    posts_path.write_text(json.dumps([{
        "media_id": "yt_1", "asset_id": "youtube_day1", "platform": "youtube",
        "published_at": published, "hook": "A specific hook", "topic": "buying guide",
        "format": "short", "insights_recorded": False, "measurement_snapshots": [],
        "fetch_attempts_by_window": {}, "failed_windows": [],
    }]), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    calls = []
    monkeypatch.setattr(platform_learning, "_fetch_platform_metrics", lambda post: (
        {"views": 100, "likes": 8, "comments": 2}, "measured"
    ))
    monkeypatch.setattr(learning_engine, "record_performance", lambda **kwargs: calls.append(kwargs) or kwargs)

    first = platform_learning.fetch_pending_platform_metrics(now=now)
    second = platform_learning.fetch_pending_platform_metrics(now=now)
    third = platform_learning.fetch_pending_platform_metrics(now=now)
    row = json.loads(posts_path.read_text(encoding="utf-8"))[0]

    assert first["snapshots"] == 1
    assert second["snapshots"] == 1
    assert third["snapshots"] == 1
    assert len(row["measurement_snapshots"]) == 3
    assert len(calls) == 1
    assert calls[0]["platform"] == "youtube"
    assert calls[0]["observation_window"] == "7d"
    assert row["insights_recorded"] is True


def test_platform_learning_is_injected_into_prompt(monkeypatch):
    monkeypatch.setattr(
        learning_engine, "get_platform_learning_block",
        lambda platform: f"TEST MEASURED LESSON FOR {platform}",
    )
    block = platforms._platform_learning("threads")
    assert block == "TEST MEASURED LESSON FOR threads"


def test_timezone_aware_publication_timestamp_is_measurable():
    from content_generator.analytics.insights_fetcher import _hours_since
    now = dt.datetime(2026, 10, 25, 12, 0)
    assert _hours_since("2026-10-25T00:00:00+00:00", now) > 0
