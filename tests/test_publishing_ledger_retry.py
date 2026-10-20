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


def test_corrected_instagram_account_id_reopens_only_stale_page_id_failures(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "494003270464484")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "17841468220846030")
    content = {"date": today_ist().isoformat(), "generation_id": "ig-account-recovery"}
    key, identity = ledger._identity(content, "instagram", "morning", 289)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    old_error = (
        "Unsupported post request. Object with ID '494003270464484' does not exist, "
        "cannot be loaded due to missing permissions, or does not support this operation."
    )
    data = {"version": 1, "records": {key: {
        **identity, "status": "FAILED", "attempt_count": 3,
        "next_retry_at": None, "remote_id": "", "url": "",
        "error": old_error, "updated_at": past,
    }}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")

    ticket = ledger.begin_attempt(content, "instagram", "morning", 289)
    assert ticket["allowed"] is True
    assert ticket["record"]["attempt_count"] == 4


def test_preflight_no_images_does_not_exhaust_retry_cap(tmp_path, monkeypatch):
    """A no_images miss never reached Instagram, so it must stay retryable."""
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": today_ist().isoformat(), "generation_id": "ig-no-images"}
    key, identity = ledger._identity(content, "instagram", "morning", 292)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    data = {"version": 1, "records": {key: {
        **identity, "status": "FAILED", "attempt_count": 3,
        "next_retry_at": None, "remote_id": "", "url": "",
        "error": "no_images", "updated_at": past,
    }}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")

    ticket = ledger.begin_attempt(content, "instagram", "morning", 292)
    assert ticket["allowed"] is True
    assert ticket["record"]["attempt_count"] == 4
    assert ledger.attempt_budget_exhausted(data["records"][key]) is False


def test_corrected_instagram_account_id_does_not_reopen_unrelated_or_ambiguous_failures(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "494003270464484")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "17841468220846030")
    content = {"date": today_ist().isoformat(), "generation_id": "ig-account-no-reopen"}
    key, identity = ledger._identity(content, "instagram", "morning", 289)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    data = {"version": 1, "records": {key: {
        **identity, "status": "FAILED", "attempt_count": 3,
        "next_retry_at": None, "remote_id": "", "url": "",
        "error": "caption rejected", "updated_at": past,
    }}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")
    ticket = ledger.begin_attempt(content, "instagram", "morning", 289)
    assert ticket["allowed"] is False
    assert ticket["reason"] == "retry_limit_reached"
