"""
Time-slot publishing — different content at its algorithm-optimal time.

The engine's own platform knowledge says:
  - Feed posts / carousels: 7-9 AM IST (commute + morning coffee scroll)
  - Reels: 7-10 PM IST (evening leisure scroll = highest watch time)

So instead of publishing everything at 06:00 IST, the day is split:

  SLOT       UTC cron    IST     WHAT HAPPENS
  generate   43 0 * * *  06:13   Full pipeline: insights, revenue, generate,
                                 editorial, images, LinkedIn/YouTube (blog off by default).
                                 Instagram + Facebook HELD for their windows.
  morning    23 4 * * *  09:53   IG carousel + feed post + Story + growth_reel
                                 + FB mirror (owner-chosen time)
  evening    23 16 * * * 21:53   IG reel_1 + FB mirror (owner-chosen time)

Two reels a day, spread across the day (owner, 2 Nov 2026): growth_reel in
the morning, reel_1 in the evening, reel_2 never. See core/reel_schedule.

Content + images are committed to the repo by the generate run, so the
later stateless CI runs can load and publish them.

Controlled by ENABLE_TIMED_SLOTS=true (set in the workflow). When unset,
legacy behavior (publish everything at 06:00) is preserved.
"""
from __future__ import annotations
import datetime
import glob as _glob
import json
import logging
import os

logger = logging.getLogger(__name__)


def slots_enabled() -> bool:
    return os.getenv("ENABLE_TIMED_SLOTS", "false").lower() == "true"


def get_current_slot(now_utc: datetime.datetime = None) -> str:
    """
    Determine the slot from the current UTC hour.

    Boundaries are derived from core/slot_registry rather than hardcoded here.
    They were hardcoded, and after the crons moved to 04:30/16:30 UTC the old
    "< 2 / < 12 / else" thresholds no longer matched the schedule they were
    meant to describe — a manual dispatch could resolve to a different slot
    than the same time on a cron would.

    Only reached on manual dispatch; scheduled runs set FORCE_SLOT.
    """
    from content_generator.core.slot_registry import SLOTS_BY_ID, slot_from_utc_hour

    forced = os.getenv("FORCE_SLOT")
    if forced in SLOTS_BY_ID:
        logger.info("[slots] Current slot forced by FORCE_SLOT env: %s", forced)
        return forced

    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    slot = slot_from_utc_hour(now_utc.hour)
    logger.info("[slots] No FORCE_SLOT — derived %s from %02d:00 UTC",
                slot, now_utc.hour)
    return slot


def _load_slot_content(on_date: datetime.date) -> dict | None:
    """Load the content JSON for the IST day this slot is responsible for."""
    date_str = on_date.isoformat()
    path = os.path.join("output", f"content_{date_str}.json")
    if not os.path.exists(path):
        logger.error("[slots] No content file for %s — generate run missing?", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
        from content_generator.core.draft_purge import purge_banned_drafts
        purge_banned_drafts(content)
        from content_generator.scheduler.publish_recovery import normalize_handle
        normalize_handle(content)
        return content
    except Exception as e:
        logger.error("[slots] Could not read content file: %s", e)
        return None


def _load_todays_content() -> dict | None:
    """Load the content JSON saved by this morning's generate run."""
    from content_generator.core.ist_dates import today_ist
    return _load_slot_content(today_ist())


def _find_reel_thumbnail(date_str: str | None = None) -> str | None:
    """Find the reel thumbnail for the content day, not the wall-clock day."""
    from content_generator.core.ist_dates import today_ist
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    date_str = date_str or today_ist().isoformat()
    for pattern in (f"reel_1_thumb_*_{date_str}.jpg", f"reel_1*{date_str}.jpg",
                    f"reel_hook_*_{date_str}.jpg"):
        matches = sorted(_glob.glob(os.path.join(creative_dir, pattern)))
        if matches:
            return matches[0]
    return None


def _select_slot_reel(approved: dict, slot: str, skip: set | None = None,
                      only: str = "") -> tuple[str, dict] | None:
    """The one reel this slot owns (core/reel_schedule), if approved and not yet live.

    No substitution: the evening slot never publishes growth_reel or reel_2,
    and the morning slot never publishes reel_1. ``only`` must name the slot's
    own reel, otherwise nothing is selected.
    """
    from content_generator.core.reel_schedule import reel_for_slot
    name = reel_for_slot(slot)
    if not name or not isinstance(approved, dict):
        return None
    if only and only != name:
        return None
    if name in (skip or set()):
        return None
    piece = approved.get(name)
    if isinstance(piece, dict) and piece:
        return name, piece
    return None


def _select_evening_reel(approved: dict, skip: set | None = None, only: str = "") -> tuple[str, dict] | None:
    """Evening reel: reel_1 only. growth_reel moved to the morning; reel_2 is retired."""
    return _select_slot_reel(approved, "evening", skip, only)


def _reel_records(on_date) -> list[dict]:
    from content_generator.scheduler.retry_unposted import records_for_date
    return records_for_date(on_date.isoformat())


def _evening_assets_posted(on_date) -> set[str]:
    """Reels already live for this content day, in any slot. A legacy evening row with no asset is reel_1."""
    from content_generator.core.reel_schedule import posted_reels
    from content_generator.publisher.publishing_ledger import POSTED_STATES
    return set(posted_reels(_reel_records(on_date), POSTED_STATES))


def _feed_assets_to_publish(approved: dict, on_date) -> list[str]:
    """Carousel and the feed post are separate. A bare morning row is the feed post only."""
    from content_generator.publisher.publishing_ledger import POSTED_STATES
    from content_generator.scheduler.retry_unposted import records_for_date
    live = set()
    bare = False
    for record in records_for_date(on_date.isoformat()):
        if record.get("slot") != "morning" or str(record.get("platform") or "").lower() != "instagram":
            continue
        if record.get("status") not in POSTED_STATES:
            continue
        asset = str(record.get("asset") or "").strip()
        if asset:
            live.add(asset)
        else:
            bare = True
    queue = []
    if isinstance(approved.get("carousel"), dict) and approved.get("carousel") and "carousel" not in live:
        queue.append("carousel")
    post = approved.get("instagram_post")
    if isinstance(post, dict) and post and "instagram_post" not in live and not bare:
        queue.append("instagram_post")
    return queue


def _first(piece: dict, *keys: str) -> str:
    """First non-empty value among keys — schemas drift, field names move."""
    for k in keys:
        v = piece.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _track(result: dict, content: dict, slot: str, piece: dict) -> None:
    """Register the published media for tomorrow's insights fetch."""
    try:
        if result.get("success") and result.get("media_id"):
            from content_generator.analytics.insights_fetcher import track_published_post

            # The schema field is `hook`. This read `hook_text`/`title`, which
            # exist on neither carousels nor reels, so all 50 tracked posts
            # carried an empty hook and the learning engine had nothing to
            # attribute performance to. Cascade + warn, so a future rename
            # degrades loudly instead of silently emptying the learning log.
            hook = _first(piece, "hook", "hook_text", "headline", "title")
            topic = _first(piece, "objective", "angle", "save_mechanic",
                           "hook_archetype", "type")
            # `slot` is the time of day, not a format — it made every record say
            # "morning"/"evening" and made format-level learning impossible.
            fmt = _first(piece, "type") or slot

            if not hook:
                logger.warning(
                    "[slots] no hook found on %s piece (keys=%s) — this post "
                    "cannot be learned from", slot, sorted(piece.keys())[:12])

            # Log value-vs-product so the 80/20 cap measures what actually
            # published, not what was planned.
            try:
                from content_generator.core.content_balance import (
                    classify_asset, record as record_balance, current_share,
                )
                kind = classify_asset(piece)
                record_balance(f"instagram_{slot}_day{content.get('day_number', 0)}", kind)
                share = current_share()
                logger.info("[slots] published as %s — product share now %.0f%% of last %d",
                            kind, share["share"] * 100, share["n"])
            except Exception as e:
                logger.debug("[slots] content balance logging skipped: %s", e)

            # Classify the attention mechanism at publish time so the learning
            # record can later be grouped by it (ADR-002 Phase 1).
            dims = {}
            try:
                from content_generator.core.scroller_psychology import describe
                dims = describe(piece, content, platform='instagram', fmt=fmt)
            except Exception as e:
                logger.debug("[slots] scroller dimensions unavailable: %s", e)

            track_published_post(
                media_id    = result["media_id"],
                asset_id    = f"instagram_{slot}_day{content.get('day_number', 0)}",
                track       = piece.get("track", "brand"),
                hook        = hook[:120],
                topic       = topic[:120],
                format_used = fmt,
                hashtags    = str(result.get("hashtags_used") or ""),
                kpi_at_creation=piece.get("target_kpi_at_creation", ""),
                policy_version=piece.get("policy_version_at_creation", ""),
                attention_mechanism=dims.get("attention_mechanism") or "",
                scroller_state=dims.get("scroller_state") or "",
                psychology_frame=dims.get("psychology_frame") or "",
                hook_strategy=dims.get("hook_strategy") or "",
                payoff_type=dims.get("payoff_type") or "",
                decision_version=dims.get("decision_version") or "",
            )
    except Exception as e:
        logger.warning("[slots] tracking failed: %s", e)


def _held(slot: str, day: int, content: dict, reason: str) -> dict:
    """
    A deliberate decision NOT to publish, reported as such.

    "Held because nothing passed the gate" and "no contract at all" are
    different states, and the workflow must be able to tell them apart: the
    first is the safety system working, the second is a broken run. Returning a
    bare {"success": False} collapsed them.
    """
    from content_generator.core.publish_contract import build
    logger.warning("[slots] %s slot HELD — %s", slot, reason)
    return build(slot=slot, day=day, expected={}, results={},
                 generation_id=str((content or {}).get("generation_id") or ""),
                 status="held", reason=reason)


def _skipped(slot: str, day: int = 0, reason: str = "") -> dict:
    """
    A deliberate decision that a publish slot is skipped (e.g. dry-run mode or already ran).
    Emits a valid publish contract so CI workflow verification passes cleanly.
    """
    from content_generator.core.publish_contract import build
    logger.info("[slots] %s slot SKIPPED — %s", slot, reason)
    res = build(slot=slot, day=day, expected={}, results={},
                status="skipped", reason=reason)
    res["_skipped"] = True
    return res


def run_publish_slot(slot: str, force_retry: bool = False, on_date: datetime.date | None = None,
                     only_asset: str = "") -> dict:
    """
    Execute a publish-only slot (morning or evening).
    Loads the content day for this slot and posts the slot's asset.

    on_date overrides the clock. Recovery passes yesterday when a delayed
    evening cron crossed midnight.
    """
    from content_generator.core.ist_dates import content_date_for_slot
    from content_generator.scheduler.run_lock import RunLock

    slot_date = on_date or content_date_for_slot(slot)

    # Respect the founder policy dry-run switch here too — the publish slots
    # must honor auto_publish=false, not just the generate slot.
    try:
        from content_generator.core.founder_policy import policy
        if not policy().get("auto_publish", True):
            logger.warning("[slots] auto_publish=false — %s slot generates nothing "
                           "and posts nothing (dry run)", slot)
            return _skipped(slot, reason="auto_publish_disabled")
    except Exception as _e:
        logger.debug("[slots] optional step failed: %s", _e)

    lock = RunLock(lock_path=os.path.join("output", f".running_{slot}"), for_date=slot_date)
    lock.__enter__()
    retrying_completed_slot = bool(lock.already_ran and force_retry)
    if lock.already_ran and not force_retry:
        logger.info("[slots] %s slot already ran today — skipping", slot)
        return _skipped(slot, reason="already_ran")
    if retrying_completed_slot:
        logger.warning("[slots] %s slot retry requested; platform ledger will suppress prior successes", slot)

    # The lock is taken BEFORE the work and marked completed only after it.
    #
    # This used to call lock.__enter__() and never __exit__(), so RunLock's
    # crash-release path was dead code here: a slot that raised left a lock
    # behind that read as a completed run, and because the workflow reports a
    # skipped slot as green, every later slot that day skipped in silence. The
    # lock file is committed to the repo, so that state outlived the container.
    try:
        result = _execute_publish_slot(slot, on_date=slot_date, only_asset=only_asset)
    except Exception:
        lock.release()          # crashed — let the next slot attempt proceed
        raise
    # A HOLD is a legitimate completion: we looked and decided not to publish.
    # Only a crash leaves the lock unmarked.
    if not retrying_completed_slot:
        lock.mark_completed()
    return result


def _execute_publish_slot(slot: str, on_date: datetime.date | None = None, only_asset: str = "") -> dict:
    """The slot's actual work. The lock lifecycle belongs to run_publish_slot."""
    # MISSING CONTENT IS A HOLD, NEVER A GENERATION.
    #
    # This used to call run_full_pipeline() when today's file was absent, so a
    # publish slot could generate its own content and post it minutes later —
    # skipping the whole generate-slot pipeline (research, editorial review,
    # image composition) and, when the LLMs were down, publishing an emergency
    # fallback the founder never saw. It also broke correlation: the asset
    # published at 22:00 was not the asset the 06:00 run produced and recorded.
    #
    # A publish slot publishes what generation already produced and validated.
    # If that does not exist, the honest outcome is to publish nothing.
    from content_generator.core.ist_dates import content_date_for_slot, content_matches_today
    slot_date = on_date or content_date_for_slot(slot)
    content = _load_slot_content(slot_date)
    if not content:
        return _held(slot, 0, {}, "no_content_for_today — the generate slot "
                                  "produced nothing; publish slots never generate")

    # Correlation: the loaded file must be the content day this slot owns.
    # A delayed 22:00 IST evening cron often starts after midnight; that run
    # still belongs to yesterday's file, not a file generate has not written.
    fresh, why = content_matches_today(content, today=slot_date)
    if content.get("date") and not fresh:
        # stale_content: why names the file date and today's IST date.
        return _held(slot, content.get("day_number", 0), content, why)

    day = content.get("day_number", 0)

    if slot == "morning":
        # Carousel / feed post + Instagram Story — 10:00 IST (owner-chosen)
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content)

        def _hold_feed(reason: str) -> dict:
            # A held feed does not hold the morning reel, which has its own target.
            logger.info("[slots] morning growth_reel (feed held): %s",
                        _morning_reel(content, day, slot_date, only_asset))
            return _held(slot, day, content, reason)

        if "carousel" not in approved and "instagram_post" not in approved:
            return _hold_feed("canonical_validation_failed")

        feed_queue = _feed_assets_to_publish(approved, slot_date)
        from content_generator.core.instagram_pause import instagram_paused
        ig_paused = instagram_paused()
        if ig_paused:
            logger.warning("[slots] Instagram PAUSED (owner kill switch) — morning feed/carousel/story "
                           "not published; Facebook mirror still runs")
            feed_queue = []
        # Hand the publisher ONLY gate-approved objects. A rejected asset is
        # absent by construction, not by downstream cooperation.
        from content_generator.publisher.instagram import _find_carousel_images, post_content, post_story
        preview = content.copy()
        preview["carousel"] = approved.get("carousel", {})
        preview["instagram_post"] = approved.get("instagram_post", {})
        imgs = _find_carousel_images(preview)
        if imgs:
            from content_generator.creative.jar_provenance import verify_creative_suite
            ok, issues = verify_creative_suite(imgs)
            if not ok:
                return _hold_feed(f"real_jar_unverified — {'; '.join(issues)}")

        from content_generator.publisher.publishing_ledger import publish_with_ledger
        result = {"success": True, "skipped": True, "error": ""}
        piece = {}
        for asset_name in feed_queue:
            filtered_content = content.copy()
            filtered_content["carousel"] = approved.get("carousel", {}) if asset_name == "carousel" else {}
            filtered_content["instagram_post"] = approved.get("instagram_post", {}) if asset_name == "instagram_post" else {}
            result = publish_with_ledger(
                "instagram", filtered_content, slot, day,
                lambda c=filtered_content: post_content(c, day=day),
                asset=asset_name,
            )
            piece = approved.get(asset_name) or {}
            _track(result, content, slot, piece)
        if not feed_queue:
            piece = approved.get("carousel") or approved.get("instagram_post") or {}
        fb_result = _mirror_to_facebook(content, day, slot)
        # Instagram Story (image, 24h) — separate method, same slot
        try:
            if ig_paused:
                raise _InstagramPaused()
            from content_generator.publisher.publishing_ledger import publish_with_ledger
            story_res = publish_with_ledger("instagram_story", content, slot, day,
                                            lambda: post_story(content, day=day))
            logger.info("[slots] instagram story: %s", story_res.get("success"))
            result["story"] = story_res
        except _InstagramPaused:
            logger.warning("[slots] instagram story: PAUSED (owner kill switch)")
        except Exception as e:
            logger.warning("[slots] instagram story failed: %s", e)
        # growth_reel — the day's first reel (two reels a day, owner 2 Nov 2026).
        # Its own ledger row and retry target; it never holds the feed contract.
        result["growth_reel"] = _morning_reel(content, day, slot_date, only_asset)
        logger.info("[slots] morning growth_reel: %s", result["growth_reel"])
        logger.info("[slots] morning publish: %s", result.get("success"))
        try:
            from content_generator.campaigns.trial_diwali_push import publish_for_slot
            result["sales_push"] = publish_for_slot(content, slot, day)
        except Exception as e:
            logger.warning("[slots] sales push publish skipped: %s", e)
        asset = feed_queue[0] if feed_queue else ("carousel" if "carousel" in approved else "instagram_post")
        if ig_paused:
            return _contract(slot, day, content, {"facebook": fb_result}, {"facebook": [asset]})
        return _contract(slot, day, content, {"instagram": result, "facebook": fb_result},
                         {"instagram": [asset], "facebook": [asset]})

    if slot == "evening":
        # reel_1 only — 21:53 IST. growth_reel posts in the morning; reel_2 is retired.
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content)
        out = _publish_slot_reel(slot, day, content, approved, slot_date, only_asset)
        if out.get("contract"):
            return out["contract"]
        chosen, result, fb_result, ig_paused = out["chosen"], out["result"], out["fb_result"], out["ig_paused"]
        try:
            from content_generator.campaigns.trial_diwali_push import publish_for_slot
            result["sales_push"] = publish_for_slot(content, slot, day)
        except Exception as e:
            logger.warning("[slots] sales push publish skipped: %s", e)
        if ig_paused:
            return _contract(slot, day, content, {"facebook": fb_result}, {"facebook": [chosen]})
        return _contract(slot, day, content,
                         {"instagram": result, "facebook": fb_result},
                         {"instagram": [chosen], "facebook": [chosen]})

    return {"slot": slot, "success": False, "error": f"unknown_slot_{slot}"}


def _morning_reel(content: dict, day: int, slot_date, only_asset: str = "") -> dict:
    """growth_reel in the morning slot. Never holds or fails the feed contract.

    Video only: the image/Story fallbacks belong to the evening reel, and a
    morning Story row would read as the day's Instagram Story to the ledger.
    """
    from content_generator.core.reel_schedule import GROWTH_REEL_CUTOFF_IST, reel_for_slot
    name = reel_for_slot("morning")
    if not name or (only_asset and only_asset != name):
        return {"skipped": True, "reason": "not_this_reel"}
    from content_generator.core.instagram_pause import instagram_paused
    if instagram_paused():
        logger.warning("[slots] Instagram PAUSED (owner kill switch) — morning %s not published", name)
        return {"skipped": True, "reason": "instagram_paused"}
    from content_generator.core.ist_dates import today_ist
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    if slot_date != today_ist() or (now_ist.hour, now_ist.minute) >= GROWTH_REEL_CUTOFF_IST:
        logger.info("[slots] morning reel %s not posted: window closed for %s", name, slot_date)
        return {"skipped": True, "reason": "morning_reel_window_closed"}
    try:
        from content_generator.core.editorial_engine import approved_assets
        out = _publish_slot_reel("morning", day, content, approved_assets(content), slot_date,
                                 only_asset, allow_image_fallback=False, mirror_facebook=False)
    except Exception as e:
        logger.warning("[slots] morning reel failed: %s", e)
        return {"success": False, "error": str(e)[:200]}
    if out.get("contract"):
        c = out["contract"]
        return {"success": False, "held": True, "reason": c.get("reason") or c.get("status")}
    res = out["result"] or {}
    res["asset"] = out["chosen"]
    return res


def _publish_slot_reel(slot: str, day: int, content: dict, approved: dict, slot_date,
                       only_asset: str = "", *, allow_image_fallback: bool = True,
                       mirror_facebook: bool = True) -> dict:
    """Publish the slot's own reel. Returns {"contract": held} or the publish results."""
    from content_generator.publisher.instagram import (
        _post_single_image, _assemble_caption, is_configured, _post_reel_direct_binary,
        prepare_feed_image, post_local_story,
    )
    from content_generator.core.instagram_pause import instagram_paused, paused_result
    ig_paused = instagram_paused()
    if ig_paused:
        logger.warning("[slots] Instagram PAUSED (owner kill switch) — %s reel not published; "
                       "Facebook mirror still runs", slot)
    elif not is_configured():
        return {"contract": _held(slot, day, content, "instagram_not_configured")}

    # Publish the OBJECT the canonical gate approved — never look the asset
    # up again separately. Each slot owns exactly one reel (core/reel_schedule):
    # growth_reel in the morning, reel_1 in the evening. reel_2 is retired and
    # no reel substitutes for another, so the day never carries more than two.
    from content_generator.core.reel_schedule import reel_for_slot
    live = _evening_assets_posted(slot_date)
    if reel_for_slot(slot) in live and (not only_asset or only_asset == reel_for_slot(slot)):
        return {"contract": _held(slot, day, content, f"already_published — {reel_for_slot(slot)} is live")}
    picked = _select_slot_reel(approved, slot, live, only=only_asset)
    if not picked:
        logger.error("[slots] %s slot: its reel did not pass the canonical gate or is already "
                     "live (approved=%s)", slot, sorted(approved))
        return {"contract": _held(slot, day, content, "canonical_validation_failed")}
    chosen, reel = picked
    if not ig_paused:
        from content_generator.core.reel_schedule import reel_block_reason
        from content_generator.publisher.publishing_ledger import POSTED_STATES
        why = reel_block_reason(chosen, _reel_records(slot_date), POSTED_STATES)
        if why:
            return {"contract": _held(slot, day, content, why)}
    logger.info("[slots] %s slot publishing gate-approved asset: %s", slot, chosen)
    from content_generator.core.publish_bar import quality_block, reason_code
    reel_block = quality_block(reel, chosen)
    if reel_block:
        return {"contract": _held(slot, day, content, reason_code(reel_block) + " — " + reel_block)}
    body = str(reel.get("caption") or reel.get("hook_text") or reel.get("chosen_hook") or reel.get("hook") or "").strip()
    cta  = str(reel.get("cta") or "").strip()
    if cta and cta.lower() not in body.lower():
        body = f"{body}\n\n{cta}"
    caption = _assemble_caption(body, reel, day)

    # 1. Try an actual REEL VIDEO — HERO video first (founder-produced,
    #    the format that actually spreads), else the free motion reel.
    result = None
    try:
        if ig_paused:
            raise _InstagramPaused()
        # Founder hero videos stay in the prime evening slot.
        hero = _find_hero_video() if slot == "evening" else None
        if hero:
            video_path, is_hero = hero, True
            logger.info("[slots] using HERO video: %s", os.path.basename(hero))
        else:
            from content_generator.creative.reel_video import build_reel_video
            video_path, is_hero = build_reel_video(reel, day, label=chosen, on_date=slot_date), False
        if video_path:
            logger.info("[slots] publishing reel via Meta resumable upload")
            from content_generator.publisher.publishing_ledger import publish_with_ledger
            result = publish_with_ledger(
                "instagram_video", content, slot, day,
                lambda: _post_reel_direct_binary(video_path, caption),
                asset=chosen,
            )
            if result.get("success"):
                logger.info("[slots] %s published %s as %s REEL VIDEO", slot, chosen,
                            "HERO" if is_hero else "motion")
                if is_hero:
                    _mark_hero_posted(video_path)
            else:
                logger.warning("[slots] reel video not published (%s) — falling back to image",
                               result.get("error"))
    except _InstagramPaused:
        result = None
    except Exception as e:
        logger.warning("[slots] reel video path failed (%s) — falling back to image", e)

    # 2. Fallback image. Reel thumbnails are 1080x1920 (9:16). Instagram
    #    feed posts must be between 4:5 and 1.91:1, so a raw thumbnail is
    #    rendered to 4:5. If that render fails, it goes out as a Story
    #    instead of a feed image the API will reject.
    if (not result or not result.get("success")) and not allow_image_fallback:
        if ig_paused:
            result = paused_result()
        result = result or {"success": False, "error": "reel_video_not_built"}
        fb_result = {"success": True, "skipped": True, "error": ""}
    elif not result or not result.get("success"):
        image = _find_reel_thumbnail(slot_date.isoformat())
        if not image:
            return {"contract": _held(slot, day, content, "no_image")}

        from content_generator.creative.jar_provenance import verify_jar_provenance
        prov = verify_jar_provenance(image)
        if not prov.get("verified"):
            return {"contract": _held(slot, day, content, f"real_jar_unverified — {prov.get('reason')}")}

        feed = prepare_feed_image(image)
        if feed:
            from content_generator.creative.rendered_asset_qa import audit_rendered_images
            visual = audit_rendered_images([feed])
            if not visual.get("ok"):
                return {"contract": _held(
                    slot, day, content,
                    "visual_qa_failed — " + "; ".join(visual.get("issues") or ["broken_render"]),
                )}
            from content_generator.publisher.publishing_ledger import publish_with_ledger
            result = paused_result() if ig_paused else publish_with_ledger(
                "instagram", content, slot, day,
                lambda: _post_single_image(feed, caption), asset=chosen)
            fb_result = _mirror_to_facebook(
                content, day, slot, image=feed, message=caption,
                mirror_piece=reel, mirror_label=chosen,
            )
        else:
            logger.warning("[slots] reel thumbnail is not a feed aspect — posting as Story")
            from content_generator.publisher.publishing_ledger import publish_with_ledger
            result = paused_result() if ig_paused else publish_with_ledger(
                "instagram_story", content, slot, day,
                lambda: post_local_story(image), asset=chosen)
            fb_result = _mirror_to_facebook(
                content, day, slot, message=caption,
                mirror_piece=reel, mirror_label=chosen,
            )
    elif mirror_facebook:
        fb_result = _mirror_to_facebook(
            content, day, slot, message=caption,
            mirror_piece=reel, mirror_label=chosen,
        )
    else:
        fb_result = {"success": True, "skipped": True, "error": ""}

    result["hashtags_used"] = " ".join(w for w in caption.split() if w.startswith("#"))
    _track(result, content, slot, reel)
    logger.info("[slots] %s reel publish (%s): %s", slot, chosen, result.get("success"))
    return {"chosen": chosen, "result": result, "fb_result": fb_result, "ig_paused": ig_paused}


_HERO_DIR    = os.getenv("HERO_VIDEO_DIR", "hero_videos")
_HERO_POSTED = os.path.join(os.getenv("LEARNING_DIR", os.path.join("output", "learning")),
                            "hero_posted.json")


def _find_hero_video() -> str | None:
    """
    Return the oldest founder-produced hero video not yet posted.
    Drop .mp4/.mov files in hero_videos/ and the prime evening slot uses them
    first (the format that actually spreads) — slideshow is only the fallback.
    """
    if not os.path.isdir(_HERO_DIR):
        return None
    posted = set()
    if os.path.exists(_HERO_POSTED):
        try:
            posted = set(json.load(open(_HERO_POSTED, encoding="utf-8")))
        except Exception:
            posted = set()
    vids = []
    for ext in ("*.mp4", "*.mov", "*.MP4", "*.MOV"):
        vids += _glob.glob(os.path.join(_HERO_DIR, ext))
    fresh = [v for v in vids if os.path.basename(v) not in posted]
    if not fresh:
        return None
    return sorted(fresh, key=os.path.getmtime)[0]   # oldest first


def _mark_hero_posted(path: str) -> None:
    try:
        posted = []
        if os.path.exists(_HERO_POSTED):
            posted = json.load(open(_HERO_POSTED, encoding="utf-8"))
        posted.append(os.path.basename(path))
        os.makedirs(os.path.dirname(_HERO_POSTED), exist_ok=True)
        json.dump(posted[-500:], open(_HERO_POSTED, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        logger.debug("[slots] could not mark hero posted: %s", e)


def _mirror_to_facebook(content: dict, day: int, slot: str,
                        image: str | None = None, message: str | None = None,
                        mirror_piece: dict | None = None,
                        mirror_label: str | None = None) -> dict:
    """
    Facebook copies Instagram's timing: same slot, same image, same text.

    Returns the publisher result. It used to return None and swallow failures
    into a log line, so Facebook could fail on every run and the slot still
    reported success — the exact "one platform silently fails" case.
    """
    try:
        from content_generator.publisher.facebook import post_content as fb_post
        from content_generator.publisher.publishing_ledger import publish_with_ledger
        r = publish_with_ledger(
            "facebook", content, slot, day,
            lambda: fb_post(
                content, day=day, preferred_image=image, message_override=message,
                mirror_piece=mirror_piece, mirror_label=mirror_label,
            ),
        ) or {}
        if r.get("success"):
            logger.info("[slots] facebook mirror (%s): published", slot)
        else:
            logger.warning(
                "[slots] facebook mirror failed (%s): %s",
                slot, r.get("error") or "unpublished",
            )
        return r
    except Exception as e:
        logger.warning("[slots] facebook mirror failed (%s): %s", slot, e)
        return {"success": False, "error": str(e)[:200]}


class _InstagramPaused(Exception):
    """Internal: owner kill switch skips an Instagram step (not an error)."""


def _contract(slot: str, day: int, content: dict,
              results: dict, expected: dict) -> dict:
    """
    The publish result contract this slot reports back (core/publish_contract).

    Every platform the slot is responsible for appears with its own outcome, so
    the workflow can tell "Instagram published, Facebook failed" from "published".
    """
    from content_generator.core.publish_contract import build, format_report
    norm = {}
    for platform, r in (results or {}).items():
        r = r or {}
        norm[platform] = {
            "status":   "published" if r.get("success") else "failed",
            "asset_id": (expected.get(platform) or [""])[0],
            "remote_id": r.get("media_id") or r.get("post_id") or r.get("id") or "",
            "error":    r.get("error") or "",
        }
    c = build(slot=slot, day=day, expected=expected, results=norm,
              generation_id=str(content.get("generation_id") or ""))
    logger.info("[slots] publish contract:\n%s", format_report(c))
    return c
