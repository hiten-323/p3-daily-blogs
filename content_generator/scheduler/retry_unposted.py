"""Self-resuming retry: regenerate and publish anything not yet posted today.

Runs every 30 minutes (.github/workflows/retry-unposted.yml). Each run:
  1. finds which platform/type has no live post today (ledger, deduped by
     date + slot + platform, any content_id),
  2. runs the fallback ladder (~8 attempts) on the blocked pieces, with the
     8.0 gate unchanged,
  3. publishes only what then passes, via the normal slot/dispatcher paths,
  4. backs off exponentially on rate limits / repeated failures.
There is no overall cap: it keeps going every 30 min until everything is
posted or the IST day ends. The Shopify blog is excluded unless
BLOG_ENABLED=true (owned by the separate Blogs bot). Tomorrow's pack then takes over (carry-over), and
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
    "ig_reel":   ("evening", ("instagram_reel", "instagram_video", "instagram"), ("growth_reel", "reel_1", "reel_2"), 22),
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


def active_targets() -> dict:
    """TARGETS with blog removed when BLOG_ENABLED is off (Blogs bot owns it)."""
    from content_generator.core.blog_flags import blog_enabled
    if blog_enabled():
        return dict(TARGETS)
    return {k: v for k, v in TARGETS.items() if k != "blog"}


def records_for_date(date: str) -> list[dict]:
    from content_generator.publisher import publishing_ledger as pl
    with pl._LOCK:
        data = pl._load()
    return [dict(r, ledger_key=k) for k, r in data["records"].items()
            if str(r.get("content_date", "")).startswith(date)]


def evening_backstop_wait(now_ist: dt.datetime) -> bool:
    """True before 22:15 IST, while the scheduled evening slot should run."""
    return now_ist.hour == 22 and now_ist.minute < 15


def unposted_targets(records: list[dict], now_hour: int) -> list[str]:
    states = _posted_states()
    out = []
    for name, (slot, platforms, _labels, hour) in active_targets().items():
        if now_hour < hour:
            continue
        done = any(r.get("slot") == slot and str(r.get("platform", "")).lower() in platforms
                   and r.get("status") in states for r in records)
        if not done:
            out.append(name)
    return out


NO_PACK = "no_pack"
# Chain from 07:00 IST: the 06:13 generate cron is often dropped or hours late.
CHAIN_FROM_HOUR = 7


def pending_targets(now_ist: dt.datetime | None = None, records: list[dict] | None = None,
                    pack_exists: bool | None = None) -> list[str]:
    """What is still due today; drives the workflow's self-resume chain.

    The chain used to count only non-live ledger rows for today. A slot whose
    cron GitHub dropped writes NO rows (e.g. the 09:53 morning slot on Oct 17),
    and before generate there is no pack, so the count was 0 and the chain died
    with nothing posted. This counts targets that are due now and not posted,
    whether or not anything was ever attempted, plus a missing pack.
    """
    if now_ist is None:
        now_ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
    if now_ist.hour < CHAIN_FROM_HOUR:
        return []
    date = now_ist.date().isoformat()
    if pack_exists is None:
        from content_generator.scheduler.publish_recovery import _load_content
        pack_exists = _load_content(date)[0] is not None
    if not pack_exists:
        return [NO_PACK]
    if records is None:
        records = records_for_date(date)
    return unposted_targets(records, now_ist.hour)


def is_mandatory(target: str) -> bool:
    return TARGETS[target][0] in MANDATORY_SLOTS


def prioritise(todo: list[str]) -> list[str]:
    """Mandatory morning/evening targets first, in TARGETS order."""
    return [t for t in todo if is_mandatory(t)] + [t for t in todo if not is_mandatory(t)]


# Native assets the pre-publish gate requires. Emergency packs omit them;
# a stub is not publishable copy — retry fills it through the unchanged gates.
NATIVE_REGEN_LABELS = ("facebook_post", "threads_post", "yt_short")


def native_regen_stub(content: dict, label: str, regen_round: int | None = None) -> dict:
    stub = {
        "type": label,
        "needs_regen": True,
        "featured_product": content.get("featured_product"),
    }
    if regen_round is not None:
        stub["regen_round"] = regen_round
    return stub


def ensure_native_regen_stubs(content: dict) -> dict:
    """Ensure facebook_post, threads_post, and yt_short exist as regen stubs.

    Does not invent copy. An existing non-empty piece is left untouched.
    """
    if not isinstance(content, dict):
        return content
    for label in NATIVE_REGEN_LABELS:
        val = content.get(label)
        if isinstance(val, dict) and val:
            continue
        content[label] = native_regen_stub(content, label)
    return content


def _piece_slot(content: dict, label: str):
    """Return (key, index, piece). piece is None when the slot is missing or empty."""
    if re.fullmatch(r"reel_\d+", label):
        key, idx = "reels", int(label.split("_")[1]) - 1
        val = content.get(key)
        piece = val[idx] if isinstance(val, list) and 0 <= idx < len(val) and isinstance(val[idx], dict) else None
        return key, idx, piece if piece else None
    val = content.get(label)
    return label, None, val if isinstance(val, dict) and val else None


def _store_piece(content: dict, key: str, idx: int | None, piece: dict) -> None:
    if idx is None:
        content[key] = piece
        return
    reels = content.get(key)
    if not isinstance(reels, list):
        reels = []
        content[key] = reels
    while len(reels) <= idx:
        reels.append({})
    reels[idx] = piece


def mark_fresh(content: dict, labels) -> list[str]:
    """Flag saved drafts for from-scratch regeneration on a new angle.

    The ladder treats needs_regen as 'build a brand-new piece' (no copying the
    held draft). The round counter rotates angle/template/provider seeds.
    A missing slot is seeded with a stub so targeted regen can create it.
    """
    marked = []
    rounds = content.setdefault("mandatory_regen_rounds", {})
    for label in labels:
        key, idx, piece = _piece_slot(content, label)
        rounds[label] = int(rounds.get(label) or 0) + 1
        if not isinstance(piece, dict) or not piece:
            _store_piece(content, key, idx, native_regen_stub(content, label, rounds[label]))
        else:
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


TARGET_GATE_PLATFORM = {"ig_feed": "instagram", "facebook": "facebook", "linkedin": "linkedin",
                        "youtube": "youtube", "threads": "threads", "blog": "shopify"}


def _approved(content: dict) -> dict:
    """Editorial-approved assets that ALSO clear the pre-publish gate.

    An asset can be editorially approved and still be held at publish time
    (e.g. growth_engine_regenerate). Counting it as approved meant the ladder
    never regenerated it, so the hold was permanent.
    """
    from content_generator.core.editorial_engine import approved_assets
    approved = dict(approved_assets(content))
    try:
        from content_generator.publisher.prepublish_gate import _PLATFORM_KEYS, authorize_publish
        for platform in set(TARGET_GATE_PLATFORM.values()):
            keys = [k for k in _PLATFORM_KEYS.get(platform, ()) if k in approved]
            if not keys:
                continue
            res = authorize_publish(content, platform)
            if not res.get("allowed"):
                bad = res.get("asset_key") or keys[0]
                log.warning("[retry] %s approved but held by pre-publish gate (%s) — will regenerate",
                            bad, res.get("reason"))
                approved.pop(bad, None)
    except Exception as e:
        log.warning("[retry] pre-publish gate check failed (%s) — relying on editorial approval", e)
    return approved


def ensure_ig_images(content: dict) -> bool:
    """Render today's carousel / feed images (new templates) if none exist on disk."""
    try:
        from content_generator.publisher.instagram import _find_carousel_images
        if _find_carousel_images(content):
            return True
    except Exception:
        pass
    try:
        from content_generator.scheduler.daily import _do_generate_images
        res = _do_generate_images(content, int(content.get("day_number") or 0))
        log.info("[retry] rendered IG images: %s", {k: (len(v) if isinstance(v, list) else bool(v)) for k, v in (res or {}).items()})
        return bool((res or {}).get("carousel") or (res or {}).get("instagram_post"))
    except Exception as e:
        log.error("[retry] IG image render failed: %s", e)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from content_generator.core.ist_dates import today_ist
    from content_generator.publisher.publishing_ledger import records_for_today
    from content_generator.scheduler.publish_recovery import _load_content

    now = dt.datetime.now(dt.timezone.utc)
    now_ist = now + dt.timedelta(hours=5, minutes=30)
    ist_hour = now_ist.hour
    date = today_ist().isoformat()
    only = None
    override = os.getenv("RETRY_DATE", "").strip()
    if override:
        # Manual backfill of a past day: every slot of that day is due.
        date = dt.date.fromisoformat(override).isoformat()
        ist_hour = 23
    elif ist_hour < 6:
        # Evening backstop across midnight: a dropped 21:53 cron (or a crash)
        # must not lose yesterday's mandatory evening reel.
        y = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
        if "ig_reel" in unposted_targets(records_for_date(y), 23):
            log.warning("Evening backstop: %s has no evening post; publishing it now.", y)
            date, ist_hour, only = y, 23, {"ig_reel"}
    content, why = _load_content(date)
    if content is None:
        log.info("No pack for %s yet (%s); carry-over waits for today's generate.", date, why)
        return 0

    records = records_for_date(date)
    missing = unposted_targets(records, ist_hour)
    if only is not None:
        missing = [t for t in missing if t in only]
    if not override and only is None and evening_backstop_wait(now_ist):
        # The scheduled evening slot owns 21:53-22:15; backstop only after.
        missing = [t for t in missing if t != "ig_reel"]
    # Mandatory evening reel: regenerate from 10:00 IST so a passing reel is
    # ready at 22:00 (publishing still waits for the evening slot hour).
    if ist_hour >= 10 and "ig_reel" not in missing and unposted_targets(records, 23).count("ig_reel"):
        missing.append("ig_reel")
        prewarm_reel = True
    else:
        prewarm_reel = False
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
    slots = {TARGETS[t][0] for t in todo if any(l in approved for l in TARGETS[t][2])
             and not (t == "ig_reel" and prewarm_reel)}
    if "ig_feed" in todo and "morning" in slots:
        ensure_ig_images(content)
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
    # Prewarming the evening reel before 22:00 is expected; every other target
    # selected for this run must now be present in the authoritative ledger.
    checked_todo = [t for t in todo if not (t == "ig_reel" and prewarm_reel)]
    after_records = records_for_date(date)
    remaining = [t for t in checked_todo if t in unposted_targets(after_records, ist_hour)]
    unresolved = sorted(set(blocked + remaining))
    if unresolved:
        msg = (
            f"RETRY-UNPOSTED: {date} still has targets not published after recovery: "
            f"{unresolved}; next attempt is scheduled by the recovery chain."
        )
        log.error(msg)
        try:
            from content_generator.scheduler.watchdog import alert_failure
            alert_failure(msg)
        except Exception:
            log.exception("[retry] failure alert could not be delivered")
        return 1
    return 0


def _cli() -> int:
    import sys
    if "--pending" in sys.argv[1:]:
        logging.basicConfig(level=logging.ERROR)
        try:
            pending = pending_targets()
        except Exception as exc:
            logging.getLogger(__name__).error("pending probe failed: %s", exc)
            print("PENDING_ERROR:" + type(exc).__name__)
            return 1
        print("PENDING:" + ",".join(pending))
        return 0
    return main()


if __name__ == "__main__":
    raise SystemExit(_cli())
