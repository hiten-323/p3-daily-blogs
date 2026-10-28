"""Self-resuming retry. Each reel, the carousel, and the YouTube Short are separate targets.

A legacy ledger row with no asset still clears single-platform targets and reel_1.
It does not clear carousel, reel_2, or growth_reel. Reels regenerate from 10:00 IST
and each one publishes once the evening slot time has passed. The 8.0 gates stay.
Blog stays off unless BLOG_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import re

log = logging.getLogger(__name__)

# target -> (slot, ledger platforms, labels, earliest IST hour)
_EVENING_PLATFORMS = ("instagram_reel", "instagram_video", "instagram")
TARGETS = {
    "ig_feed":     ("morning", ("instagram",), ("instagram_post",), 10),
    "carousel":    ("morning", ("instagram",), ("carousel",), 10),
    "ig_story":    ("morning", ("instagram_story",), ("carousel", "instagram_post"), 10),
    "facebook":    ("morning", ("facebook",), ("facebook_post",), 10),
    "reel_1":      ("evening", _EVENING_PLATFORMS, ("reel_1",), 10),
    "reel_2":      ("evening", _EVENING_PLATFORMS, ("reel_2",), 10),
    "growth_reel": ("evening", _EVENING_PLATFORMS, ("growth_reel",), 10),
    "linkedin":    ("generate", ("linkedin",), ("linkedin_post",), 6),
    "youtube":     ("generate", ("youtube",), ("yt_short",), 6),
    "threads":     ("generate", ("threads",), ("threads_post",), 6),
    "blog":        ("generate", ("blog",), ("blog_post",), 6),
}
PIECE_ASSET = {"carousel": "carousel", "reel_1": "reel_1", "reel_2": "reel_2", "growth_reel": "growth_reel"}
LEGACY_BARE_ASSET = frozenset({"reel_1"})
REEL_TARGETS = ("reel_1", "reel_2", "growth_reel")
INSTAGRAM_TARGETS = frozenset({"ig_feed", "carousel", "ig_story", "reel_1", "reel_2", "growth_reel"})
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
    from content_generator.core.instagram_pause import instagram_paused
    targets = dict(TARGETS) if blog_enabled() else {k: v for k, v in TARGETS.items() if k != "blog"}
    if instagram_paused():
        # Owner kill switch: Instagram pieces are not due, not retried, and do
        # not keep the self-resume chain alive. Facebook/LinkedIn/YouTube/Threads stay.
        targets = {k: v for k, v in targets.items() if k not in INSTAGRAM_TARGETS}
    return targets


def records_for_date(date: str) -> list[dict]:
    from content_generator.publisher import publishing_ledger as pl
    with pl._LOCK:
        data = pl._load()
    return [dict(r, ledger_key=k) for k, r in data["records"].items()
            if str(r.get("content_date", "")).startswith(date)]


def evening_backstop_wait(now_ist: dt.datetime) -> bool:
    """True before 22:15 IST, the old window when the cron alone owned every reel.

    Kept so callers can still name that window. publish_plan does not use it:
    the cron publishes one reel, and deleting reel_1, reel_2, and growth_reel
    from the retry left them unattempted when that cron did not run.
    """
    return now_ist.hour == 22 and now_ist.minute < 15


def _evening_clock() -> tuple[int, int]:
    from content_generator.core.slot_registry import SLOTS_BY_ID
    hour, minute = (int(part) for part in SLOTS_BY_ID["evening"]["ist"].split(":"))
    return hour, minute


def prewarm_targets(missing: list[str], ist_hour: int, ist_minute: int, *,
                    override: bool = False, only: set | None = None) -> set[str]:
    """Reels regenerate before the evening slot. They publish once that slot is due."""
    if override or only is not None:
        return set()
    hour, minute = _evening_clock()
    if (ist_hour, ist_minute) >= (hour, minute):
        return set()
    return {t for t in missing if t in REEL_TARGETS}


def slots_for_targets(todo: list[str], prewarm: set[str], approved: dict) -> set[str]:
    approved = approved or {}
    return {
        TARGETS[t][0] for t in todo
        if t not in prewarm and any(label in approved for label in TARGETS[t][2])
    }


def evening_assets_due(todo: list[str], prewarm: set[str]) -> list[str]:
    """Same preference as the evening slot, one entry per unposted reel."""
    return [name for name in ("growth_reel", "reel_1", "reel_2") if name in todo and name not in prewarm]


def publish_plan(todo: list[str], approved: dict, ist_hour: int, ist_minute: int, *,
                 override: bool = False, only: set | None = None,
                 missing: list[str] | None = None) -> dict:
    """Slots to run, reels to publish one by one, and targets that are regen-only."""
    prewarm = prewarm_targets(
        list(missing if missing is not None else todo), ist_hour, ist_minute,
        override=override, only=only)
    return {
        "prewarm": prewarm,
        "slots": slots_for_targets(todo, prewarm, approved),
        "reels": evening_assets_due(todo, prewarm),
    }


def _asset_matches(record: dict, target: str) -> bool:
    recorded = str(record.get("asset") or "").strip()
    if target == "ig_feed":
        # A carousel row is not the feed post. A bare legacy row is.
        return recorded in ("", "instagram_post")
    asset = PIECE_ASSET.get(target)
    if not asset:
        return True
    if recorded:
        return recorded == asset
    return target in LEGACY_BARE_ASSET


def _row_covers(record: dict, name: str, slot: str, platforms: tuple) -> bool:
    if record.get("slot") != slot:
        return False
    if str(record.get("platform") or "").lower() not in platforms:
        return False
    if record.get("status") not in _posted_states():
        return False
    return _asset_matches(record, name)


def _target_rows(records: list[dict], target: str) -> list[dict]:
    slot, platforms, _labels, _hour = TARGETS[target]
    return [r for r in records
            if r.get("slot") == slot and str(r.get("platform") or "").lower() in platforms
            and _asset_matches(r, target)]


def unposted_targets(records: list[dict], now_hour: int) -> list[str]:
    out = []
    for name, (slot, platforms, _labels, hour) in active_targets().items():
        if now_hour < hour:
            continue
        if not any(_row_covers(r, name, slot, platforms) for r in records):
            out.append(name)
    return out


NO_PACK = "no_pack"
CHAIN_FROM_HOUR = 7


def threads_only_auth_block(unresolved: list[str], records: list[dict]) -> bool:
    """True when the only thing still unposted is a Threads credential block.

    Other platforms already had their chance. The block stays in the ledger
    so the next retry tries Threads again, and this job does not go red.
    """
    if list(unresolved) != ["threads"]:
        return False
    from content_generator.publisher.publishing_ledger import threads_auth_block
    rows = _target_rows(records, "threads")
    return bool(rows) and all(threads_auth_block(row) for row in rows)


def target_refuses_retry(records: list[dict], target: str) -> bool:
    """True when every real attempt for this target is past the ledger retry cap.

    Pre-flight misses do not count, so the self-resume chain can drop this target.
    """
    from content_generator.publisher.publishing_ledger import attempt_budget_exhausted
    rows = _target_rows(records, target)
    if not rows:
        return False
    return all(attempt_budget_exhausted(r) for r in rows)


def pending_targets(now_ist: dt.datetime | None = None, records: list[dict] | None = None,
                    pack_exists: bool | None = None) -> list[str]:
    """Due targets plus a missing pack. A dropped cron writes no rows and must stay pending."""
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
    return [t for t in unposted_targets(records, now_ist.hour) if not target_refuses_retry(records, t)]


def is_mandatory(target: str) -> bool:
    return TARGETS[target][0] in MANDATORY_SLOTS


def labels_to_regen(todo: list[str], approved: dict | None, records: list[dict] | None) -> list[str]:
    """Mandatory unapproved labels, plus prepublish_gate SKIPPED or FAILED rows."""
    approved, queued = approved or {}, []
    for name, (slot, platforms, labs, _hour) in TARGETS.items():
        if name not in todo:
            continue
        labels = labs[:1]
        mandatory = is_mandatory(name) and not any(label in approved for label in labs)
        gate = any(
            r.get("slot") == slot and str(r.get("platform") or "").lower() in platforms
            and str(r.get("status") or "") in ("SKIPPED", "FAILED")
            and str(r.get("error") or "").startswith("prepublish_gate:")
            for r in records or [])
        if not mandatory and not gate:
            continue
        for label in labels:
            if label not in queued and (mandatory or label not in approved):
                queued.append(label)
    return queued


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
            from content_generator.core.publish_bar import clear_ladder_hold
            clear_ladder_hold(piece)
            piece["needs_regen"] = True
            piece["regen_round"] = rounds[label]
            piece.pop("editorial_review", None)
            piece.pop("editorial_score", None)
            piece.pop("viral_potential", None)
        marked.append(label)
    return marked


def backoff_ok(records: list[dict], target: str, now: dt.datetime) -> bool:
    """Exponential backoff on rate limits: 30, 60, 120, 240 min (capped)."""
    fails = [r for r in _target_rows(records, target) if r.get("status") == "FAILED"]
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


def _feed_content_for_discovery(content: dict) -> dict:
    """Approved feed copy only, so a rejected carousel is not treated as images on disk."""
    if not isinstance(content, dict) or not (content.get("carousel") or content.get("instagram_post")):
        return content if isinstance(content, dict) else {}
    try:
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content)
    except Exception as exc:
        log.warning("[retry] feed discovery kept the full pack (%s)", type(exc).__name__)
        return content
    if not isinstance(approved, dict) or not ("carousel" in approved or "instagram_post" in approved):
        return content
    scoped = dict(content)
    scoped["carousel"] = approved.get("carousel") or {}
    scoped["instagram_post"] = approved.get("instagram_post") or {}
    return scoped


def ensure_ig_images(content: dict) -> bool:
    """Render the day's carousel / feed images if none exist on disk, or if the
    ones on disk fail jar provenance.

    Oct 18: the provenance registry had been deleted, so day290's committed
    slides were ``unregistered_image`` and every retry held the morning slot
    forever — files existed, so nothing was ever re-rendered. Re-rendering goes
    through the real-jar compositor, which records fresh provenance; the
    publish-time verification itself is unchanged.
    """
    try:
        from content_generator.publisher.instagram import _find_carousel_images
        imgs = _find_carousel_images(_feed_content_for_discovery(content))
        if imgs:
            from content_generator.creative.jar_provenance import verify_creative_suite
            ok, issues = verify_creative_suite(imgs)
            if ok:
                return True
            log.warning("[retry] on-disk IG images fail provenance (%s) — re-rendering", "; ".join(issues)[:300])
    except Exception:
        pass
    try:
        from content_generator.scheduler.daily import _do_generate_images
        from content_generator.core.ist_dates import asset_date
        _prev = os.environ.get("CREATIVE_ASSET_DATE")
        os.environ["CREATIVE_ASSET_DATE"] = asset_date(content)
        try:
            res = _do_generate_images(content, int(content.get("day_number") or 0))
        finally:
            if _prev is None:
                os.environ.pop("CREATIVE_ASSET_DATE", None)
            else:
                os.environ["CREATIVE_ASSET_DATE"] = _prev
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
        due = [t for t in REEL_TARGETS if t in unposted_targets(records_for_date(y), 23)]
        if due:
            log.warning("Evening backstop: %s still missing %s; publishing them now.", y, due)
            date, ist_hour, only = y, 23, set(due)
    content, why = _load_content(date)
    if content is None:
        log.info("No pack for %s yet (%s); carry-over waits for today's generate.", date, why)
        return 0

    records = records_for_date(date)
    missing = unposted_targets(records, ist_hour)
    if only is not None:
        missing = [t for t in missing if t in only]
    # Reel targets stay in `missing` after the evening slot time, including
    # 22:00-22:15. The cron publishes one reel; the others are this retry's.
    minute = now_ist.minute if ist_hour == now_ist.hour else 0
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
            need.extend(labels[:1])
    from content_generator.scheduler.daily import _do_editorial
    from content_generator.pipeline.generator import save_content
    import time as _time
    regen_need = labels_to_regen(todo, approved, records)
    deadline = _time.monotonic() + MANDATORY_BUDGET_S
    while regen_need and _time.monotonic() < deadline:
        log.warning("Gate regen (from scratch, 8.0 unchanged): %s", regen_need)
        mark_fresh(content, regen_need)
        _do_editorial(content, only=set(regen_need))
        save_content(content)
        approved = _approved(content)
        regen_need = [l for l in regen_need if l not in approved]
    handled = set(labels_to_regen(todo, {}, records))
    need = [l for l in need if l not in approved and l not in handled]
    if need:
        _do_editorial(content, only=set(need))
        save_content(content)
        approved = _approved(content)

    # 2. Publish through the normal paths; the ledger dedupes by date+slot+platform+asset.
    failures = []
    plan = publish_plan(
        todo, approved, ist_hour, minute, override=bool(override), only=only, missing=missing)
    prewarm = plan["prewarm"]
    slots = plan["slots"]
    if ("ig_feed" in todo or "carousel" in todo) and "morning" in slots:
        ensure_ig_images(content)
    os.environ.setdefault("ENABLE_TIMED_SLOTS", "true")
    if "generate" in slots:
        os.environ["FORCE_SLOT"] = "generate"
        from content_generator.publisher.dispatcher import publish_all
        res = publish_all(content, day_number=int(content.get("day_number") or 0))
        log.info("generate-path result: %s", res.get("summary"))
    from content_generator.scheduler.slots import run_publish_slot
    on_date = dt.date.fromisoformat(date)
    for slot in ("morning", "evening"):
        if slot not in slots:
            continue
        os.environ["FORCE_SLOT"] = slot
        if slot == "evening":
            for asset in plan["reels"]:
                res = run_publish_slot(slot, force_retry=True, on_date=on_date, only_asset=asset)
                log.info("%s %s result: %s", slot, asset, res.get("status"))
            continue
        res = run_publish_slot(slot, force_retry=True, on_date=on_date)
        log.info("%s result: %s", slot, res.get("status"))
    blocked = [t for t in todo if not any(l in approved for l in TARGETS[t][2])]
    # Prewarming a reel before the evening slot is expected; every other target
    # selected for this run must now be present in the authoritative ledger.
    checked_todo = [t for t in todo if t not in prewarm]
    after_records = records_for_date(date)
    remaining = [t for t in checked_todo if t in unposted_targets(after_records, ist_hour)]
    unresolved = sorted(set(blocked + remaining))
    if unresolved:
        if threads_only_auth_block(unresolved, after_records):
            log.warning(
                "Threads credential block is retryable and does not fail this job: %s",
                unresolved,
            )
            return 0
        refused = [t for t in unresolved if target_refuses_retry(after_records, t)]
        retryable = [t for t in unresolved if t not in refused]
        if refused and not retryable:
            msg = (
                f"RETRY-UNPOSTED: {date} will not retry {refused} "
                f"(retry limit reached after a real publish attempt). "
                f"Recovery chain will not re-dispatch."
            )
        else:
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
