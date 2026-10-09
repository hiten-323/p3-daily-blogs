import datetime as dt
import json


def test_confirmed_missing_post_clears_old_identity_before_retry(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.publisher import platform_verification as verifier
    from content_generator.core.ist_dates import today_ist
    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(verifier, "verify_remote_post", lambda platform, record: {"state": "missing", "method": "test", "detail": "404"})
    content = {"date": today_ist().isoformat(), "generation_id": "retry-1"}
    key, identity = ledger._identity(content, "instagram", "morning", 1)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    data = {"version": 1, "records": {key: {**identity, "status": "FAILED", "attempt_count": 1, "next_retry_at": past, "remote_id": "old-id", "url": "https://example.com/old", "updated_at": past}}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")
    ticket = ledger.begin_attempt(content, "instagram", "morning", 1)
    assert ticket["allowed"] is True
    assert ticket["record"]["remote_id"] == ""
    assert ticket["record"]["url"] == ""
