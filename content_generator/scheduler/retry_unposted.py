"""Self-resuming retry: regenerate and publish anything not yet posted today.

Runs every 30 minutes (.github/workflows/retry-unposted.yml). Each run:
  1. finds which platform/type has no live post today (ledger, deduped by
     date + slot + platform, any content_id),
  2. runs the fallback ladder (~8 attempts) on the blocked pieces, with the
     8.0 gate unchanged,
  3. publishes only what then passes, via the normal slot/dispatcher paths,
  4. backs off exponentially on rate limits / repeated failures.
There is no overall cap: it keeps going every 30 min until everything is
posted or the IST day ends. Tomorrow's pack then takes over (carry-over), and
the same loop covers it. Timed slots are respected: the morning targets wait
for 10:00 IST and the evening reel for 22:00 IST.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger(__name__)

# target -> (slot, ledger platforms that count as posted, labels that feed it, earliest IST hour)
TARGETS = {
    "ig_feed":   ("morning", ("instagram",), ("carousel", "instagram_post"), 10),
    "ig_story":  ("morning", ("instagram_story",), ("carousel", "instagram_post"), 10),
    "facebook":  ("morning", ("facebook",), ("facebook_post",), 10),
    "ig_reel":   ("evening", ("instagram_video", "instagram"), ("growth_reel", "reel_1", "reel_2"), 22),
    "linkedin":  ("generate", ("linkedin",), ("linkedin_post",), 6),
    "youtube":   ("generate", ("youtube",), ("yt_short",), 6),
    "threads":   ("generate", ("threads",), ("threads_post",), 6),
    "blog":      ("generate", ("blog",), ("blog_post",), 6),
}
# Morning and evening posts are MANDATORY every day: a missing one is always
# regenerated from scratch (fresh angle / template / provider), never left idle.
MANDATORY_SLOTS = ("morning", "evening")
MANDATORY_BUDGET_S = int(os.getenv("MANDATORY_REGEN_BUDGET_S", "2400"))
_RATE = re.compile(r"429|rate.?limit|too many|throttl|quota", re.I)
BASE_BACKOFF_MIN = 30
MAX_BACKOFF_MIN = 240


def _posted_states():
    from content_generator.publisher.publishing_ledger import POSTED_STATES
    return POSTED_STATES


def unposted_targets(records: list[dict], now_hour: int) -> list[str]:
    states = _posted_states()
    out = []
    for name, (slot, platforms, _labels, hour) in TARGETS.items():
        if now_hour < hour:
            continue
        done = any(r.get("slot") == slot and str(r.get("platform", "")).lower() in platforms
                   and r.get("status") in states for r in records)
        if not done:
            out.append(name)
    return out


def is_mandatory(target: str) -> bool:
    return TARGETS[target][0] in MANDATORY_SLOTS


def prioritise(todo: list[str]) -> list[str]:
    """Mandatory morning/evening targets first, in TARGETS order."""
    return [t for t in todo if is_mandatory(t)] + [t for t in todo if not is_mandatory(t)]


def mark_fresh(content: dict, labels) -> list[str]:
    """Flag saved drafts for from-scratch regeneration on a new angle.

    The ladder treats needs_regen as 'build a brand-new piece' (no copying the
    held draft). The round counter rotates angle/template/provider seeds.
    """
    marked = []
    rounds = content.setdefault("mandatory_regen_rounds", {})
    for label in labels:
        key, idx = ("reels", int(label.split("_")[1]) - 1) if re.fullmatch(r"reel_\d+", label) else (label, None)
        val = content.get(key)
        piece = val[idx] if isinstance(val, list) and idx is not None and idx < len(val) else (
            val if isinstance(val, dict) else None)
        rounds[label] = int(rounds.get(label) or 0) + 1
        if isinstance(piece, dict):
            piece["needs_regen"] = True
            piece["regen_round"] = rounds[label]
            piece.pop("editorial_review", None)
            marked.append(label)
    return marked


def backoff_ok(records: list[dict], target: str, now: dt.datetime) -> bool:
    """Exponential backoff on rate limits: 30, 60, 120, 240 min (capped)."""
    slot, platforms, _l, _h = TARGETS[target]
    fails = [r for r in records if r.get("slot") == slot and str(r.get("platform", "")).lower() in platforms
             and r.get("status") == "FAILED"]
    if not fails:
        return True
    last = max(fails, key=lambda r: str(r.get("updated_at") or ""))
    if not _RATE.search(str(last.get("error") or "")):
        return True
    n = sum(int(r.get("attempt_count") or 1) for r in fails)
    wait = min(MAX_BACKOFF_MIN, BASE_BACKOFF_MIN * (2 ** max(0, n - 1)))
    try:
        ts = dt.datetime.fromisoformat(str(last.get("updated_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return now >= ts + dt.timedelta(minutes=wait)


def _approved(content: dict) -> dict:
    from content_generator.core.editorial_engine import approved_assets
    return approved_assets(content)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from content_generator.core.ist_dates import today_ist
    from content_generator.publisher.publishing_ledger import records_for_today
    from content_generator.scheduler.publish_recovery import _load_content

    now = dt.datetime.now(dt.timezone.utc)
    ist_hour = (now + dt.timedelta(hours=5, minutes=30)).hour
    date = today_ist().isoformat()
    content, why = _load_content(date)
    if content is None:
        log.info("No pack for %s yet (%s); carry-over waits for today's generate.", date, why)
        return 0

    records = records_for_today()
    missing = unposted_targets(records, ist_hour)
    # A missing mandatory slot is never parked in backoff.
    todo = prioritise([t for t in missing if is_mandatory(t) or backoff_ok(records, t, now)])
    if not todo:
        log.info("Nothing unposted (or all in backoff) for %s.", date)
        return 0
    log.warning("Unposted today: %s", todo)

    # 1. Ladder-regenerate blocked pieces for those targets (gate unchanged).
    approved = _approved(content)
    need = []
    for t in todo:
        labels = TARGETS[t][2]
        if not any(l in approved for l in labels):
            need.extend(labels[:1] if t != "ig_reel" else labels[:2])
    from content_generator.scheduler.daily import _do_editorial
    from content_generator.pipeline.generator import save_content
    import time as _time
    mandatory_need = [l for t in todo if is_mandatory(t) and not any(x in approved for x in TARGETS[t][2])
                      for l in (TARGETS[t][2][:2] if t == "ig_reel" else TARGETS[t][2][:1])]
    deadline = _time.monotonic() + MANDATORY_BUDGET_S
    rounds = 0
    while mandatory_need and _time.monotonic() < deadline:
        rounds += 1
        log.warning("MANDATORY slot regen round %d (from scratch): %s", rounds, mandatory_need)
        mark_fresh(content, mandatory_need)
        _do_editorial(content, only=set(mandatory_need))
        save_content(content)
        approved = _approved(content)
        mandatory_need = [l for l in mandatory_need
                          if not any(x in approved for t in todo if l in TARGETS[t][2] for x in TARGETS[t][2])]
    need = [l for l in need if l not in approved and not any(
        l in TARGETS[t][2] and is_mandatory(t) for t in todo)]
    if need:
        _do_editorial(content, only=set(need))
        save_content(content)
        approved = _approved(content)

    # 2. Publish through the normal paths; the ledger dedupes by date+slot+platform.
    failures = []
    slots = {TARGETS[t][0] for t in todo if any(l in approved for l in TARGETS[t][2])}
    os.environ.setdefault("ENABLE_TIMED_SLOTS", "true")
    if "generate" in slots:
        os.environ["FORCE_SLOT"] = "generate"
        from content_generator.publisher.dispatcher import publish_all
        res = publish_all(content, day_number=int(content.get("day_number") or 0))
        log.info("generate-path result: %s", res.get("summary"))
    for slot in ("morning", "evening"):
        if slot in slots:
            os.environ["FORCE_SLOT"] = slot
            from content_generator.scheduler.slots import run_publish_slot
            res = run_publish_slot(slot, force_retry=True, on_date=dt.date.fromisoformat(date))
            log.info("%s result: %s", slot, res.get("status"))
    blocked = [t for t in todo if not any(l in approved for l in TARGETS[t][2])]
    if blocked:
        msg = f"RETRY-UNPOSTED: still blocked after ladder for {date}: {blocked}; next try in 30 min."
        log.error(msg)
        try:
            from content_generator.scheduler.watchdog import _alert
            _alert(msg)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
