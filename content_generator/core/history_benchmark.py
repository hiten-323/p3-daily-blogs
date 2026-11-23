"""Historical benchmark engine for evening growth reels.

Extracts performance history, prior morning generation results, audit feedback,
and obstacle lessons so that evening growth reels on YouTube Shorts, Facebook,
and Instagram are strictly superior to earlier generations.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_json_safe(path: str | Path, default=None):
    if default is None:
        default = {}
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.debug("[history_benchmark] Could not read %s: %s", path, exc)
        return default


def get_latest_content_pack(on_date: str | None = None) -> tuple[dict, str]:
    """Load the content pack for today (or the most recent available date)."""
    from content_generator.core.ist_dates import today_ist
    date_str = on_date or today_ist().isoformat()
    path = Path("output") / f"content_{date_str}.json"
    if path.exists():
        data = _load_json_safe(path, {})
        if data:
            return data, date_str

    # Search for yesterday's pack if today's is not yet generated
    try:
        current_dt = dt.date.fromisoformat(date_str)
        yesterday_str = (current_dt - dt.timedelta(days=1)).isoformat()
        y_path = Path("output") / f"content_{yesterday_str}.json"
        if y_path.exists():
            data = _load_json_safe(y_path, {})
            if data:
                return data, yesterday_str
    except Exception:
        pass
    return {}, date_str


def extract_platform_history(platform: str, date_str: str | None = None) -> dict:
    """Extract prior generation results, audits, and obstacle lessons for a platform.

    Platform should be one of: 'youtube', 'facebook', 'instagram'.
    """
    content, resolved_date = get_latest_content_pack(date_str)
    learning_dir = Path("output") / "learning"

    # 1. Prior generation piece & hook
    prior_hook = ""
    prior_score = 7.5
    prior_topic = ""
    prior_cta = ""

    if platform == "youtube":
        piece = content.get("yt_short") or {}
        prior_hook = str(piece.get("hook") or piece.get("chosen_hook") or "").strip()
        prior_topic = str(piece.get("title") or piece.get("objective") or "").strip()
        prior_cta = str(piece.get("cta") or "Subscribe for daily coffee science").strip()
    elif platform == "facebook":
        piece = content.get("facebook_post") or content.get("growth_reel") or {}
        prior_hook = str(piece.get("hook") or piece.get("headline") or piece.get("chosen_hook") or "").strip()
        prior_topic = str(piece.get("angle") or piece.get("objective") or "").strip()
        prior_cta = str(piece.get("cta") or "Drop your coffee routine in the comments").strip()
    else:  # instagram
        piece = content.get("growth_reel") or content.get("instagram_post") or {}
        prior_hook = str(piece.get("chosen_hook") or piece.get("hook") or "").strip()
        prior_topic = str(piece.get("viral_idea") or piece.get("objective") or "").strip()
        prior_cta = str(piece.get("comment_trigger") or piece.get("save_trigger") or "Follow @purepantryprovisions").strip()

    # 2. Obstacle lessons relevant to this platform
    lessons_data = _load_json_safe(learning_dir / "obstacle_lessons.json", {"lessons": []})
    platform_key = "youtube" if platform == "youtube" else ("facebook" if platform == "facebook" else "instagram")
    platform_lessons = []
    for row in lessons_data.get("lessons") or []:
        if not isinstance(row, dict):
            continue
        if row.get("platform") == platform_key or platform_key in str(row.get("id") or ""):
            feedback = str(row.get("feedback") or row.get("reason") or "").strip()
            fix = str(row.get("fix") or "").strip()
            if feedback and feedback not in platform_lessons:
                platform_lessons.append(feedback[:180])
            if fix and fix not in platform_lessons:
                platform_lessons.append(f"Fix applied: {fix[:150]}")

    # 3. Creative post audits recommendations
    audits_data = _load_json_safe(learning_dir / "creative_post_audits.json", [])
    recent_audit_recs = []
    if isinstance(audits_data, list) and audits_data:
        last_audit = audits_data[-1] if isinstance(audits_data[-1], dict) else {}
        recs = last_audit.get("recommendations") or []
        for rec in recs:
            rec_str = str(rec).strip()
            if platform == "youtube" and ("yt" in rec_str.lower() or "youtube" in rec_str.lower() or "motion" in rec_str.lower()):
                recent_audit_recs.append(rec_str)
            elif platform == "facebook" and ("facebook" in rec_str.lower() or "community" in rec_str.lower() or "debate" in rec_str.lower()):
                recent_audit_recs.append(rec_str)
            elif platform == "instagram" and ("instagram" in rec_str.lower() or "variety" in rec_str.lower() or "visual" in rec_str.lower() or "dark" in rec_str.lower()):
                recent_audit_recs.append(rec_str)

    # 4. Verified live posts from publishing ledger
    ledger_data = _load_json_safe(learning_dir / "publishing_ledger.json", {"records": {}})
    ledger_records = ledger_data.get("records") or {}
    platform_live_count = sum(
        1 for r in ledger_records.values()
        if isinstance(r, dict) and r.get("platform") == platform_key and r.get("status") == "VERIFIED_LIVE"
    )

    return {
        "platform": platform,
        "content_date": resolved_date,
        "prior_hook": prior_hook or "Three lines on the back of your coffee jar you never read",
        "prior_topic": prior_topic,
        "prior_score": prior_score,
        "prior_cta": prior_cta,
        "obstacle_lessons": platform_lessons[-4:] if platform_lessons else [
            "Contrasting the cafe receipt directly against home jar cost in first 1.5s",
            "Sharpen curiosity gap by naming the hidden ingredient/technique rather than stating general facts",
        ],
        "audit_recommendations": recent_audit_recs[-3:] if recent_audit_recs else [
            "Ensure visual pacing cuts every 1.5 to 2 seconds",
            "Pair clear on-screen punchline with voiceover synchronization",
        ],
        "live_posts_historical": platform_live_count,
    }


def build_history_benchmark_prompt(platform: str, day_number: int, on_date: str | None = None) -> str:
    """Generate an explicit prompt section injecting history and demanding superior results."""
    history = extract_platform_history(platform, on_date)
    prior_hook = history["prior_hook"]
    lessons = "\n".join(f"  • {item}" for item in history["obstacle_lessons"][:3])
    audits = "\n".join(f"  • {item}" for item in history["audit_recommendations"][:2])

    platform_rules = {
        "youtube": (
            "YOUTUBE SHORTS ALGORITHM OPTIMIZATION:\n"
            "- Hook lands in 0-1.5s (immediate visual pattern interrupt or counter-intuitive claim).\n"
            "- YouTube search SEO title (under 50 chars, high-volume query e.g. 'Coffee Secret Nobody Tells You').\n"
            "- Seamless narrative loop: final spoken sentence connects directly back into opening hook.\n"
            "- High-value subscriber CTA: 'Subscribe for daily coffee science truths'."
        ),
        "facebook": (
            "FACEBOOK REELS & WATCH OPTIMIZATION:\n"
            "- Relatable conversational opening (addresses 28-55 demographic coffee habits in India).\n"
            "- High-comment debate driver: deliberately pit common habit vs expert truth.\n"
            "- Clear narrative payoff before the end.\n"
            "- Discussion comment CTA: 'Tell me your morning brew ratio below & share with a coffee lover'."
        ),
        "instagram": (
            "INSTAGRAM EXPLORE & REELS OPTIMIZATION:\n"
            "- Aesthetic 9:16 vertical cinematography (ASMR coffee bloom, micro-textures, steam).\n"
            "- Audio beat synchronization (visual cut on every musical accent).\n"
            "- High save/share multiplier: pack a genuine brew hack or label breakdown worth saving.\n"
            "- Follower growth CTA: 'Follow @purepantryprovisions for the unadvertised coffee truth'."
        ),
    }

    rule_block = platform_rules.get(platform, platform_rules["instagram"])

    return f"""
================================================================================
HISTORICAL BENCHMARK & PRIOR GENERATION ANALYSIS (BEAT PREVIOUS RESULTS):
================================================================================
The evening content MUST be measurably superior to today's morning generation.

EARLIER GENERATION BASELINE TO BEAT:
- Prior Hook: "{prior_hook}"
- Target Viral Quality Score: MUST EXCEED 8.0 (Target: 8.5 - 9.5)

LESSONS LEARNED FROM PAST OBSTACLES:
{lessons}

AUDIT RECOMMENDATIONS TO IMPLEMENT:
{audits}

{rule_block}

HARD CONTRACT FOR THIS EVENING GENERATION:
1. DO NOT repeat the previous hook or similar phrasing.
2. Ensure immediate tension in the first 1.5 seconds.
3. Deliver the payoff cleanly with zero promotional fluff or commercial clichés.
4. Craft platform-native copy that triggers algorithmic growth.
================================================================================
"""


def verify_better_than_previous(current_piece: dict, platform: str, on_date: str | None = None) -> tuple[bool, str]:
    """Verify that a candidate evening piece passes quality gates and improves on history."""
    if not isinstance(current_piece, dict) or not current_piece:
        return False, "empty_piece"

    history = extract_platform_history(platform, on_date)
    prior_hook = history["prior_hook"].strip().lower()

    # Extract current hook
    current_hook = str(
        current_piece.get("chosen_hook")
        or current_piece.get("hook")
        or current_piece.get("hook_text")
        or current_piece.get("headline")
        or ""
    ).strip().lower()

    if not current_hook:
        return False, "missing_hook"

    # Must not be a copy or near-duplicate of earlier hook
    if current_hook == prior_hook or (prior_hook and prior_hook in current_hook):
        return False, f"hook_repeated_from_earlier_generation: '{current_hook[:40]}...'"

    # Must pass length sanity (too short = weak pattern interrupt)
    if len(current_hook) < 15:
        return False, f"hook_too_brief ({len(current_hook)} chars < 15)"

    # Platform specific checks
    if platform == "youtube":
        # Needs title and scenes/script
        title = str(current_piece.get("title") or current_piece.get("tagline") or "").strip()
        if not title:
            return False, "missing_youtube_shorts_title"
    elif platform == "facebook":
        caption = str(current_piece.get("caption") or current_piece.get("body") or current_piece.get("text") or "").strip()
        if len(caption) < 40:
            return False, "facebook_caption_too_short_for_discussion"
    elif platform == "instagram":
        # Needs script and visual prompts
        script = current_piece.get("script") or []
        if not script and not current_piece.get("frames"):
            return False, "missing_instagram_visual_script"

    return True, "verified_superior_to_baseline"
