"""Regression tests for the evidence-backed cross-platform learning loop."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from content_generator.analytics import insights_fetcher, platform_learning
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
        "correct_existing": {
            "status": "VERIFIED_LIVE", "platform": "youtube", "remote_id": "old_1",
            "url": "https://youtube.com/shorts/old_1", "verified_at": "2026-10-20T00:00:00+00:00",
        },
        "failed": {"status": "FAILED", "platform": "facebook", "remote_id": "fb_1"},
    }}), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setattr(platform_learning, "LEDGER_PATH", ledger_path)

    result = platform_learning.reconcile_verified_publications()
    rows = json.loads(posts_path.read_text(encoding="utf-8"))
    assert result["added"] == 1
    assert result["skipped_unverified"] == 1
    assert next(p for p in rows if p["media_id"] == "old_1")["platform"] == "youtube"
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
    published_dt = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
    published = published_dt.isoformat()
    now = published_dt + dt.timedelta(hours=24)
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
    second = platform_learning.fetch_pending_platform_metrics(now=published_dt + dt.timedelta(hours=72))
    third = platform_learning.fetch_pending_platform_metrics(now=published_dt + dt.timedelta(hours=168))
    row = json.loads(posts_path.read_text(encoding="utf-8"))[0]

    assert first["snapshots"] == 1
    assert second["snapshots"] == 1
    assert third["snapshots"] == 1
    assert len(row["measurement_snapshots"]) == 3
    assert len(calls) == 3
    assert [call["observation_window"] for call in calls] == ["24h", "72h", "7d"]
    assert all(call["publication_id"] == "yt_1" for call in calls)
    assert calls[-1]["platform"] == "youtube"
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



def test_learning_record_upsert_is_idempotent_but_keeps_same_day_posts_distinct(tmp_path, monkeypatch):
    log_path = tmp_path / "performance_log.json"
    monkeypatch.setattr(learning_engine, "_LOG_PATH", str(log_path))
    base = {
        "asset_id": "instagram_day300",
        "track": "brand",
        "platform": "instagram",
        "observation_window": "7d",
    }
    learning_engine.record_performance(**base, publication_id="media-a", metrics={"views": 100, "likes": 10, "comments": 2})
    learning_engine.record_performance(**{**base, "observation_window": "72h"}, publication_id="media-a", metrics={"views": 150, "likes": 12, "comments": 3})
    learning_engine.record_performance(**base, publication_id="media-b", metrics={"views": 100, "likes": 10, "comments": 2})
    rows = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(rows) == 2
    latest = next(row for row in rows if row["publication_id"] == "media-a")
    assert latest["metrics"]["views"] == 150
    assert latest["observation_window"] == "72h"



def test_stale_publication_is_not_mislabeled_as_a_24h_observation(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    now = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    posts_path.write_text(json.dumps([{
        "media_id": "fb_old", "asset_id": "facebook_day1", "platform": "facebook",
        "published_at": (now - dt.timedelta(days=30)).isoformat(),
        "insights_recorded": False, "measurement_snapshots": [],
        "fetch_attempts_by_window": {}, "failed_windows": [],
    }]), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setattr(platform_learning, "_fetch_platform_metrics", lambda post: (_ for _ in ()).throw(AssertionError("stale post must not be queried")))

    result = platform_learning.fetch_pending_platform_metrics(now=now)
    row = json.loads(posts_path.read_text(encoding="utf-8"))[0]
    assert result["snapshots"] == 0
    assert row["measurement_terminal"] is True
    assert row["measurement_status"] == "too_old_for_comparable_window"
    assert row["measurement_snapshots"] == []



def test_single_measured_post_informs_next_day_without_claiming_a_winner(monkeypatch):
    monkeypatch.setattr(learning_engine, "_load_log", lambda: [{
        "asset_id": "threads_day300",
        "publication_id": "threads-media-1",
        "platform": "threads",
        "observation_window": "24h",
        "posted_at": "2026-10-25T10:00:00",
        "hook": "A precise coffee question",
        "topic": "conversation",
        "format": "discussion",
        "metrics": {"views": 100, "likes": 12, "comments": 4},
    }])
    monkeypatch.setattr(learning_engine, "is_teachable", lambda entry: True)

    block = learning_engine.get_platform_learning_block("threads")
    assert "PROVISIONAL THREADS SIGNALS" in block
    assert "views=100" in block
    assert "not enough evidence to declare winners" in block



def test_prompt_block_calls_platform_learning_without_breaking_generation(monkeypatch):
    monkeypatch.setattr(
        learning_engine, "get_platform_learning_block",
        lambda platform: f"INJECTED LESSON FOR {platform}",
    )
    block = platforms.prompt_block("threads", "Purica", 300)
    assert "PLATFORM MODULE (threads)." in block
    assert "INJECTED LESSON FOR threads" in block



def test_corrupt_tracker_is_never_overwritten_by_reconciliation(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    ledger_path = tmp_path / "publishing_ledger.json"
    original = '{"records": broken'
    posts_path.write_text(original, encoding="utf-8")
    ledger_path.write_text(json.dumps({"records": {}}), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setattr(platform_learning, "LEDGER_PATH", ledger_path)

    with pytest.raises(ValueError, match="Refusing to overwrite malformed JSON"):
        platform_learning.reconcile_verified_publications()
    assert posts_path.read_text(encoding="utf-8") == original


def test_invalid_tracker_shape_is_not_replaced_with_an_empty_list(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    posts_path.write_text(json.dumps({"unexpected": "object"}), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)

    with pytest.raises(ValueError, match="Invalid published-post tracker schema"):
        platform_learning.fetch_pending_platform_metrics()
    assert json.loads(posts_path.read_text(encoding="utf-8")) == {"unexpected": "object"}



def test_missing_platform_credentials_do_not_burn_retry_budget(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    published = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
    posts_path.write_text(json.dumps([{
        "media_id": "yt_missing_auth", "asset_id": "youtube_day1", "platform": "youtube",
        "published_at": published.isoformat(), "measurement_snapshots": [],
        "fetch_attempts_by_window": {}, "failed_windows": [],
    }]), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)

    result = platform_learning.fetch_pending_platform_metrics()
    row = json.loads(posts_path.read_text(encoding="utf-8"))[0]
    assert result["blocked"] == 1
    assert row["measurement_status"] == "missing_youtube_credentials"
    assert row["fetch_attempts_by_window"] == {}
    assert row["failed_windows"] == []


def test_corrupt_performance_log_is_not_overwritten(tmp_path, monkeypatch):
    log_path = tmp_path / "performance_log.json"
    original = '{"not": "an array"}'
    log_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(learning_engine, "_LOG_PATH", str(log_path))

    with pytest.raises(ValueError, match="Refusing to overwrite invalid performance log"):
        learning_engine.record_performance(
            asset_id="threads_day300", track="brand", platform="threads",
            publication_id="media-1", observation_window="24h",
            metrics={"views": 100, "likes": 10},
        )
    assert log_path.read_text(encoding="utf-8") == original



def test_instagram_tracker_does_not_replace_corrupt_json(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    original = "{broken tracker"
    posts_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(insights_fetcher, "_POSTS_PATH", str(posts_path))

    with pytest.raises(ValueError, match="Cannot safely read published-post tracker"):
        insights_fetcher._load_posts()
    assert posts_path.read_text(encoding="utf-8") == original


def test_cross_platform_fetch_budget_defers_excess_posts_without_spending_attempts(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for media_id, age in (("newest", 25), ("older", 26)):
        rows.append({
            "media_id": media_id, "asset_id": "youtube_day1", "platform": "youtube",
            "published_at": (now - dt.timedelta(hours=age)).isoformat(),
            "measurement_snapshots": [], "fetch_attempts_by_window": {}, "failed_windows": [],
        })
    posts_path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setattr(platform_learning, "MAX_API_FETCHES_PER_RUN", 1)
    monkeypatch.setattr(platform_learning, "_fetch_platform_metrics", lambda post: (
        {"views": 100, "likes": 10}, "measured"
    ))
    monkeypatch.setattr(learning_engine, "record_performance", lambda **kwargs: kwargs)

    result = platform_learning.fetch_pending_platform_metrics(now=now)
    persisted = json.loads(posts_path.read_text(encoding="utf-8"))
    assert result["snapshots"] == 1
    assert result["pending"] == 1
    deferred = next(row for row in persisted if row["media_id"] == "older")
    assert deferred["fetch_attempts_by_window"] == {}
    assert deferred["measurement_snapshots"] == []
