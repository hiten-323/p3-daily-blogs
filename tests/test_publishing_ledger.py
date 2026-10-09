import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_success_is_persisted_and_duplicate_is_blocked(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.publisher import platform_verification as verifier
    monkeypatch.setattr(verifier, "verify_remote_post", lambda platform, record: {"state": "found", "method": "test_readback", "detail": "confirmed"})
    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": "2026-10-09", "generation_id": "gen-1", "_asset_metadata": [{"content_id": "post-1"}]}
    ticket = ledger.begin_attempt(content, "instagram", "morning", 1)
    assert ticket["allowed"]
    record = ledger.finish_attempt(ticket, {"success": True, "media_id": "ig-123", "permalink": "https://instagram.com/p/123"})
    assert record["status"] == "VERIFIED_LIVE"
    assert record["remote_id"] == "ig-123"
    again = ledger.begin_attempt(content, "instagram", "morning", 1)
    assert again["allowed"] is False
    assert again["reason"] == "already_published"


def test_ambiguous_timeout_is_not_blindly_retried(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": "2026-10-09", "generation_id": "gen-2"}
    ticket = ledger.begin_attempt(content, "facebook", "morning", 1)
    ledger.finish_attempt(ticket, {"success": False, "error": "Read timed out"})
    again = ledger.begin_attempt(content, "facebook", "morning", 1)
    assert again["allowed"] is False
    assert again["reason"] == "readback_unavailable_no_duplicate"


def test_transient_failure_has_backoff(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": "2026-10-09", "generation_id": "gen-3"}
    ticket = ledger.begin_attempt(content, "linkedin", "generate", 1)
    record = ledger.finish_attempt(ticket, {"success": False, "error": "HTTP 429 rate limit"})
    assert record["status"] == "FAILED"
    assert record["next_retry_at"]
    assert ledger.begin_attempt(content, "linkedin", "generate", 1)["reason"] == "retry_backoff"


def test_ledger_file_is_valid_json(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    path = tmp_path / "ledger.json"
    monkeypatch.setattr(ledger, "_PATH", path)
    content = {"date": "2026-10-09", "generation_id": "gen-4"}
    ticket = ledger.begin_attempt(content, "youtube", "generate", 1)
    ledger.finish_attempt(ticket, {"success": True, "video_id": "yt-123", "url": "https://youtube.com/shorts/yt-123"})
    assert json.loads(path.read_text())["version"] == 1
