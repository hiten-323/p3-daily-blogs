"""
Time-slot publishing — different content at its algorithm-optimal time.

The engine's own platform knowledge says:
  - Feed posts / carousels: 7-9 AM IST (commute + morning coffee scroll)
  - Reels: 7-10 PM IST (evening leisure scroll = highest watch time)

So instead of publishing everything at 06:00 IST, the day is split:

  SLOT       UTC cron    IST     WHAT HAPPENS
  generate   30 0 * * *  06:00   Full pipeline: insights, revenue, generate,
                                 editorial, images, LinkedIn/blog/YouTube.
                                 Instagram + Facebook HELD for their windows.
  morning    30 4 * * *  10:00   IG carousel + FB mirror (owner-chosen time)
  evening    30 16 * * * 22:00   IG reel-style post + FB mirror
                                 (owner-chosen time)

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


def _load_todays_content() -> dict | None:
    """Load the content JSON saved by this morning's generate run."""
    from content_generator.core.ist_dates import today_ist
    date_str = today_ist().isoformat()
    path = os.path.join("output", f"content_{date_str}.json")
    if not os.path.exists(path):
        logger.error("[slots] No content file for today (%s) — generate run missing?", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("[slots] Could not read content file: %s", e)
        return None


def _find_reel_thumbnail() -> str | None:
    """Find today's reel thumbnail image on disk."""
    from content_generator.core.ist_dates import today_ist
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    date_str = today_ist().isoformat()
    for pattern in (f"reel_1_thumb_*_{date_str}.jpg", f"reel_1*{date_str}.jpg",
                    f"reel_hook_*_{date_str}.jpg"):
        matches = sorted(_glob.glob(os.path.join(creative_dir, pattern)))
        if matches:
            return matches[0]
    return None


def _select_evening_reel(approved: dict) -> tuple[str, dict] | None:
    """Prefer growth_reel, then reel_1, then any other approved reel."""
    if not isinstance(approved, dict):
        return None
    for key in ("growth_reel", "reel_1", "reel_2"):
        piece = approved.get(key)
        if isinstance(piece, dict) and piece:
            return key, piece
    for key, piece in approved.items():
        if not isinstance(piece, dict) or not piece:
            continue
        kind = f"{key} {piece.get('type') or ''} {piece.get('id') or ''}".lower()
        if "reel" in kind or str(piece.get("track") or "").lower() == "growth":
            return key, piece
    return None


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


def run_publish_slot(slot: str) -> dict:
    """
    Execute a publish-only slot (morning or evening).
    Loads this morning's generated content and posts the slot's asset.
    """
    from content_generator.scheduler.run_lock import RunLock

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

    lock = RunLock(lock_path=os.path.join("output", f".running_{slot}"))
    lock.__enter__()
    if lock.already_ran:
        logger.info("[slots] %s slot already ran today — skipping", slot)
        return _skipped(slot, reason="already_ran")

    # The lock is taken BEFORE the work and marked completed only after it.
    #
    # This used to call lock.__enter__() and never __exit__(), so RunLock's
    # crash-release path was dead code here: a slot that raised left a lock
    # behind that read as a completed run, and because the workflow reports a
    # skipped slot as green, every later slot that day skipped in silence. The
    # lock file is committed to the repo, so that state outlived the container.
    try:
        result = _execute_publish_slot(slot)
    except Exception:
        lock.release()          # crashed — let the next slot attempt proceed
        raise
    # A HOLD is a legitimate completion: we looked and decided not to publish.
    # Only a crash leaves the lock unmarked.
    lock.mark_completed()
    return result


def _execute_publish_slot(slot: str) -> dict:
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
    content = _load_todays_content()
    if not content:
        return _held(slot, 0, {}, "no_content_for_today — the generate slot "
                                  "produced nothing; publish slots never generate")

    # Correlation: the loaded file must actually be today's work. A stale file
    # left in the working tree would otherwise republish yesterday's asset under
    # today's decision record. content.get("date") may be ISO or the legacy
    # "October 03, 2026" form; both are compared as an IST calendar day.
    from content_generator.core.ist_dates import content_matches_today
    fresh, why = content_matches_today(content)
    if content.get("date") and not fresh:
        # stale_content: why names the file date and today's IST date.
        return _held(slot, content.get("day_number", 0), content, why)

    day = content.get("day_number", 0)

    if slot == "morning":
        # Carousel / feed post + Instagram Story — 10:00 IST (owner-chosen)
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content)

        if "carousel" not in approved and "instagram_post" not in approved:
            return _held(slot, day, content, "canonical_validation_failed")

        # Hand the publisher ONLY gate-approved objects. Blanking a rejected key
        # to {} and relying on post_content to interpret empty-dict as "skip"
        # made the publisher a safety boundary enforced by convention. Assigning
        # straight from `approved` means a rejected asset is absent by
        # construction, not by downstream cooperation.
        filtered_content = content.copy()
        filtered_content["carousel"]        = approved.get("carousel", {})
        filtered_content["instagram_post"]  = approved.get("instagram_post", {})

        from content_generator.publisher.instagram import post_content, post_story
        result = post_content(filtered_content, day=day)
        # Track the approved piece — tracking content.get("carousel") could stamp
        # the learning log with a hook that never passed the gate.
        piece = approved.get("carousel") or approved.get("instagram_post") or {}
        _track(result, content, slot, piece)
        fb_result = _mirror_to_facebook(content, day, slot)
        # Instagram Story (image, 24h) — separate method, same slot
        try:
            story_res = post_story(content, day=day)
            logger.info("[slots] instagram story: %s", story_res.get("success"))
            result["story"] = story_res
        except Exception as e:
            logger.warning("[slots] instagram story failed: %s", e)
        logger.info("[slots] morning publish: %s", result.get("success"))
        asset = "carousel" if "carousel" in approved else "instagram_post"
        return _contract(slot, day, content, {"instagram": result, "facebook": fb_result},
                         {"instagram": [asset], "facebook": [asset]})

    if slot == "evening":
        # Reel video (free motion reel) with image fallback — 22:00 IST
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content)

        from content_generator.publisher.instagram import (
            _post_single_image, _assemble_caption, is_configured, post_reel_video,
            prepare_feed_image, post_local_story,
        )
        if not is_configured():
            return _held(slot, day, content, "instagram_not_configured")

        # Publish the OBJECT the canonical gate approved — never look the asset
        # up again separately. Any approved reel can fill the evening slot;
        # growth_reel and reel_1 are preferred, then reel_2 and anything else
        # the gate returned. A valid reel_2 used to be ignored, so the slot
        # held even when an approved reel was sitting in the file.
        picked = _select_evening_reel(approved)
        if not picked:
            logger.error("[slots] evening slot: no reel passed the canonical gate "
                         "(approved=%s)", sorted(approved))
            return _held(slot, day, content, "canonical_validation_failed")
        chosen, reel = picked
        logger.info("[slots] evening slot publishing gate-approved asset: %s", chosen)

        body = str(reel.get("caption") or reel.get("hook_text") or reel.get("chosen_hook") or reel.get("hook") or "").strip()
        cta  = str(reel.get("cta") or "").strip()
        if cta and cta.lower() not in body.lower():
            body = f"{body}\n\n{cta}"
        caption = _assemble_caption(body, reel, day)

        # 1. Try an actual REEL VIDEO — HERO video first (founder-produced,
        #    the format that actually spreads), else the free motion reel.
        result = None
        try:
            from content_generator.publisher.video_host import upload_video, is_configured as vhost_ok
            hero = _find_hero_video()
            if hero:
                video_path, is_hero = hero, True
                logger.info("[slots] using HERO video: %s", os.path.basename(hero))
            else:
                from content_generator.creative.reel_video import build_reel_video
                video_path, is_hero = build_reel_video(reel, day), False
            if video_path and vhost_ok():
                video_url = upload_video(video_path)
                if video_url:
                    result = post_reel_video(video_url, caption)
                    if result.get("success"):
                        logger.info("[slots] evening published as %s REEL VIDEO",
                                    "HERO" if is_hero else "motion")
                        if is_hero:
                            _mark_hero_posted(video_path)
        except Exception as e:
            logger.warning("[slots] reel video path failed (%s) — falling back to image", e)

        # 2. Fallback image. Reel thumbnails are 1080x1920 (9:16). Instagram
        #    feed posts must be between 4:5 and 1.91:1, so a raw thumbnail is
        #    rendered to 4:5. If that render fails, it goes out as a Story
        #    instead of a feed image the API will reject.
        if not result or not result.get("success"):
            image = _find_reel_thumbnail()
            if not image:
                return _held(slot, day, content, "no_image")
            feed = prepare_feed_image(image)
            if feed:
                result = _post_single_image(feed, caption)
                fb_result = _mirror_to_facebook(content, day, slot, image=feed, message=caption)
            else:
                logger.warning("[slots] reel thumbnail is not a feed aspect — posting as Story")
                result = post_local_story(image)
                fb_result = _mirror_to_facebook(content, day, slot, message=caption)
        else:
            fb_result = _mirror_to_facebook(content, day, slot, message=caption)

        result["hashtags_used"] = " ".join(w for w in caption.split() if w.startswith("#"))
        _track(result, content, slot, reel)
        logger.info("[slots] evening publish: %s", result.get("success"))
        return _contract(slot, day, content,
                         {"instagram": result, "facebook": fb_result},
                         {"instagram": [chosen], "facebook": [chosen]})

    return {"slot": slot, "success": False, "error": f"unknown_slot_{slot}"}


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
                        image: str | None = None, message: str | None = None) -> dict:
    """
    Facebook copies Instagram's timing: same slot, same image, same text.

    Returns the publisher result. It used to return None and swallow failures
    into a log line, so Facebook could fail on every run and the slot still
    reported success — the exact "one platform silently fails" case.
    """
    try:
        from content_generator.publisher.facebook import post_content as fb_post
        r = fb_post(content, day=day, preferred_image=image, message_override=message) or {}
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
