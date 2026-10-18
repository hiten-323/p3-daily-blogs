"""
Regression tests for:
1. Shared publication tracking across daily dispatcher and publish recovery into published_posts.json.
2. Ledger sync merge_posts() deduplication by media_id, snapshot preservation, and retry count tracking.
3. fetch_pending_insights() Instagram-only filtering to protect Graph API circuit breaker.
4. growth_health.measurement_health() explicit permission_missing diagnosis.
5. audio_director.measure_track_tempo() audio beat synchronization and tempo verification.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from content_generator.analytics import insights_fetcher
from content_generator.ops import ledger_sync, growth_health
from content_generator.creative import audio_director


def test_track_dispatch_results_records_all_platforms(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    monkeypatch.setattr(insights_fetcher, "_POSTS_PATH", str(posts_path))
    monkeypatch.setattr(insights_fetcher, "_LEARNING_DIR", str(tmp_path))

    content = {
        "carousel": {"caption": "Pure coffee carousel", "hook": "Stop drinking chicory"},
        "yt_short": {"title": "Coffee Roast Secrets", "tags": ["coffee", "pure"]},
        "facebook_post": {"hook": "Facebook community post"},
        "linkedin_post": {"headline": "B2B Coffee Insight"},
        "threads_post": {"hook": "Quick coffee thought"},
    }
    dispatch_results = {
        "instagram": {"success": True, "media_id": "ig_12345", "hashtags_used": "#coffee"},
        "youtube": {"success": True, "video_id": "yt_67890"},
        "facebook": {"success": True, "post_id": "fb_11111"},
        "linkedin": {"success": True, "post_id": "li_22222"},
        "threads": {"success": True, "post_id": "th_33333"},
    }

    insights_fetcher.track_dispatch_results(dispatch_results, content, day_number=42)

    data = json.loads(posts_path.read_text(encoding="utf-8"))
    assert len(data) == 5
    platforms = {p["platform"] for p in data}
    assert platforms == {"instagram", "youtube", "facebook", "linkedin", "threads"}

    ig_rec = next(p for p in data if p["platform"] == "instagram")
    assert ig_rec["media_id"] == "ig_12345"
    assert ig_rec["asset_id"] == "instagram_day42"
    assert ig_rec["hook"] == "Stop drinking chicory"
    assert ig_rec["format"] == "carousel"

    yt_rec = next(p for p in data if p["platform"] == "youtube")
    assert yt_rec["media_id"] == "yt_67890"
    assert yt_rec["hook"] == "Coffee Roast Secrets"


def test_track_dispatch_results_idempotency(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    monkeypatch.setattr(insights_fetcher, "_POSTS_PATH", str(posts_path))
    monkeypatch.setattr(insights_fetcher, "_LEARNING_DIR", str(tmp_path))

    content = {"carousel": {"caption": "Hello", "hook": "Hello"}}
    dispatch_results = {"instagram": {"success": True, "media_id": "ig_dup_1"}}

    # Call twice
    insights_fetcher.track_dispatch_results(dispatch_results, content, day_number=1)
    insights_fetcher.track_dispatch_results(dispatch_results, content, day_number=1)

    data = json.loads(posts_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["media_id"] == "ig_dup_1"


def test_ledger_sync_merge_posts():
    base = [
        {
            "media_id": "ig_100",
            "asset_id": "instagram_day10",
            "platform": "instagram",
            "insights_recorded": False,
            "measurement_snapshots": [{"window": "24h", "views": 120}],
            "fetch_attempts_by_window": {"24h": 1},
            "failed_windows": [],
        },
        {
            "media_id": "yt_200",
            "asset_id": "youtube_day10",
            "platform": "youtube",
        },
    ]

    other = [
        {
            "media_id": "ig_100",
            "asset_id": "instagram_day10",
            "platform": "instagram",
            "insights_recorded": True,
            "measurement_snapshots": [
                {"window": "24h", "views": 120},
                {"window": "72h", "views": 350},
            ],
            "fetch_attempts_by_window": {"24h": 2, "72h": 1},
            "failed_windows": ["failed_probe"],
            "hook": "Recovered Hook",
        },
        {
            "media_id": "li_300",
            "asset_id": "linkedin_day10",
            "platform": "linkedin",
        },
    ]

    merged = ledger_sync.merge_posts(base, other)
    assert len(merged) == 3

    ig = next(p for p in merged if p["media_id"] == "ig_100")
    assert ig["insights_recorded"] is True
    assert len(ig["measurement_snapshots"]) == 2
    assert ig["fetch_attempts_by_window"] == {"24h": 2, "72h": 1}
    assert ig["failed_windows"] == ["failed_probe"]
    assert ig["hook"] == "Recovered Hook"

    media_ids = [p["media_id"] for p in merged]
    assert media_ids == ["ig_100", "yt_200", "li_300"]


def test_fetch_pending_insights_skips_non_instagram_posts(monkeypatch, tmp_path):
    posts_path = tmp_path / "published_posts.json"
    posts_data = [
        {
            "media_id": "yt_video_999",
            "asset_id": "youtube_day1",
            "platform": "youtube",
            "published_at": "2020-01-01T00:00:00",
            "insights_recorded": False,
        },
        {
            "media_id": "li_share_888",
            "asset_id": "linkedin_day1",
            "platform": "linkedin",
            "published_at": "2020-01-01T00:00:00",
            "insights_recorded": False,
        },
        {
            "media_id": "th_post_777",
            "asset_id": "threads_day1",
            "platform": "threads",
            "published_at": "2020-01-01T00:00:00",
            "insights_recorded": False,
        },
    ]
    posts_path.write_text(json.dumps(posts_data), encoding="utf-8")
    monkeypatch.setattr(insights_fetcher, "_POSTS_PATH", str(posts_path))
    monkeypatch.setattr(insights_fetcher, "_LEARNING_DIR", str(tmp_path))
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "fake_token")

    called_media_ids = []

    def fake_fetch_media_insights(mid):
        called_media_ids.append(mid)
        return {"views": 10}

    monkeypatch.setattr(insights_fetcher, "_fetch_media_insights", fake_fetch_media_insights)
    monkeypatch.setattr(insights_fetcher, "_fetch_follower_count", lambda: 100)
    monkeypatch.setattr(insights_fetcher, "_fetch_account_insights", lambda: {})

    res = insights_fetcher.fetch_pending_insights()
    # Non-Instagram media IDs must never be sent to _fetch_media_insights
    assert len(called_media_ids) == 0
    assert res["recorded"] == 0
    assert res["snapshots"] == 0


def test_growth_health_permission_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(growth_health, "LEARNING", tmp_path)
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "mock_token")

    with patch("content_generator.ops.meta_token_health.inspect_token") as mock_inspect:
        # Token has basic and publish scopes, but lacks instagram_manage_insights
        mock_inspect.return_value = {
            "type": "USER",
            "expires": "never",
            "scopes": ["instagram_basic", "instagram_content_publish", "pages_read_engagement"],
            "valid": True,
        }
        res = growth_health.measurement_health()
        assert res["status"] == "permission_missing"
        assert res["missing_permission"] == "instagram_manage_insights"


def test_audio_director_measure_track_tempo():
    # Test on an existing wav file in music_library
    music_dir = Path("music_library")
    lofi_path = music_dir / "lofi_cafe.wav"
    if lofi_path.exists():
        measured = audio_director.measure_track_tempo(str(lofi_path), seconds=10.0)
        assert measured["measured"] is True
        assert measured["bpm"] == 120.0
        assert measured["bar_seconds"] == 2.0
        assert 0.0 in measured["downbeats"]
        assert 2.0 in measured["downbeats"]

    # Test on non-existent track
    fallback = audio_director.measure_track_tempo("non_existent.wav", seconds=10.0)
    assert fallback["measured"] is False
    assert fallback["bpm"] == 120.0
    assert fallback["bar_seconds"] == 2.0
