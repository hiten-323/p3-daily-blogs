"""
Publishing dispatcher — posts to all configured platforms after content generation.

Called by scheduler/daily.py as the final step of the autonomous pipeline.

Platform publish order:
  1. LinkedIn   — text + image post
  2. Instagram  — carousel or single image
  3. Facebook   — text + image (uses same Meta token as Instagram)
  4. YouTube    — Short (video or slideshow)

Each platform is independent — one failure does not stop the others.
Results are saved to output/publish_log.json and included in the founder report.

Platforms auto-skip if their required secrets are not set.
No secrets needed to test locally — all platforms return {"success": False, "error": "not_configured"}.

Usage:
    from content_generator.publisher.dispatcher import publish_all

    results = publish_all(content, day_number=42)
    # Returns:
    # {
    #   "linkedin":  {"success": True,  "url": "https://linkedin.com/..."},
    #   "instagram": {"success": True,  "permalink": "https://instagram.com/..."},
    #   "facebook":  {"success": False, "error": "not_configured"},
    #   "youtube":   {"success": False, "error": "not_configured"},
    #   "summary":   "Published: LinkedIn, Instagram | Skipped: Facebook, YouTube",
    # }
"""
from __future__ import annotations
import datetime
import json
import logging
import os

from content_generator.core.ist_dates import today_ist

logger = logging.getLogger(__name__)

_PUBLISH_LOG = os.path.join("output", "publish_log.json")


def _approved_or_empty(content: dict) -> dict:
    """Canonical publish gate. Any failure refuses LinkedIn and YouTube."""
    try:
        from content_generator.core.editorial_engine import approved_assets
        approved = approved_assets(content if isinstance(content, dict) else {})
    except Exception as e:
        logger.error(
            "[publisher] approved_assets failed (%s) — LinkedIn and YouTube not attempted",
            e,
        )
        return {}
    return approved if isinstance(approved, dict) else {}


def _editor_rejected(piece: dict) -> bool:
    """True when the editor turned the piece down, rather than merely withholding it."""
    if str(piece.get("editorial_error") or "").strip():
        return True
    score = piece.get("editorial_score")
    if not isinstance(score, dict) or score.get("overall") in (None, ""):
        return True
    verdict = str(score.get("verdict") or "").strip().upper()
    if verdict in ("HOLD", "HELD"):
        return False
    if verdict in ("REJECT", "FAIL", "REJECTED"):
        return True
    try:
        from content_generator.core.editorial_engine import get_current_pass_score
        return float(score.get("overall")) < get_current_pass_score()
    except (TypeError, ValueError):
        return True


def editorial_disposition(content: dict, key: str, approved: dict | None = None) -> str:
    """
    Decision for one asset against editorial_engine.approved_assets.

    approved  the piece cleared the same gate Instagram uses and may be posted
    missing   the piece is not in the payload
    rejected  the piece is present and the editor turned it down
    held      the piece is present, the editor did not reject it, and the gate
              still withheld it
    """
    if approved is None:
        approved = _approved_or_empty(content)
    if key in approved:
        return "approved"
    from content_generator.core.editorial_engine import _piece_for
    piece = _piece_for(content if isinstance(content, dict) else {}, key)
    if not isinstance(piece, dict) or not piece:
        return "missing"
    if _editor_rejected(piece):
        return "rejected"
    return "held"


def not_attempted_result(piece: str, disposition: str) -> dict:
    """A deliberate non-post. It is not a failure and it is not an attempt."""
    return {
        "success": False,
        "attempted": False,
        "skipped": True,
        "error": "not_attempted",
        "piece": piece,
        "gate": disposition,
        "post_id": "",
        "video_id": "",
        "url": "",
    }


def publish_all(content: dict, day_number: int = 0) -> dict:
    """
    Post today's content to all configured platforms.

    Args:
        content:    Daily content dict from the generation pipeline
        day_number: Day number (for logging)

    Returns:
        Dict with per-platform results + summary string
    """
    results: dict = {}

    # content_id / generation_id for end-to-end traceability of every attempt
    _meta = (content.get("_asset_metadata") or [{}])[0] if isinstance(content, dict) else {}
    _content_id = str(_meta.get("content_id", ""))
    _generation_id = str(content.get("generation_id", "") if isinstance(content, dict) else "")

    def _attempt(platform: str, fn) -> dict:
        """Run one publisher, timing it and recording structured diagnostics."""
        import time as _t
        start = _t.perf_counter()
        exc = None
        try:
            res = fn() or {}
        except Exception as e:          # recoverable: one platform must not kill the rest
            logger.error("[publisher] %s exception: %s", platform, e, exc_info=True)
            res, exc = {"success": False, "error": str(e)}, e
        duration_ms = int((_t.perf_counter() - start) * 1000)
        try:
            from content_generator.analytics.telemetry import record_publish
            record_publish(
                platform=platform, result=res, duration_ms=duration_ms,
                content_id=_content_id, generation_id=_generation_id,
                day_number=day_number, http_status=res.get("http_status"),
                retry_count=res.get("retry_count", 0), exception=exc,
            )
        except Exception as e:
            logger.debug("[publisher] telemetry skipped for %s: %s", platform, e)
        res["duration_ms"] = duration_ms
        return res

    # LinkedIn and YouTube use the same canonical gate as Instagram. A piece
    # that is not in approved_assets is not posted, and the skip is not an
    # attempt — a rejection must not fail the run or the publish verification.
    approved = _approved_or_empty(content)

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    li_state = editorial_disposition(content, "linkedin_post", approved)
    if li_state != "approved":
        logger.info("[publisher] Skipping linkedin_post — %s; not attempted", li_state)
        results["linkedin"] = not_attempted_result("linkedin_post", li_state)
    else:
        from content_generator.publisher.linkedin import post_content as li_post
        logger.info("[publisher] Posting to LinkedIn...")
        results["linkedin"] = _attempt("linkedin", lambda: li_post(content, day=day_number))

    # ── Instagram ─────────────────────────────────────────────────────────────
    # With timed slots enabled, Instagram is held for its algorithm-optimal
    # windows (10:00 + 22:00 IST) and published by the morning/evening slot
    # runs instead of the 06:00 generate run.
    import os as _os
    if _os.getenv("ENABLE_TIMED_SLOTS", "false").lower() == "true":
        logger.info("[publisher] Instagram held for timed slots (morning/evening runs)")
        results["instagram"] = {"success": False, "error": "held_for_timed_slot", "held": True}
    else:
        from content_generator.publisher.instagram import post_content as ig_post
        logger.info("[publisher] Posting to Instagram...")
        results["instagram"] = _attempt("instagram", lambda: ig_post(content, day=day_number))

    # ── Facebook (mirrors Instagram timing when slots are enabled) ───────────
    if _os.getenv("ENABLE_TIMED_SLOTS", "false").lower() == "true":
        logger.info("[publisher] Facebook held for timed slots (mirrors Instagram)")
        results["facebook"] = {"success": False, "error": "held_for_timed_slot", "held": True}
    else:
        from content_generator.publisher.facebook import post_content as fb_post
        logger.info("[publisher] Posting to Facebook...")
        results["facebook"] = _attempt("facebook", lambda: fb_post(content, day=day_number))

    # ── YouTube ───────────────────────────────────────────────────────────────
    yt_state = editorial_disposition(content, "yt_short", approved)
    if yt_state != "approved":
        logger.info("[publisher] Skipping yt_short — %s; not attempted", yt_state)
        results["youtube"] = not_attempted_result("yt_short", yt_state)
    else:
        from content_generator.publisher.youtube import post_content as yt_post
        logger.info("[publisher] Posting to YouTube...")
        results["youtube"] = _attempt("youtube", lambda: yt_post(content, day=day_number))

    # ── Threads (Meta Threads API) ───────────────────────────────────────────
    from content_generator.publisher.threads import is_configured as threads_ready, post_content as threads_post
    if not threads_ready():
        logger.info("[publisher] Threads not configured — skipping")
        results["threads"] = {"success": False, "attempted": False, "skipped": True, "error": "not_configured"}
    else:
        logger.info("[publisher] Posting to Threads...")
        results["threads"] = _attempt("threads", lambda: threads_post(content, day=day_number))

    # ── Blog (Shopify article — once per day, generate slot only) ──────────────
    # Same canonical gate as LinkedIn and YouTube. A piece that is not approved
    # is not an attempt. Shopify errors are also skips, inside the publisher.
    blog_slot = _os.getenv("FORCE_SLOT", "").strip()
    blog_state = editorial_disposition(content, "blog_post", approved)
    if blog_slot and blog_slot != "generate":
        logger.info("[publisher] Skipping blog_post — outside generate slot (%s); not attempted", blog_slot)
        results["blog"] = not_attempted_result("blog_post", "wrong_slot")
    elif blog_state != "approved":
        held_reason = ""
        blog_piece = content.get("blog_post") if isinstance(content, dict) else {}
        if isinstance(blog_piece, dict) and str(blog_piece.get("hold_reason") or "").strip():
            held_reason = f" ({blog_piece['hold_reason']})"
            logger.error("[blog] HELD blog_post — %s%s; not attempted", blog_state, held_reason)
        else:
            logger.info("[publisher] Skipping blog_post — %s; not attempted", blog_state)
        results["blog"] = not_attempted_result("blog_post", blog_state)
    else:
        from content_generator.publisher.shopify_blog import post_content as blog_post
        logger.info("[publisher] Posting blog to Shopify...")
        results["blog"] = _attempt("blog", lambda: blog_post(content, day=day_number))

    # ── Summary ───────────────────────────────────────────────────────────────
    # Held (timed slots) and skipped (not configured / no content) are NOT
    # failures — label them honestly so the summary reflects reality.
    _SKIP_ERRORS = (
        "not_configured", "no_blog_content", "no_content", "no_video", "no_image",
        "not_attempted", "blog_disabled", "shopify_error", "missing_secrets",
        "duplicate_handle", "duplicate_title", "blog_quality",
    )
    def _cat(r):
        if r.get("success"):
            return "published"
        if r.get("held") or r.get("error") == "held_for_timed_slot":
            return "held"
        if r.get("attempted") is False or r.get("error") in _SKIP_ERRORS:
            return "skipped"
        return "failed"

    published = [p for p, r in results.items() if _cat(r) == "published"]
    held      = [p for p, r in results.items() if _cat(r) == "held"]
    skipped   = [p for p, r in results.items() if _cat(r) == "skipped"]
    failed    = [p for p, r in results.items() if _cat(r) == "failed"]

    parts = []
    if published:
        parts.append(f"Published: {', '.join(p.title() for p in published)}")
    if held:
        parts.append(f"Held for slot: {', '.join(p.title() for p in held)}")
    if skipped:
        parts.append(f"Skipped: {', '.join(p.title() for p in skipped)}")
    if failed:
        parts.append(f"Failed: {', '.join(p.title() for p in failed)}")

    results["summary"] = " | ".join(parts) or "Nothing published"
    results["published_platforms"] = published
    results["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")

    logger.info("[publisher] Day %d — %s", day_number, results["summary"])

    # Save to publish log
    _append_publish_log(day_number, results)

    return results


def get_publish_log(limit: int = 30) -> list[dict]:
    """Return recent publish results (newest first)."""
    if not os.path.exists(_PUBLISH_LOG):
        return []
    try:
        with open(_PUBLISH_LOG, encoding="utf-8") as f:
            entries = json.load(f)
        return list(reversed(entries[-limit:]))
    except Exception:
        return []


def _append_publish_log(day_number: int, results: dict) -> None:
    """Append today's publish results to the rolling log."""
    os.makedirs("output", exist_ok=True)
    try:
        entries = []
        if os.path.exists(_PUBLISH_LOG):
            with open(_PUBLISH_LOG, encoding="utf-8") as f:
                entries = json.load(f)
    except Exception:
        entries = []

    entries.append({
        "date":        today_ist().isoformat(),
        "day_number":  day_number,
        "results":     results,
    })

    # Keep last 90 days
    entries = entries[-90:]

    try:
        with open(_PUBLISH_LOG, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)
    except Exception as e:
        logger.debug("[publisher] Log write failed: %s", e)


def publisher_status() -> dict:
    """
    Return configuration status for all publishers.
    Used by health_monitor and dashboard.
    """
    from content_generator.publisher import linkedin, instagram, facebook, youtube, threads, shopify_blog

    return {
        "linkedin":  {"configured": linkedin.is_configured()},
        "instagram": {"configured": instagram.is_configured()},
        "facebook":  {"configured": facebook.is_configured()},
        "youtube":   {"configured": youtube.is_configured()},
        "threads":   {"configured": threads.is_configured()},
        "shopify":   {"configured": shopify_blog.is_configured()},
    }
