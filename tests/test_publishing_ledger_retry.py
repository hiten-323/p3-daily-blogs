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


def test_threads_credential_block_stays_due_without_burning_the_retry_budget(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    row = ledger.record_credential_block("threads", "Threads token check (HTTP 401): checkpoint")
    assert row["status"] == "FAILED"
    assert row["platform"] == "threads"
    assert row["slot"] == "generate"
    assert row["attempt_count"] == 0
    assert row["credential_block"] is True
    assert "checkpoint" in row["error"]
    assert ledger.threads_auth_block(row) is True
    assert ledger.attempt_budget_exhausted({**row, "attempt_count": 9}) is False
    assert any(item["slot"] == "generate" for item in ledger.due_retry_groups())


def test_threads_publisher_401_does_not_exhaust_retry_budget(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(
        "content_generator.publisher.platform_verification.verify_remote_post",
        lambda platform, record: {"state": "missing", "method": "test", "detail": "404"},
    )
    content = {"date": today_ist().isoformat(), "generation_id": "threads-401"}
    key, identity = ledger._identity(content, "threads", "generate", 4)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    error = "HTTP 401: This Threads account needs to complete a checkpoint before it can access this app."
    data = {"version": 1, "records": {key: {
        **identity, "status": "FAILED", "attempt_count": 3,
        "next_retry_at": None, "remote_id": "", "url": "",
        "error": error, "updated_at": past,
    }}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")
    assert ledger.attempt_budget_exhausted(data["records"][key]) is False
    ticket = ledger.begin_attempt(content, "threads", "generate", 4)
    assert ticket["allowed"] is True


def test_instagram_http_401_still_exhausts_retry_budget(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": today_ist().isoformat(), "generation_id": "ig-401"}
    key, identity = ledger._identity(content, "instagram", "morning", 4)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).isoformat()
    data = {"version": 1, "records": {key: {
        **identity, "status": "FAILED", "attempt_count": 3,
        "next_retry_at": None, "remote_id": "", "url": "",
        "error": "HTTP 401: checkpoint", "updated_at": past,
    }}}
    ledger._PATH.write_text(json.dumps(data), encoding="utf-8")
    assert ledger.attempt_budget_exhausted(data["records"][key]) is True
    ticket = ledger.begin_attempt(content, "instagram", "morning", 4)
    assert ticket["allowed"] is False
    assert ticket["reason"] == "retry_limit_reached"


def test_threads_success_clears_credential_block(tmp_path, monkeypatch):
    from content_generator.publisher import publishing_ledger as ledger
    from content_generator.core.ist_dates import today_ist

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(
        "content_generator.publisher.platform_verification.verify_remote_post",
        lambda platform, record: {"state": "found", "method": "test", "detail": "ok"},
    )
    ledger.record_credential_block("threads", "HTTP 401 checkpoint")
    content = {"date": today_ist().isoformat(), "generation_id": "threads-live"}
    ticket = ledger.begin_attempt(content, "threads", "generate", 5)
    assert ticket["allowed"] is True
    saved = ledger.finish_attempt(ticket, {
        "success": True, "post_id": "th1", "url": "https://www.threads.net/t/abc",
        "verified_live": True,
    })
    assert saved["status"] == "VERIFIED_LIVE"
    left = ledger._load()["records"]
    assert any(row.get("status") == "VERIFIED_LIVE" for row in left.values())
    assert all(not row.get("credential_block") for row in left.values())
    assert ledger.record_credential_block("threads", "HTTP 401 checkpoint") == {}


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


def test_threads_auth_outcome_does_not_fail_recovery_job():
    from content_generator.scheduler.publish_recovery import outcome_fails_recovery

    checkpoint = {"success": False, "attempted": True, "error": "HTTP 401: checkpoint"}
    assert outcome_fails_recovery("threads", checkpoint) is False
    assert outcome_fails_recovery("instagram", checkpoint) is True
    assert outcome_fails_recovery("linkedin", {"success": True, "error": ""}) is False
    assert outcome_fails_recovery("facebook", {"success": False, "error": "caption rejected"}) is True


def test_threads_only_auth_block_does_not_fail_retry_job():
    from content_generator.scheduler.retry_unposted import threads_only_auth_block

    auth = {"platform": "threads", "slot": "generate", "status": "FAILED", "credential_block": True,
            "error": "credential_block: HTTP 401 checkpoint", "attempt_count": 0}
    content_fail = {"platform": "threads", "slot": "generate", "status": "FAILED",
                    "error": "prepublish_gate:growth", "attempt_count": 1}
    assert threads_only_auth_block(["threads"], [auth]) is True
    assert threads_only_auth_block(["threads", "linkedin"], [auth]) is False
    assert threads_only_auth_block(["threads"], [auth, content_fail]) is False
    assert threads_only_auth_block(["threads"], []) is False
