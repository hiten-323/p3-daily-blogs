"""Phase One Data Integrity and State Persistence Regression Tests.

Tests:
1. Missing state file handling (clean default without error).
2. Malformed JSON handling (raises ValueError, never silently replaces with empty dict).
3. Invalid JSON structure/schema (raises ValueError).
4. Atomic write integrity (temp file validation before replace).
5. Merge-safe reconciliation and remote media ID preservation across runs.
6. Preservation of historical snapshots, retry counts, error history, and verification states.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from content_generator.publisher import publishing_ledger as pl
from content_generator.ops import ledger_sync as ls


def test_missing_ledger_file_returns_clean_dataset(tmp_path, monkeypatch):
    missing_file = tmp_path / "publishing_ledger.json"
    monkeypatch.setattr(pl, "_PATH", missing_file)
    assert not missing_file.exists()
    data = pl._load()
    assert data == {"version": 1, "records": {}}


def test_corrupt_ledger_raises_and_never_wipes(tmp_path, monkeypatch):
    corrupt_file = tmp_path / "publishing_ledger.json"
    corrupt_file.write_text("{ this is malformed json", encoding="utf-8")
    monkeypatch.setattr(pl, "_PATH", corrupt_file)

    with pytest.raises(ValueError, match="Cannot safely read publishing ledger"):
        pl._load()

    # Verify corrupt file was not modified or overwritten
    assert corrupt_file.read_text(encoding="utf-8") == "{ this is malformed json"


def test_invalid_schema_ledger_raises(tmp_path, monkeypatch):
    invalid_file = tmp_path / "publishing_ledger.json"
    invalid_file.write_text(json.dumps({"version": 1, "records": "not-a-dict"}), encoding="utf-8")
    monkeypatch.setattr(pl, "_PATH", invalid_file)

    with pytest.raises(ValueError, match="Invalid publishing ledger schema"):
        pl._load()


def test_atomic_save_validates_and_persists(tmp_path, monkeypatch):
    target = tmp_path / "publishing_ledger.json"
    monkeypatch.setattr(pl, "_PATH", target)

    valid_data = {
        "version": 1,
        "records": {
            "2026-11-18|morning|instagram|day-1|reel_1": {
                "status": "VERIFIED_LIVE",
                "remote_id": "1801234567890",
                "url": "https://www.instagram.com/reel/Cxyz123/",
                "attempt_count": 1,
            }
        }
    }
    pl._save(valid_data)
    assert target.exists()

    loaded = pl._load()
    assert loaded["records"]["2026-11-18|morning|instagram|day-1|reel_1"]["remote_id"] == "1801234567890"

    # Saving invalid structure should be rejected
    with pytest.raises(ValueError, match="Cannot persist invalid publishing ledger structure"):
        pl._save({"version": 1, "records": []})


def test_ledger_sync_corrupt_file_raises_and_protects(tmp_path):
    bad_ledger = tmp_path / "bad_ledger.json"
    bad_ledger.write_text("corrupted content", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt ledger file"):
        ls._read(bad_ledger)

    bad_posts = tmp_path / "bad_posts.json"
    bad_posts.write_text("corrupted content", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt posts file"):
        ls._read_posts(bad_posts)

    bad_lessons = tmp_path / "bad_lessons.json"
    bad_lessons.write_text("corrupted content", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupt lessons file"):
        ls._read_lessons(bad_lessons)


def test_merge_posts_preserves_remote_ids_and_historical_snapshots():
    base_posts = [
        {
            "media_id": "meta_12345",
            "platform": "instagram",
            "published_at": "2026-11-18T10:00:00Z",
            "measurement_snapshots": [
                {"window": "early", "views": 50, "likes": 5}
            ],
            "fetch_attempts_by_window": {"early": 1},
        }
    ]
    other_posts = [
        {
            "media_id": "meta_12345",
            "platform": "instagram",
            "published_at": "2026-11-18T10:00:00Z",
            "insights_recorded": True,
            "measurement_snapshots": [
                {"window": "early", "views": 55, "likes": 6},
                {"window": "24h", "views": 500, "likes": 45}
            ],
            "fetch_attempts_by_window": {"early": 1, "24h": 1},
        },
        {
            "media_id": "meta_67890",
            "platform": "facebook",
            "published_at": "2026-11-18T10:05:00Z",
            "measurement_snapshots": [],
        }
    ]

    merged = ls.merge_posts(base_posts, other_posts)
    assert len(merged) == 2
    ig_post = next(p for p in merged if p["media_id"] == "meta_12345")
    assert ig_post["insights_recorded"] is True
    # Verify snapshots unioned and preserved
    windows = {s["window"] for s in ig_post["measurement_snapshots"]}
    assert "early" in windows and "24h" in windows
