"""Hard QA for Instagram-native assets/copy before publish.

This gate deliberately fails closed on missing creative-direction metadata. It
cannot judge pixels by itself; callers should pass image-audit results when
available and must never treat a successful image API response as proof of
photorealism.
"""
from __future__ import annotations
import re

BAD_VISIBLE_LABELS = ("slide 1:", "slide 2:", "slide 3:", "headline:", "body_text:")
BAD_GLYPHS = ("\ufffd", "\u25a1")
HOOK_KEYS = ("hook", "hook_text", "chosen_hook", "hook_line")
MOTION_KEYS = ("motion_plan", "scenes", "ai_video_motion_prompt", "ai_video_prompts", "frames", "script")
AUDIO_PLAN_KEYS = ("audio_track", "audio_recommendation", "music_vibe", "sound_suggestion", "audio", "audio_plan", "audio_direction")
LOOP_KEYS = ("loop_ending", "loop_note", "loop_ending_note", "loopable_ending")
VISUAL_DIRECTION_KEYS = ("visual_direction", "image_prompt", "visual_prompt", "art_direction", "visual_brief")
REALISM_KEYS = ("realism_check", "visual_qa", "image_audit", "photorealism_check")
STORY_KEYS = ("story_arc", "narrative_arc", "carousel_story")
REQUIRED_REALISM_TERMS = ("photoreal", "natural light", "contact shadow", "real product")


def _has_any(plan: dict, keys: tuple) -> bool:
    for key in keys:
        value = plan.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return True
    return False


def inspect_copy(text: str, surface: str = "post") -> dict:
    text = (text or "").strip()
    issues = []
    low = text.lower()
    if any(x in low for x in BAD_VISIBLE_LABELS):
        issues.append("internal slide/template label leaked into visible copy")
    if any(x in text for x in BAD_GLYPHS):
        issues.append("unsupported/replacement glyph detected")
    if surface in ("carousel", "story") and len(text) > 220:
        issues.append("too much on-canvas text")
    if surface == "reel" and len(text) > 140:
        issues.append("reel overlay/copy too dense")
    words = re.findall(r"\b[\w'-]+\b", text)
    if surface in ("carousel", "story") and len(words) > 34:
        issues.append("word count too high for mobile creative")
    return {"ok": not issues, "issues": issues}


def inspect_visual_plan(plan: dict, surface: str = "post") -> dict:
    """Validate creative direction before rendering; no pixel-level claims."""
    plan = plan if isinstance(plan, dict) else {}
    issues = []
    if not _has_any(plan, VISUAL_DIRECTION_KEYS):
        issues.append("missing specific art direction / scene prompt")
    direction = " ".join(str(plan.get(k, "")) for k in VISUAL_DIRECTION_KEYS).lower()
    if direction and any(term in direction for term in ("generic coffee jar", "fictional label", "redraw the jar", "invented packaging")):
        issues.append("visual prompt risks fabricated or altered product packaging")
    if surface in ("carousel", "story", "reel") and not _has_any(plan, REALISM_KEYS):
        issues.append("missing visual realism/asset QA result")
    if surface == "carousel" and not _has_any(plan, STORY_KEYS):
        issues.append("carousel lacks a coherent story arc")
    if plan.get("product_asset_verified") is False:
        issues.append("real product asset was not verified")
    if plan.get("visual_qa_passed") is False:
        issues.append("visual QA failed; regenerate or hold")
    return {"ok": not issues, "issues": issues}


def inspect_reel_plan(plan: dict) -> dict:
    plan = plan if isinstance(plan, dict) else {}
    issues = []
    try:
        duration = float(plan.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        duration = 0
        issues.append("invalid reel duration")
    if duration and duration > 35:
        issues.append("reel too long for discovery-first default")
    if not _has_any(plan, HOOK_KEYS):
        issues.append("missing first-second hook")
    if not _has_any(plan, MOTION_KEYS):
        issues.append("missing motion/scene plan")
    if not _has_any(plan, AUDIO_PLAN_KEYS):
        issues.append("missing audio plan")
    if not _has_any(plan, LOOP_KEYS):
        issues.append("missing loopable ending")
    # A recommendation is not proof that a track was attached to the video.
    if plan.get("audio_required") and not (plan.get("audio_attached") or plan.get("audio_publish_mode") in ("manual_native_audio", "licensed_embedded")):
        issues.append("audio required but no attached/approved publishing path is recorded")
    return {"ok": not issues, "issues": issues}


def publish_decision(copy_text="", surface="post", reel_plan=None, visual_plan=None) -> dict:
    checks = [inspect_copy(copy_text, surface)]
    if surface == "reel":
        checks.append(inspect_reel_plan(reel_plan or {}))
    if visual_plan is not None:
        checks.append(inspect_visual_plan(visual_plan, surface))
    issues = [issue for check in checks for issue in check["issues"]]
    return {"allow_publish": not issues, "issues": issues}
