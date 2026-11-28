"""Daily feedback adaptation engine: delivers real yesterday/last 7 days feedback into prompts.

Builds a compact (<= 900 chars) platform-specific feedback block containing:
1. YESTERDAY / LAST 7 DAYS on <platform>: top & bottom performer (hook, angle, metrics)
   only when real non-zero audience signal exists; else 'no reliable metrics yet - use gate feedback below'.
2. GATE FEEDBACK DIGEST: top 3 recurring weakest dimensions for this platform over last 3 days
   with concrete fix from passing pieces.
3. DO NOT REPEAT: recent hooks and premises to avoid repetition.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_BLOCK_CHARS = 900
_LEARNING_DIR = Path(os.getenv("LEARNING_DIR", "output/learning"))
_POSTS_PATH = _LEARNING_DIR / "published_posts.json"
_LESSONS_PATH = _LEARNING_DIR / "obstacle_lessons.json"
_OUTCOMES_PATH = _LEARNING_DIR / "post_outcomes.json"


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("[daily-feedback] failed reading %s: %s", path, exc)
    return fallback


def build_feedback_block(platform: str, today: str | None = None) -> str:
    """Build a concise platform-tailored feedback block (<= 900 chars)."""
    plat = str(platform or "").strip().lower()
    if plat.endswith("_post"):
        plat = plat.replace("_post", "")
    elif plat in ("reel_1", "reel_2", "growth_reel", "stories"):
        plat = "instagram"
    elif plat in ("yt_short", "youtube_short"):
        plat = "youtube"

    today_str = today or dt.date.today().isoformat()
    lines = [f"### ADAPTATION & PERFORMANCE FEEDBACK ({plat.upper()}):"]

    # 1. Performance Section: Top & Bottom performers (only with non-zero signal)
    posts = _read_json(_POSTS_PATH, [])
    cutoff = (dt.date.fromisoformat(today_str) - dt.timedelta(days=7)).isoformat()
    
    relevant = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        p_plat = str(p.get("platform") or "").lower()
        if p_plat == plat or (plat == "instagram" and "instagram" in p_plat):
            pub_at = str(p.get("published_at") or "")
            if pub_at >= cutoff:
                relevant.append(p)

    # Calculate metrics with non-zero audience engagement
    measured_with_signal = []
    for p in relevant:
        snaps = p.get("measurement_snapshots") or []
        metrics = {}
        for s in snaps:
            if isinstance(s, dict) and isinstance(s.get("metrics"), dict):
                metrics.update(s["metrics"])
        # Sum non-zero signals (likes, comments, reactions, impressions, views)
        total_signal = sum(v for k, v in metrics.items() if isinstance(v, (int, float)) and v > 0)
        if total_signal > 0:
            p_copy = dict(p)
            p_copy["_signal"] = total_signal
            p_copy["_metrics"] = metrics
            measured_with_signal.append(p_copy)

    if measured_with_signal:
        measured_with_signal.sort(key=lambda x: x["_signal"], reverse=True)
        top = measured_with_signal[0]
        bottom = measured_with_signal[-1]
        
        top_hook = str(top.get("hook") or "unknown hook")[:60]
        top_ang = str(top.get("angle") or top.get("topic") or "general")
        top_sig = top["_metrics"]
        lines.append(f"YESTERDAY / LAST 7 DAYS on {plat}:")
        lines.append(f"- TOP PERFORMER: \"{top_hook}\" (angle: {top_ang}, metrics: {top_sig})")
        if len(measured_with_signal) > 1:
            bot_hook = str(bottom.get("hook") or "unknown hook")[:60]
            bot_ang = str(bottom.get("angle") or bottom.get("topic") or "general")
            bot_sig = bottom["_metrics"]
            lines.append(f"- BOTTOM PERFORMER: \"{bot_hook}\" (angle: {bot_ang}, metrics: {bot_sig})")
    else:
        lines.append(f"YESTERDAY / LAST 7 DAYS on {plat}: no reliable metrics yet — use gate feedback below")

    # 2. Gate Feedback Digest: top 3 recurring weakest dimensions from obstacle lessons
    lessons_data = _read_json(_LESSONS_PATH, {})
    lessons = lessons_data.get("lessons") or []
    weak_counter = Counter()
    concrete_fix = ""

    for l in lessons:
        if not isinstance(l, dict):
            continue
        l_plat = str(l.get("platform") or "").lower()
        if l_plat == plat or (plat == "instagram" and "instagram" in l_plat):
            code = str(l.get("code") or l.get("reason") or "")
            count = int(l.get("count") or 1)
            if code:
                weak_counter[code] += count
            if not concrete_fix and l.get("fix"):
                concrete_fix = str(l.get("fix"))[:120]

    top_weak = weak_counter.most_common(3)
    if top_weak:
        weak_str = ", ".join(f"{k} {v}x" for k, v in top_weak)
        lines.append(f"GATE FEEDBACK DIGEST: top recurring weaknesses: {weak_str}")
        if concrete_fix:
            lines.append(f"- Applied fix: {concrete_fix}")

    # 3. Do Not Repeat: Last 7 days' hooks + narrative premises
    recent_hooks = []
    for p in relevant:
        h = str(p.get("hook") or "").strip()
        if h and h not in recent_hooks:
            recent_hooks.append(h[:70])

    if recent_hooks:
        lines.append("DO NOT REPEAT (last 7 days' hooks/premises):")
        for h in recent_hooks[:3]:
            lines.append(f"- \"{h}\"")
    elif plat == "linkedin":
        lines.append("DO NOT REPEAT: generic 'walked away from contract' or 'pilot batch failed' premises")

    block = "\n".join(lines)
    if len(block) <= _MAX_BLOCK_CHARS:
        return block
    return block[:_MAX_BLOCK_CHARS].rsplit("\n", 1)[0]


def persist_daily_feedback(injected: dict[str, str], today: str | None = None) -> Path:
    """Save daily feedback block snapshot for human audit."""
    today_str = today or dt.date.today().isoformat()
    out_dir = Path(os.getenv("LEARNING_DIR", "output/learning"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"daily_feedback_{today_str}.json"
    
    payload = {
        "date": today_str,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "injected_feedback": injected,
    }
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("[daily-feedback] Saved feedback audit to %s", out_file)
    return out_file
