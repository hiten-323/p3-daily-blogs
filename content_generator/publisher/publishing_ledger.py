"""Durable per-platform publishing ledger and duplicate-safe retry wrapper.

A successful API response is recorded as PUBLISHED_UNVERIFIED unless the adapter
explicitly confirms read-back. Ambiguous timeouts are never blindly retried.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

_PATH = Path(os.getenv("PUBLISH_LEDGER_PATH", os.path.join(os.getenv("LEARNING_DIR", "output/learning"), "publishing_ledger.json")))
_LOCK = threading.RLock()
_MAX_ATTEMPTS = int(os.getenv("PUBLISH_MAX_ATTEMPTS", "3"))
_STALE_PUBLISHING_MINUTES = int(os.getenv("PUBLISH_STALE_MINUTES", "30"))


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _load() -> dict:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("records"), dict) else {"version": 1, "records": {}}
    except (OSError, ValueError, TypeError):
        return {"version": 1, "records": {}}


def _save(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=_PATH.name + ".", suffix=".tmp", dir=str(_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, _PATH)
    finally:
        try:
            if os.path.exists(temp):
                os.unlink(temp)
        except OSError:
            pass


def _identity(content: dict, platform: str, slot: str, day_number: int) -> tuple[str, dict]:
    from content_generator.core.ist_dates import today_ist
    meta = (content.get("_asset_metadata") or [{}])[0] if isinstance(content, dict) else {}
    content_id = str(meta.get("content_id") or content.get("generation_id") or f"day-{day_number}")
    raw_date = str(content.get("date") or today_ist().isoformat()) if isinstance(content, dict) else today_ist().isoformat()
    try:
        from content_generator.core.ist_dates import content_matches_today
        fresh, _ = content_matches_today(content)
        content_date = today_ist().isoformat() if fresh else raw_date
    except Exception:
        content_date = raw_date
    key = "|".join((content_date, slot, platform.lower(), content_id))
    return key, {"content_date": content_date, "content_id": content_id, "platform": platform.lower(), "slot": slot, "day_number": day_number}


def _due(record: dict, now: dt.datetime) -> bool:
    value = record.get("next_retry_at")
    if not value:
        # A FAILED record with no scheduled retry time (e.g. a pre-publish
        # gate hold) must stay retryable; otherwise it is stuck in
        # "retry_backoff" forever and the piece is never regenerated.
        return True
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) <= now
    except (ValueError, TypeError):
        return False


# Local misses: the platform API was never called, so they cannot duplicate a
# post and must not burn the publish-attempt budget. Counting them (Oct 20
# morning IG `no_images`) made retry-unposted refuse the only recovery path.
_PREFLIGHT_MISSES = ("no_images", "no_video", "no_content")


def _preflight_miss(record: dict) -> bool:
    err = str((record or {}).get("error") or "").strip().lower()
    if err.startswith("prepublish_gate:"):
        return True
    return err.split(":", 1)[0].strip() in _PREFLIGHT_MISSES


def attempt_budget_exhausted(record: dict) -> bool:
    """True when another automatic publish of this row would be a duplicate risk."""
    if str((record or {}).get("status") or "") != "FAILED":
        return False
    if _preflight_miss(record):
        return False
    try:
        attempts = int((record or {}).get("attempt_count") or 0)
    except (TypeError, ValueError):
        attempts = 0
    return attempts >= _MAX_ATTEMPTS


def _recoverable_instagram_account_mismatch(old: dict, platform: str) -> bool:
    """Allow one safe recovery after the configured IG ID was corrected.

    Older failed records may have exhausted their retry budget while the
    publisher was accidentally calling Meta with the Facebook Page ID. Only
    reopen that narrow case when the current job has a distinct Instagram
    professional-account ID, the previous error explicitly names the Page ID,
    and no remote post ID/URL exists (so there is no possible duplicate).
    """
    if str(platform or "").lower() not in ("instagram", "instagram_story"):
        return False
    page_id = str(os.getenv("FACEBOOK_PAGE_ID", "")).strip()
    ig_id = str(os.getenv("INSTAGRAM_ACCOUNT_ID", "")).strip()
    error = str(old.get("error") or "").lower()
    if not page_id or not ig_id or ig_id == page_id:
        return False
    if old.get("remote_id") or old.get("url"):
        return False
    return (
        "unsupported post request" in error
        and "object with id" in error
        and page_id.lower() in error
    )


def begin_attempt(content: dict, platform: str, slot: str, day_number: int) -> dict:
    """Return an attempt ticket, or a skip decision that prevents duplicate posts."""
    with _LOCK:
        data = _load()
        key, identity = _identity(content, platform, slot, day_number)
        old = data["records"].get(key, {})
        status = old.get("status")
        now = _now()
        if status in ("PUBLISHED_UNVERIFIED", "UNCERTAIN") or (status == "FAILED" and (old.get("remote_id") or old.get("url"))):
            from content_generator.publisher.platform_verification import verify_remote_post
            verification = verify_remote_post(platform, old)
            old["verification_method"] = verification.get("method", "")
            old["verification_detail"] = verification.get("detail", "")
            old["last_verification_at"] = _iso(now)
            if verification.get("state") == "found":
                old.update({"status": "VERIFIED_LIVE", "verified_at": _iso(now), "error": "", "next_retry_at": None, "updated_at": _iso(now)})
                data["records"][key] = old
                _save(data)
                return {"allowed": False, "reason": "already_published", "record": old, "key": key}
            if verification.get("state") == "exists_not_public":
                old.update({"status": "PUBLISHED_UNVERIFIED", "error": verification.get("detail", "remote object exists but is not public"), "next_retry_at": None, "updated_at": _iso(now)})
                data["records"][key] = old
                _save(data)
                return {"allowed": False, "reason": "remote_object_exists_not_public", "record": old, "key": key}
            if verification.get("state") == "unknown":
                old.update({"status": "PUBLISHED_UNVERIFIED" if status == "PUBLISHED_UNVERIFIED" else "UNCERTAIN", "error": verification.get("detail", "read-back verification unavailable"), "next_retry_at": _iso(now + dt.timedelta(hours=1)) if status == "PUBLISHED_UNVERIFIED" else None, "updated_at": _iso(now)})
                data["records"][key] = old
                _save(data)
                return {"allowed": False, "reason": "readback_unavailable_no_duplicate", "record": old, "key": key}
            if status in ("PUBLISHED_UNVERIFIED", "UNCERTAIN"):
                old.update({"status": "FAILED", "error": verification.get("detail", "remote object not found on read-back"), "next_retry_at": _iso(now + dt.timedelta(minutes=5)), "updated_at": _iso(now)})
                data["records"][key] = old
                _save(data)
                return {"allowed": False, "reason": "remote_confirmed_missing_wait_for_retry", "record": old, "key": key}
        if status == "FAILED" and (old.get("remote_id") or old.get("url")) and verification.get("state") == "missing":
            # The prior remote ID is confirmed absent. Preserve it in history,
            # but clear it before retry so a new response without an ID cannot
            # accidentally verify against the old, missing object.
            old["remote_id"] = ""
            old["url"] = ""
            old["verification_detail"] = "prior remote object confirmed missing; retry uses a fresh remote identity"
            old["updated_at"] = _iso(now)
            data["records"][key] = old
            _save(data)
        if status == "VERIFIED_LIVE":
            return {"allowed": False, "reason": "already_published", "record": old, "key": key}
        if status == "UNCERTAIN":
            return {"allowed": False, "reason": "ambiguous_result_requires_reconciliation", "record": old, "key": key}
        if status == "PUBLISHING":
            try:
                started = dt.datetime.fromisoformat(str(old.get("updated_at", "")).replace("Z", "+00:00"))
                if now - started < dt.timedelta(minutes=_STALE_PUBLISHING_MINUTES):
                    return {"allowed": False, "reason": "attempt_in_progress", "record": old, "key": key}
            except (ValueError, TypeError):
                return {"allowed": False, "reason": "stale_attempt_requires_reconciliation", "record": old, "key": key}
            # A stale in-flight attempt is ambiguous. Do not send it again blindly.
            old["status"] = "UNCERTAIN"
            old["error"] = "stale PUBLISHING record; remote result must be reconciled before retry"
            old["updated_at"] = _iso(now)
            data["records"][key] = old
            _save(data)
            return {"allowed": False, "reason": "stale_attempt_requires_reconciliation", "record": old, "key": key}
        attempts = int(old.get("attempt_count", 0))
        if status == "FAILED":
            account_id_recovery = _recoverable_instagram_account_mismatch(old, platform)
            if attempt_budget_exhausted(old) and not account_id_recovery:
                return {"allowed": False, "reason": "retry_limit_reached", "record": old, "key": key}
            if not _due(old, now):
                return {"allowed": False, "reason": "retry_backoff", "record": old, "key": key}
        prior_snapshot = json.loads(json.dumps(old)) if old else None
        record = {**identity, **old, **identity}
        record.update({
            "status": "PUBLISHING",
            "attempt_count": attempts + 1,
            "updated_at": _iso(now),
            "last_attempt_at": _iso(now),
            "next_retry_at": None,
            "error": "",
        })
        history = list(record.get("history") or [])
        history.append({"event": "attempt_started", "attempt": attempts + 1, "at": _iso(now)})
        record["history"] = history[-100:]
        data["records"][key] = record
        _save(data)
        return {"allowed": True, "key": key, "record": record, "prior": prior_snapshot}


def abandon_attempt(ticket: dict) -> None:
    """Undo begin_attempt when the publisher is deliberately NOT called.

    The dedupe branch of publish_with_ledger used to leave the row in
    PUBLISHING; 30 minutes later it became UNCERTAIN ("stale attempt") and,
    since an UNCERTAIN row with no remote id can never be read back, the
    target was blocked forever even though no platform call was ever made
    (Oct 18 morning backfill, run 39228725174).
    """
    if not ticket or not ticket.get("allowed") or not ticket.get("key"):
        return
    with _LOCK:
        data = _load()
        key = ticket["key"]
        current = data["records"].get(key) or {}
        if current.get("status") != "PUBLISHING":
            return
        prior = ticket.get("prior")
        if prior:
            data["records"][key] = prior
        else:
            data["records"].pop(key, None)
        _save(data)


def finish_attempt(ticket: dict, result: dict) -> dict:
    """Persist a platform result; ambiguous network outcomes are never auto-resubmitted."""
    if not ticket or not ticket.get("allowed"):
        return {}
    with _LOCK:
        data = _load()
        key = ticket["key"]
        record = data["records"].get(key, ticket.get("record", {}))
        result = result if isinstance(result, dict) else {}
        error = str(result.get("error") or result.get("message") or "")
        success = bool(result.get("success"))
        not_attempted = bool(result.get("skipped") or result.get("held") or result.get("attempted") is False)
        if not_attempted and not success:
            # A deliberate hold/skip (e.g. no native Threads copy or no native video)
            # is not a failed delivery and must not enter the automatic retry queue.
            status, next_retry = "SKIPPED", None
        elif success:
            status = "VERIFIED_LIVE" if result.get("verified_live") is True else "PUBLISHED_UNVERIFIED"
            next_retry = None
        else:
            text = error.lower()
            ambiguous = any(token in text for token in ("timeout", "timed out", "connection reset", "connection aborted", "remote end closed", "read error")) or any(f"http {code}" in text for code in range(500, 600))
            permanent = any(token in text for token in ("not_configured", "unauthorized", "expired_access_token", "permission", "prepublish_gate", "no_content", "no_images", "no_video"))
            if ambiguous:
                status, next_retry = "UNCERTAIN", None
            elif permanent or int(record.get("attempt_count", 1)) >= _MAX_ATTEMPTS:
                status, next_retry = "FAILED", None
            else:
                status = "FAILED"
                delay = min(60, 5 * (2 ** (int(record.get("attempt_count", 1)) - 1)))
                next_retry = _iso(_now() + dt.timedelta(minutes=delay))
        record.update({
            "status": status,
            "updated_at": _iso(),
            "error": error[:1000],
            "remote_id": str(result.get("media_id") or result.get("post_id") or result.get("video_id") or result.get("id") or ""),
            "url": str(result.get("permalink") or result.get("url") or ""),
            "verification_method": str(result.get("verification_method") or ("adapter_readback" if status == "VERIFIED_LIVE" else "publish_response" if success else "")),
            "verified_at": _iso() if status == "VERIFIED_LIVE" else None,
            "next_retry_at": next_retry,
            "last_result": {"success": success, "error": error[:1000]},
        })
        if success:
            from content_generator.publisher.platform_verification import verify_remote_post
            verification = verify_remote_post(record.get("platform", ""), record)
            record["verification_method"] = verification.get("method", "")
            record["verification_detail"] = verification.get("detail", "")
            record["last_verification_at"] = _iso()
            if verification.get("state") == "found":
                record.update({"status": "VERIFIED_LIVE", "verified_at": _iso(), "next_retry_at": None, "error": ""})
            elif verification.get("state") == "missing":
                record.update({"status": "PUBLISHED_UNVERIFIED", "next_retry_at": _iso(_now() + dt.timedelta(minutes=5)), "error": "POST accepted but read-back did not find it yet; recheck before any retry"})
            elif verification.get("state") == "exists_not_public":
                record.update({"status": "PUBLISHED_UNVERIFIED", "next_retry_at": None, "error": verification.get("detail", "remote object exists but is not public")})
            else:
                record.update({"status": "PUBLISHED_UNVERIFIED", "next_retry_at": _iso(_now() + dt.timedelta(hours=1)), "error": verification.get("detail", "read-back verification unavailable")})
        record["published"] = record.get("status") == "VERIFIED_LIVE"
        history = list(record.get("history") or [])
        history.append({
            "event": "attempt_finished",
            "attempt": int(record.get("attempt_count", 0)),
            "at": _iso(),
            "status": record.get("status", ""),
            "error": str(record.get("error") or "")[:1000],
            "remote_id": str(record.get("remote_id") or ""),
            "url": str(record.get("url") or ""),
            "verification_method": str(record.get("verification_method") or ""),
        })
        record["history"] = history[-100:]
        data["records"][key] = record
        _save(data)
        return record


def publish_with_ledger(platform: str, content: dict, slot: str, day_number: int, publish: Callable[[], dict]) -> dict:
    """Run one publisher with durable duplicate prevention and outcome recording."""
    ticket = begin_attempt(content, platform, slot, day_number)
    if ticket.get("allowed"):
        _kdate = str(ticket.get("key", "")).split("|")[0]
        prior = already_posted_today(platform, slot, ticket.get("key", ""), on_date=_kdate or None)
        if prior:
            abandon_attempt(ticket)
            ticket = {"allowed": False, "reason": "already_published", "record": prior, "key": ticket.get("key")}
    if not ticket.get("allowed"):
        logger_message = f"[publish-ledger] {platform} not retried: {ticket.get('reason')}"
        import logging
        logging.getLogger(__name__).warning(logger_message)
        return {
            "success": ticket.get("reason") == "already_published", "attempted": False, "skipped": True,
            "error": "" if ticket.get("reason") == "already_published" else ticket.get("reason", "ledger_skip"),
            "ledger_status": (ticket.get("record") or {}).get("status", ""),
            "post_id": (ticket.get("record") or {}).get("remote_id", ""),
            "media_id": (ticket.get("record") or {}).get("remote_id", ""),
            "video_id": (ticket.get("record") or {}).get("remote_id", ""),
            "permalink": (ticket.get("record") or {}).get("url", ""),
            "url": (ticket.get("record") or {}).get("url", ""),
        }
    from content_generator.publisher import publish_claim
    key_parts = str(ticket.get("key", "")).split("|")
    claim_date = key_parts[0] if key_parts and key_parts[0] else str(content.get("date", ""))[:10]
    ok, claim_ref = publish_claim.acquire(claim_date, slot, platform)
    if not ok:
        import logging
        logging.getLogger(__name__).warning("[publish-ledger] %s %s not published: %s", platform, slot, claim_ref)
        released = {"success": claim_ref == "already_published_remote", "attempted": False, "skipped": True,
                    "error": "" if claim_ref == "already_published_remote" else claim_ref}
        finish_attempt(ticket, dict(released, success=False))
        return released
    try:
        result = publish() or {"success": False, "error": "publisher_returned_no_result"}
    except Exception as exc:
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    if not result.get("success") and not result.get("uncertain"):
        publish_claim.release(claim_ref)
    saved = finish_attempt(ticket, result)
    result["ledger_status"] = saved.get("status", "")
    result["ledger_attempt_count"] = saved.get("attempt_count", 0)
    return result


POSTED_STATES = ("VERIFIED_LIVE", "PUBLISHED_UNVERIFIED", "UNCERTAIN")


def already_posted_today(platform: str, slot: str, exclude_key: str = "", on_date: str | None = None) -> dict | None:
    """A post for this (date, slot, platform) under ANY content_id blocks a second one.

    The ledger key includes content_id, so a regenerated pack used to look like
    new work. Dedupe here is by date + slot + platform. UNCERTAIN counts as
    posted: a possible duplicate is worse than a late retry.
    """
    # Dedupe against the CONTENT date being published, not the wall-clock
    # day: a backfill of 2026-10-18 was matched against 2026-10-19's live
    # morning posts and silently "skipped as already published".
    try:
        records = records_for_today() if not on_date or on_date == _today_iso() else records_for_content_date(on_date)
        for record in records:
            if record.get("ledger_key") == exclude_key:
                continue
            if (str(record.get("platform", "")).lower() == platform.lower()
                    and record.get("slot") == slot
                    and record.get("status") in POSTED_STATES):
                return record
    except Exception:
        return None
    return None


def records_for_content_date(date_iso: str) -> list[dict]:
    with _LOCK:
        data = _load()
        return [dict(r, ledger_key=k) for k, r in data["records"].items() if str(r.get("content_date", "")).startswith(str(date_iso)[:10])]


def records_for_today() -> list[dict]:
    from content_generator.core.ist_dates import today_ist
    with _LOCK:
        data = _load()
        today = today_ist().isoformat()
        return [dict(r, ledger_key=k) for k, r in data["records"].items() if str(r.get("content_date", "")).startswith(today)]


def due_retry_slots() -> list[str]:
    """Slots with due, retryable failures; uncertain outcomes are deliberately excluded."""
    return sorted({item["slot"] for item in due_retry_groups() if item["content_date"] == _today_iso()})


def _today_iso() -> str:
    from content_generator.core.ist_dates import today_ist
    return today_ist().isoformat()


def _retry_window_dates() -> set[str]:
    """Today and yesterday only. Older failures are not retried automatically."""
    from content_generator.core.ist_dates import today_ist
    today = today_ist()
    return {today.isoformat(), (today - dt.timedelta(days=1)).isoformat()}


def due_retry_groups() -> list[dict]:
    """Due retries for today and yesterday, keyed by content day and slot.

    A 22:00 IST evening that starts after midnight records yesterday's content
    date. Limiting recovery to today made that failure invisible.
    """
    now = _now()
    window = _retry_window_dates()
    due = []
    seen = set()
    with _LOCK:
        data = _load()
        records = [
            dict(record, ledger_key=key)
            for key, record in data["records"].items()
            if str(record.get("content_date", ""))[:10] in window
        ]
    for record in records:
        slot = str(record.get("slot") or "")
        content_date = str(record.get("content_date") or "")[:10]
        if not slot or not content_date:
            continue
        failed = (
            record.get("status") == "FAILED"
            and not attempt_budget_exhausted(record)
            and _due(record, now)
        )
        unverified = record.get("status") == "PUBLISHED_UNVERIFIED" and _due(record, now)
        if not (failed or unverified):
            continue
        key = (content_date, slot)
        if key in seen:
            continue
        seen.add(key)
        due.append({"content_date": content_date, "slot": slot})
    return sorted(due, key=lambda item: (item["content_date"], item["slot"]))
