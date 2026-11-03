"""
Video Learning & Cross-Platform Viral Growth Engine.

Closes the feedback loop between past video performance/editorial scores
and tomorrow's video generation across all platforms (Instagram, Facebook, YouTube).

Features:
1. Winning hook archetypes & structures from recent high-performing videos (score >= 8.5).
2. Failure patterns populated from actual obstacle lessons & gate rejections (score < 8.0).
3. 14-day hook deduplication: prevents reusing identical hooks.
4. Honest sparse data handling: logs when audience data is sparse without fabricating trends.
5. Per-platform video metrics collection into performance_log.json.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join(_DEFAULT_OUTPUT_DIR, "learning"))


def _normalize_hook(text: str) -> str:
    """Normalize a hook for comparison (lowercase, alphanumeric, collapsed spaces)."""
    t = re.sub(r"[^a-z0-9\s]", "", str(text or "").lower())
    return " ".join(t.split())


def get_real_platform_metrics() -> dict[str, Any]:
    """Load real measured follower growth and top-performing post metrics from learning storage."""
    perf_file = os.path.join(_LEARNING_DIR, "performance_log.json")
    snap_file = os.path.join(_LEARNING_DIR, "follower_snapshots.json")
    
    real_data = {
        "follower_count": 0,
        "follower_delta_7d": 0,
        "top_posts_by_reach": [],
        "is_sparse": True,
    }
    
    if os.path.exists(snap_file):
        try:
            with open(snap_file, "r", encoding="utf-8") as fh:
                snaps = json.load(fh)
            if isinstance(snaps, list) and snaps:
                real_data["follower_count"] = snaps[-1].get("count", 0)
                if len(snaps) > 1:
                    first_count = snaps[max(0, len(snaps) - 7)].get("count", 0)
                    real_data["follower_delta_7d"] = real_data["follower_count"] - first_count
        except Exception as e:
            logger.debug("[video_learning] follower snapshot load error: %s", e)
            
    if os.path.exists(perf_file):
        try:
            with open(perf_file, "r", encoding="utf-8") as fh:
                logs = json.load(fh)
            if isinstance(logs, list):
                scored_posts = []
                for p in logs:
                    hook = str(p.get("hook") or "").strip()
                    m = p.get("metrics") or {}
                    views = int(m.get("views") or 0)
                    shares = int(m.get("shares") or 0)
                    comments = int(m.get("comments") or 0)
                    if hook and (views > 0 or shares > 0 or comments > 0):
                        scored_posts.append({
                            "hook": hook,
                            "platform": p.get("platform", "unknown"),
                            "views": views,
                            "shares": shares,
                            "comments": comments,
                            "score": views + (shares * 5) + (comments * 3),
                        })
                scored_posts.sort(key=lambda x: x["score"], reverse=True)
                real_data["top_posts_by_reach"] = scored_posts[:5]
        except Exception as e:
            logger.debug("[video_learning] performance log load error: %s", e)

    # Sparse check: if no follower count or no engagement records
    if real_data["follower_count"] > 0 and len(real_data["top_posts_by_reach"]) >= 3:
        real_data["is_sparse"] = False
    else:
        real_data["is_sparse"] = True
            
    return real_data


def get_recent_video_outcomes(max_days: int = 14) -> list[dict[str, Any]]:
    """Inspect previous days' content packs and extract video outcomes and scores."""
    outcomes: list[dict[str, Any]] = []
    pattern = os.path.join(_DEFAULT_OUTPUT_DIR, "content_*.json")
    files = sorted(glob.glob(pattern))
    
    for fpath in files[-max_days:]:
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            
            date = str(data.get("date") or os.path.basename(fpath).replace("content_", "").replace(".json", ""))
            
            # 1. growth_reel
            gr = data.get("growth_reel") or {}
            gr_hook = str(gr.get("hook") or gr.get("chosen_hook") or "").strip()
            gr_score = float((gr.get("editorial_score") or {}).get("overall") or 0.0)
            
            # 2. reel_1
            r1 = data.get("reel_1") or (data.get("reels", [{}])[0] if data.get("reels") else {})
            r1_hook = str(r1.get("hook") or r1.get("hook_text") or "").strip()
            r1_score = float((r1.get("editorial_score") or {}).get("overall") or 0.0)
            
            # 3. yt_short
            yt = data.get("yt_short") or {}
            yt_hook = str(yt.get("hook") or yt.get("title") or "").strip()
            yt_score = float((yt.get("editorial_score") or {}).get("overall") or 0.0)
            
            outcomes.append({
                "date": date,
                "growth_reel": {"hook": gr_hook, "score": gr_score, "format": "growth_reel"},
                "reel_1": {"hook": r1_hook, "score": r1_score, "format": "reel_1"},
                "yt_short": {"hook": yt_hook, "score": yt_score, "format": "yt_short"},
            })
        except Exception as e:
            logger.debug("[video_learning] could not parse %s: %s", fpath, e)
            
    return outcomes


def get_recent_hooks(days: int = 14) -> list[str]:
    """Return all unique hooks used across videos in the last `days` days."""
    outcomes = get_recent_video_outcomes(max_days=days)
    hooks: list[str] = []
    seen = set()
    for day in outcomes:
        for key in ("growth_reel", "reel_1", "yt_short"):
            hook = (day.get(key) or {}).get("hook", "").strip()
            if hook:
                norm = _normalize_hook(hook)
                if norm and norm not in seen:
                    seen.add(norm)
                    hooks.append(hook)
    return hooks


def is_duplicate_hook(hook: str, days: int = 14) -> bool:
    """Return True if `hook` matches any video hook from the past `days` days."""
    norm = _normalize_hook(hook)
    if not norm:
        return False
    recent = {_normalize_hook(h) for h in get_recent_hooks(days=days)}
    return norm in recent


def get_failed_patterns_from_lessons(max_lessons: int = 8) -> list[dict[str, str]]:
    """Populate failed patterns and rejection reasons from real gate lessons."""
    lessons_file = os.path.join(_LEARNING_DIR, "obstacle_lessons.json")
    if not os.path.exists(lessons_file):
        return []
    
    failures = []
    try:
        with open(lessons_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        lessons = data.get("lessons", []) if isinstance(data, dict) else []
        for l in lessons:
            platform = str(l.get("platform") or "").lower()
            gate = str(l.get("gate") or "").lower()
            desc = str(l.get("feedback") or l.get("obstacle") or l.get("description") or "").strip()
            if not desc or desc.lower() == "none":
                continue
            # Pick lessons relevant to video/reels/shorts, editorial quality, or claims
            if any(k in platform for k in ("reel", "video", "youtube", "yt", "short")) or gate in ("editorial", "viral", "visual", "brand"):
                failures.append({
                    "gate": gate or "gate",
                    "reason": desc[:140],
                    "platform": platform or "video",
                })
                if len(failures) >= max_lessons:
                    break
    except Exception as e:
        logger.debug("[video_learning] failed to load obstacle lessons: %s", e)

    return failures


def record_platform_video_metrics(
    platform: str,
    asset_id: str,
    publication_id: str,
    hook: str,
    views: int,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    """Append or update a platform video metrics record in performance_log.json."""
    import datetime as dt
    os.makedirs(_LEARNING_DIR, exist_ok=True)
    perf_file = os.path.join(_LEARNING_DIR, "performance_log.json")
    
    logs: list[dict[str, Any]] = []
    if os.path.exists(perf_file):
        try:
            with open(perf_file, "r", encoding="utf-8") as fh:
                logs = json.load(fh)
        except Exception:
            logs = []
    if not isinstance(logs, list):
        logs = []

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {
        "asset_id": asset_id,
        "platform": platform,
        "publication_id": publication_id,
        "hook": hook,
        "recorded_at": now_iso,
        "metrics": {
            "views": int(views),
            "likes": int(likes),
            "comments": int(comments),
            "shares": int(shares),
        },
        "notes": notes or f"recorded from {platform} native metrics API",
    }

    # Dedupe by publication_id if provided
    updated = False
    if publication_id:
        for i, existing in enumerate(logs):
            if existing.get("publication_id") == publication_id:
                logs[i] = record
                updated = True
                break
    if not updated:
        logs.append(record)

    try:
        tmp_file = perf_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(logs, fh, indent=2)
        os.replace(tmp_file, perf_file)
    except Exception as e:
        logger.warning("[video_learning] failed to save performance log: %s", e)

    return record


def build_video_learning_directive(platform: str = "", max_days: int = 14) -> str:
    """
    Synthesize measured previous outcomes, gate lessons, and audience metrics into an actionable
    learning directive for tomorrow's video generation.
    """
    outcomes = get_recent_video_outcomes(max_days=max_days)
    real_metrics = get_real_platform_metrics()
    failed_lessons = get_failed_patterns_from_lessons(max_lessons=6)
    recent_hooks = get_recent_hooks(days=14)
    
    winning_hooks: list[tuple[str, float, str]] = []
    losing_hooks: list[tuple[str, float, str]] = []
    
    for day in outcomes:
        for key in ("growth_reel", "reel_1", "yt_short"):
            item = day.get(key) or {}
            hook = item.get("hook", "")
            score = item.get("score", 0.0)
            if not hook or score <= 0.0:
                continue
            if score >= 8.5:
                winning_hooks.append((hook, score, key))
            elif score < 8.0:
                losing_hooks.append((hook, score, key))
                
    winning_hooks.sort(key=lambda x: x[1], reverse=True)
    losing_hooks.sort(key=lambda x: x[1])

    lines = [
        "=================== VIDEO LEARNING & OUTCOMES FEEDBACK ===================",
        "CRITICAL OWNER MANDATE: Learn from previous generated videos and performance outcomes.",
        "Every video generated must be scroll-stopping, cinematic, and actively compel viewers to follow."
    ]

    # Audience metrics & honest sparse data handling
    if real_metrics["follower_count"] > 0:
        lines.append(f"\nLIVE FOLLOWER DATA: {real_metrics['follower_count']} followers (7-day change: {real_metrics['follower_delta_7d']:+d})")
        if real_metrics["top_posts_by_reach"]:
            lines.append("TOP HOOKS BY ACTUAL AUDIENCE REACH & ENGAGEMENT:")
            for post in real_metrics["top_posts_by_reach"][:3]:
                lines.append(f'  * [{post["platform"].upper()} - {post["views"]} views, {post["shares"]} shares, {post["comments"]} comments] "{post["hook"]}"')
        else:
            lines.append("REAL AUDIENCE DATA: Sparse post engagement data (falling back to editorial evaluation scores). No trend fabricated.")
    else:
        logger.info("[video_learning] Sparse performance data; falling back to editorial scores without fabricating trends")
        lines.append("\nREAL AUDIENCE DATA: Sparse/insufficient performance data (falling back to editorial evaluation scores). No trend fabricated.")

    # Winning hooks
    if winning_hooks:
        lines.append("\nHIGH-RETENTION PROVEN HOOKS (Clearing >= 8.5 Visual & Viral Gates):")
        for hook, score, fmt in winning_hooks[:4]:
            lines.append(f'  + [{fmt.upper()} - Score {score:.1f}] "{hook}"')
        lines.append("  -> LEARNING: Open with active investigation, specific label proof, sensory brewing details, or honest jar labels.")

    # Failed patterns from both low scores AND obstacle lessons
    lines.append("\nFAILED / REJECTED HOOK PATTERNS (Scored < 8.0 or Rejected at Gate - STRICTLY BANNED):")
    if losing_hooks:
        for hook, score, fmt in losing_hooks[:3]:
            lines.append(f'  x [{fmt.upper()} - Score {score:.1f}] "{hook}"')
    if failed_lessons:
        for fl in failed_lessons[:4]:
            lines.append(f'  x [{fl["gate"].upper()} GATE REJECTION - {fl["platform"]}] {fl["reason"]}')
    lines.append("  -> LEARNING: Avoid passive observations, plain catalog product cutouts, unverified claims, or flat generic statements.")

    # 14-day deduplication warning
    if recent_hooks:
        lines.append("\nRECENTLY USED HOOKS (DO NOT REPEAT OR REUSE IN THE LAST 14 DAYS):")
        for rh in recent_hooks[:10]:
            lines.append(f'  ! BANNED REPEAT: "{rh}"')

    # Platform-specific follower conversion requirements
    plat_lower = platform.lower().strip()
    lines.append("\nPLATFORM-SPECIFIC GROWTH & RETENTION REQUIREMENTS:")
    
    if "insta" in plat_lower or plat_lower in ("", "all"):
        lines.append("- INSTAGRAM (Reels):")
        lines.append("  * Hook in first 1.5 seconds with high-tension question or unexpected visual contrast.")
        lines.append("  * Cinematic 1080x1920 pacing with rich studio lighting; single jar in-situ context.")
        lines.append("  * Compelling follow CTA: 'Follow @purepantryprovisions for daily honest coffee craft.'")

    if "face" in plat_lower or plat_lower in ("", "all"):
        lines.append("- FACEBOOK (Watch & Reels):")
        lines.append("  * Front-loaded hook visible before the fold line.")
        lines.append("  * Community engagement question to ignite comments (Facebook's #1 organic reach multiplier).")
        lines.append("  * Page follow CTA: '👉 Follow Pure Pantry Provisions for honest roasts & coffee guides.'")

    if "you" in plat_lower or plat_lower in ("", "all"):
        lines.append("- YOUTUBE SHORTS:")
        lines.append("  * Fast cuts (scene changes every 2.5-4s), tension-then-payoff structure.")
        lines.append("  * Subscribe CTA: 'Subscribe for the honest breakdown on what is in your coffee.'")

    lines.append("==========================================================================")
    return "\n".join(lines)
