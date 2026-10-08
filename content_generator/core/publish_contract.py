"""
The publish result contract — what a run must prove before it may report success.

WHY THIS EXISTS

The workflow's check was "did we publish to at least one platform", read from a
`published_platforms` list. Two things were wrong with it:

  1. run_publish_slot() never returned that key. It returns the publisher's own
     dict, so on the morning and evening slots — the runs that actually post to
     Instagram — the key was always absent and the check exited 0 with a
     warning. Those slots have never been verified.

  2. "Something published" is not the same as "what was supposed to publish did".
     Instagram is the publish slot's obligation. Facebook mirrors that post.
     An expired Facebook token is logged and reported, and it does not turn
     a successful Instagram publish into a failed run.

So a run now declares what it EXPECTED to publish and what actually happened,
per platform, and the workflow compares the two. A missing contract is a hard
failure: a run that cannot say what it did has not demonstrated that it did
anything.

DELIBERATELY DISTINCT STATES

    skipped   an explicit, allow-listed decision not to publish -> green
    held      unexpected hold (stale file, empty gate, ...)  -> RED
    published Instagram (and any other fatal platform) succeeded -> green
    partial   a fatal expected platform failed               -> RED
    missing   no contract at all                             -> RED

Facebook is a mirror. When Instagram published, a Facebook failure is a
warning on an otherwise green publish. When Instagram itself failed, the
run stays red.

A hold is green only for an explicit allow-list (already published today,
founder dry-run). Every other hold used to exit 0, so morning and evening
could publish nothing and still look successful.
"""
from __future__ import annotations
import datetime
import logging
import os

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1.0.0"

# What each slot is responsible for. Defined once in core/slot_registry, which
# is also where the schedule lives — a slot's time and its obligations are the
# same decision and drifted apart when they were stated separately.
from content_generator.core.slot_registry import (   # noqa: E402
    SLOTS_BY_ID, expected_platforms,
)

SLOT_EXPECTATIONS: dict[str, list[str]] = {
    sid: list(s.get("expects", [])) for sid, s in SLOTS_BY_ID.items()
}

# A slot may finish without posting and still be green only for these.
# Match is a case-insensitive substring of the contract reason.
LEGIT_HOLDS = (
    "already_ran",
    "already_published",
    "already published",
    "auto_publish_disabled",
    "auto_publish=false",
)


def hold_is_expected(reason: str) -> bool:
    """True when a hold/skip is an intentional non-publish, not a silent failure."""
    text = (reason or "").strip().lower()
    return any(token in text for token in LEGIT_HOLDS)


def build(slot: str, day: int, expected: dict, results: dict,
          generation_id: str = "", status: str = "", reason: str = "") -> dict:
    """
    Assemble the contract a run reports back.

    expected: {"instagram": ["carousel"], "facebook": ["carousel"]}
    results:  {"instagram": {"status": "published", "asset_id": ..., "remote_id": ...}}
    """
    contract = {
        "contract_version": CONTRACT_VERSION,
        "run_id":        os.getenv("GITHUB_RUN_ID", "") or datetime.datetime.now()
                         .strftime("local_%Y%m%d_%H%M%S"),
        "generation_id": generation_id,
        "slot":          slot,
        "day":           day,
        "expected":      expected or {},
        "results":       results or {},
        "reason":        reason,
    }
    contract["status"] = status or evaluate(contract)["status"]
    # Retained so older readers of the result keep working; the contract above
    # is what the workflow actually checks.
    contract["published_platforms"] = [
        p for p, r in (results or {}).items()
        if str((r or {}).get("status")) == "published"
    ]
    return contract


def evaluate(contract: dict) -> dict:
    """
    Compare expected against actual.
    Returns {"status": ..., "ok": bool, "missing": [...], "detail": str}
    """
    if not isinstance(contract, dict):
        return {"status": "missing", "ok": False, "missing": [],
                "detail": "no publish contract in the run result"}

    if contract.get("_skipped") or contract.get("skipped") or contract.get("status") in ("skipped", "held"):
        status = contract.get("status") if contract.get("status") in ("skipped", "held") else "skipped"
        reason = contract.get("reason") or status
        ok = hold_is_expected(reason)
        return {"status": status, "ok": ok, "missing": [], "detail": reason}

    if "expected" not in contract:
        return {"status": "missing", "ok": False, "missing": [],
                "detail": "no publish contract in the run result"}

    expected = contract.get("expected") or {}
    results  = contract.get("results") or {}
    missing  = []
    warnings = []
    instagram_ok = _instagram_published(expected, results)
    for platform in expected:
        r = results.get(platform) or {}
        if str(r.get("status")) == "published":
            continue
        line = _platform_line(platform, r)
        if platform == "facebook" and instagram_ok:
            warnings.append(line)
        else:
            missing.append(line)

    if not expected:
        return {"status": "nothing_expected", "ok": True, "missing": [],
                "warnings": [], "detail": "this slot publishes nothing"}
    if missing:
        return {"status": "partial", "ok": False, "missing": missing,
                "warnings": warnings,
                "detail": "expected but not published: " + "; ".join(missing)}
    if warnings:
        return {"status": "published", "ok": True, "missing": [],
                "warnings": warnings,
                "detail": "instagram published; facebook mirror warning: " + "; ".join(warnings)}
    return {"status": "published", "ok": True, "missing": [], "warnings": [],
            "detail": f"all {len(expected)} expected platform(s) published"}


def _instagram_published(expected: dict, results: dict) -> bool:
    if "instagram" not in (expected or {}):
        return False
    return str((results.get("instagram") or {}).get("status")) == "published"


def _platform_line(platform: str, result: dict) -> str:
    line = f"{platform} ({result.get('status') or 'no result'}"
    if result.get("error"):
        line += f": {result.get('error')}"
    return line + ")"


def format_report(contract: dict) -> str:
    """Human-readable per-platform outcome for the CI log."""
    ev = evaluate(contract)
    lines = [f"slot={contract.get('slot')} day={contract.get('day')} "
             f"run_id={contract.get('run_id')} -> {ev['status'].upper()}"]
    if ev["status"] in ("skipped", "held"):
        mark = "OK  " if ev["ok"] else "FAIL"
        lines.append(f"  {mark} REASON: {ev['detail']}")
        return "\n".join(lines)
    expected = contract.get("expected") or {}
    results  = contract.get("results") or {}
    instagram_ok = _instagram_published(expected, results)
    for platform in sorted(set(expected) | set(results)):
        if platform not in expected:
            lines.append(f"  {platform.upper():<10} — not expected this slot")
            continue
        r = results.get(platform) or {}
        published = str(r.get("status")) == "published"
        if published:
            mark = "OK  "
        elif platform == "facebook" and instagram_ok:
            mark = "WARN"
        else:
            mark = "FAIL"
        detail = r.get("remote_id") or r.get("error") or r.get("status") or "no result"
        lines.append(f"  {platform.upper():<10} {mark} {detail}")
    return "\n".join(lines)
