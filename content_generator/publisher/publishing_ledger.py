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
        return False
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) <= now
    except (ValueError, TypeError):
        return False


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
            if attempts >= _MAX_ATTEMPTS:
                return {"allowed": False, "reason": "retry_limit_reached", "record": old, "key": key}
            if not _due(old, now):
                return {"allowed": False, "reason": "retry_backoff", "record": old, "key": key}
        record = {**identity, **old, **identity}
        record.update({
            "status": "PUBLISHING",
            "attempt_count": attempts + 1,
            "updated_at": _iso(now),
            "last_attempt_at": _iso(now),
            "next_retry_at": None,
            "error": "",
        })
        data["records"][key] = record
        _save(data)
        return {"allowed": True, "key": key, "record": record}


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
        if success:
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
        data["records"][key] = record
        _save(data)
        return record


def publish_with_ledger(platform: str, content: dict, slot: str, day_number: int, publish: Callable[[], dict]) -> dict:
    """Run one publisher with durable duplicate prevention and outcome recording."""
    ticket = begin_attempt(content, platform, slot, day_number)
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
    try:
        result = publish() or {"success": False, "error": "publisher_returned_no_result"}
    except Exception as exc:
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    saved = finish_attempt(ticket, result)
    result["ledger_status"] = saved.get("status", "")
    result["ledger_attempt_count"] = saved.get("attempt_count", 0)
    return result


def records_for_today() -> list[dict]:
    from content_generator.core.ist_dates import today_ist
    with _LOCK:
        data = _load()
        today = today_ist().isoformat()
        return [dict(r, ledger_key=k) for k, r in data["records"].items() if str(r.get("content_date", "")).startswith(today)]


def due_retry_slots() -> list[str]:
    """Slots with due, retryable failures; uncertain outcomes are deliberately excluded."""
    now = _now()
    due = []
    for record in records_for_today():
        if not record.get("slot"):
            continue
        if record.get("status") == "FAILED" and int(record.get("attempt_count", 0)) < _MAX_ATTEMPTS and _due(record, now):
            due.append(str(record["slot"]))
        elif record.get("status") == "PUBLISHED_UNVERIFIED" and _due(record, now):
            due.append(str(record["slot"]))
    return sorted(set(due))
