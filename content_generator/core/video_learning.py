"""
Video Learning & Cross-Platform Viral Growth Engine.

Closes the feedback loop between past video performance/editorial scores
and tomorrow's video generation across all platforms (Instagram, Facebook, YouTube).

Extracts:
1. Winning hook archetypes & structures from recent high-performing videos (score >= 8.5).
2. Failure patterns to strictly avoid (score < 8.0 or rejected by viral gate).
3. Real platform metrics (views, shares, comments, net follower growth) from learning logs.
4. Visual & sensory retention drivers (in-situ lighting, crystal dissolution, label proof).
5. Platform-specific follower conversion requirements.
"""
from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join(_DEFAULT_OUTPUT_DIR, "learning"))


def get_real_platform_metrics() -> dict[str, Any]:
    """Load real measured follower growth and top-performing post metrics from learning storage."""
    perf_file = os.path.join(_LEARNING_DIR, "performance_log.json")
    snap_file = os.path.join(_LEARNING_DIR, "follower_snapshots.json")
    
    real_data = {
        "follower_count": 0,
        "follower_delta_7d": 0,
        "top_posts_by_reach": [],
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
            
    return real_data


def get_recent_video_outcomes(max_days: int = 7) -> list[dict[str, Any]]:
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


def build_video_learning_directive(platform: str = "", max_days: int = 7) -> str:
    """
    Synthesize measured previous outcomes and live audience metrics into an actionable
    learning directive for tomorrow's video generation.
    """
    outcomes = get_recent_video_outcomes(max_days=max_days)
    real_metrics = get_real_platform_metrics()
    
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
                
    # Sort winners highest first
    winning_hooks.sort(key=lambda x: x[1], reverse=True)
    losing_hooks.sort(key=lambda x: x[1])

    lines = [
        "=================== VIDEO LEARNING & OUTCOMES FEEDBACK ===================",
        "CRITICAL OWNER MANDATE: Learn from previous generated videos and performance outcomes.",
        "Every video generated must be scroll-stopping, cinematic, and actively compel viewers to follow."
    ]

    if real_metrics["follower_count"] > 0:
        lines.append(f"\nLIVE FOLLOWER DATA: {real_metrics['follower_count']} followers (7-day change: {real_metrics['follower_delta_7d']:+d})")
    
    if real_metrics["top_posts_by_reach"]:
        lines.append("TOP HOOKS BY ACTUAL AUDIENCE REACH & ENGAGEMENT:")
        for post in real_metrics["top_posts_by_reach"][:3]:
            lines.append(f'  ★ [{post["platform"].upper()} - {post["views"]} views, {post["shares"]} shares, {post["comments"]} comments] "{post["hook"]}"')

    if winning_hooks:
        lines.append("\nHIGH-RETENTION PROVEN HOOKS (Clearing >= 8.5 Visual & Viral Gates):")
        for hook, score, fmt in winning_hooks[:4]:
            lines.append(f'  ✓ [{fmt.upper()} - Score {score:.1f}] "{hook}"')
        lines.append("  ↳ LEARNING: Open with active investigation, specific label proof, sensory brewing details, or honest jar labels.")

    if losing_hooks:
        lines.append("\nFAILED / REJECTED HOOK PATTERNS (Scored < 8.0 - STRICTLY BANNED):")
        for hook, score, fmt in losing_hooks[:3]:
            lines.append(f'  ✗ [{fmt.upper()} - Score {score:.1f}] "{hook}"')
        lines.append("  ↳ LEARNING: Avoid passive observations, accounting/math angles, or flat generic statements.")

    # Platform-specific follower conversion requirements
    plat_lower = platform.lower().strip()
    lines.append("\nPLATFORM-SPECIFIC GROWTH & RETENTION REQUIREMENTS:")
    
    if "insta" in plat_lower or plat_lower in ("", "all"):
        lines.append("- INSTAGRAM (Reels):")
        lines.append("  • Hook in first 1.5 seconds with high-tension question or unexpected visual contrast.")
        lines.append("  • Cinematic 1080x1920 pacing with rich studio lighting; single jar in-situ context.")
        lines.append("  • Compelling follow CTA: 'Follow @purepantryprovisions for daily honest coffee craft.'")

    if "face" in plat_lower or plat_lower in ("", "all"):
        lines.append("- FACEBOOK (Watch & Reels):")
        lines.append("  • Front-loaded hook visible before the fold line.")
        lines.append("  • Community engagement question to ignite comments (Facebook's #1 organic reach multiplier).")
        lines.append("  • Page follow CTA: '👉 Follow Pure Pantry Provisions for honest roasts & coffee guides.'")

    if "you" in plat_lower or plat_lower in ("", "all"):
        lines.append("- YOUTUBE SHORTS:")
        lines.append("  • Fast cuts (scene changes every 2.5-4s), tension-then-payoff structure.")
        lines.append("  • Subscribe CTA: 'Subscribe for the honest breakdown on what is in your coffee.'")

    lines.append("==========================================================================")
    return "\n".join(lines)
