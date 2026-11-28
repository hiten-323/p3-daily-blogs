"""Distinctness gate: every piece in a day is its own idea, and no surface repeats itself.

Two checks, both on the audience-facing opening (hook), the angle and the
video template:

* same day — no two pieces may open the same way, share an opening phrase,
  or share an angle with an overlapping hook; two video pieces may not use the
  same ad template;
* recent history — a piece may not repeat an opening used on the same
  platform in the last ``NOVELTY_DAYS`` days (from the committed
  ``output/content_<date>.json`` files).

A collision is regenerated with explicit feedback (which piece it collided
with and which angles are still unused), re-checked, and logged as an obstacle
lesson. No quality gate is lowered: regenerated pieces are re-scored by the
normal editorial gate before they can publish.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import logging
import os
import re
from pathlib import Path
from typing import Callable

from content_generator.analytics.post_outcomes import (
    content_pieces, piece_angle, piece_hook, piece_template, text_similarity,
)

logger = logging.getLogger(__name__)

NOVELTY_DAYS = int(os.getenv("NOVELTY_DAYS", "14"))
SAME_DAY_HOOK_SIM = float(os.getenv("DISTINCT_SAME_DAY_SIM", "0.50"))
SAME_ANGLE_HOOK_SIM = 0.30
HISTORY_HOOK_SIM = float(os.getenv("DISTINCT_HISTORY_SIM", "0.55"))
OPENER_WORDS = 4
MAX_ROUNDS = int(os.getenv("DISTINCT_MAX_ROUNDS", "2"))

# Keep the earlier piece, regenerate the later one.
PRIORITY = ("growth_reel", "reel_1", "yt_short", "instagram_post", "carousel",
            "facebook_post", "threads_post", "linkedin_post", "stories")
VIDEO_LABELS = ("growth_reel", "reel_1", "yt_short")
NO_REGEN = {"stories", "blog_post"}
SURFACE = {
    "growth_reel": "instagram", "reel_1": "instagram", "instagram_post": "instagram",
    "carousel": "instagram", "stories": "instagram_story", "facebook_post": "facebook",
    "threads_post": "threads", "linkedin_post": "linkedin", "yt_short": "youtube",
}
ANGLE_POOL = (
    "morning ritual POV (first-person, one real moment)",
    "brew-temperature craft (one precise number)",
    "texture and aroma close-up (sensory, no claims)",
    "freeze-dried vs agglomerated process explainer (only for the matching SKUs)",
    "office desk or travel cup routine",
    "gifting moment",
    "pairing (milk, cold brew, dessert)",
    "label-reading check (what the back of the jar says)",
    "behind the brand (founder decision)",
    "myth vs fact",
    "quick recipe in 3 steps",
    "comment-driven question (one opinion poll)",
)
# Coarse idea clusters. Two pieces on the same surface the same day may not be
# built on the same idea even when the words differ (12 Nov: both Instagram
# reels were "boiling water poured on coffee"; 14 Nov: post and carousel were
# both "the lines on your jar label").
# Recurring LinkedIn founder narratives count as one premise even when wording changes.
LINKEDIN_PREMISES = {
    "failed_batch_walkaway": (
        "walked away", "walk away", "signed contract", "pilot batch", "pilot lot",
        "pilot run", "hollow cup", "label is the only contract", "the label is the contract",
        "dumped the batch", "start over", "almost launched with the wrong label",
    ),
}


def linkedin_premise(text: str) -> str:
    low = str(text or "").lower()
    for name, keys in LINKEDIN_PREMISES.items():
        if any(k in low for k in keys):
            return name
    return ""


CONCEPTS = {
    "water_temperature": ("boil", "kettle", "degree", "°c", "100c", "94c", "temperature", "scorch", "burnt", "hot water"),
    "label_reading": ("label", "ingredient", "back of", "print", "panel", "lines on", "lines of text", "fine print"),
    "chicory_blend": ("chicory", "70/30", "70%", "blend"),
    "process": ("freeze-dried", "freeze dried", "agglomerat", "crystal", "granule", "drying"),
    "milk_coffee": ("milk coffee", "milk", "latte"),
    "aroma_taste": ("aroma", "smell", "caramel", "taste", "sip", "flavor", "flavour", "bitter"),
    "price_value": ("₹", "rupee", "per cup", "cafe bill", "cost", "cups from"),
    "ritual_routine": ("ritual", "routine", "7 am", "desk", "office", "commute"),
    "gifting": ("gift", "diwali", "hamper"),
    "quantity_weight": ("weigh", "gram", "scale", "spoon"),
}


def concept(text: str) -> str:
    low = f" {str(text or '').lower()} "
    hits = {name: sum(low.count(k) for k in keys) for name, keys in CONCEPTS.items()}
    best = max(hits.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else ""


_STOP = {"the", "a", "an", "your", "you", "of", "to", "and", "is", "in", "on", "that", "this", "it", "for", "my"}


def _opener(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if w not in _STOP]
    return " ".join(words[:OPENER_WORDS]) if len(words) >= OPENER_WORDS else ""


def fingerprint(label: str, piece: dict) -> dict:
    hook = piece_hook(piece)
    full = " ".join(str(piece.get(k) or "") for k in ("hook", "body", "cta", "brand_bridge"))
    return {
        "label": label,
        "surface": SURFACE.get(label, label),
        "hook": hook,
        "opener": _opener(hook),
        "angle": piece_angle(piece),
        "concept": concept(hook),
        "premise": linkedin_premise(full) if label == "linkedin_post" else "",
        "template": piece_template(piece) if label in VIDEO_LABELS else "",
    }


def day_fingerprints(content: dict) -> list[dict]:
    pieces = content_pieces(content)
    return [fingerprint(lbl, pieces[lbl]) for lbl in PRIORITY if lbl in pieces and piece_hook(pieces[lbl])]


def load_history(today: dt.date | str | None = None, days: int = NOVELTY_DAYS,
                 output_dir: str | None = None) -> list[dict]:
    """Fingerprints of the previous ``days`` content files (today excluded)."""
    root = Path(output_dir or os.getenv("CONTENT_OUTPUT_DIR", "output"))
    if today is None:
        from content_generator.core.ist_dates import today_ist
        today = today_ist()
    today_s = today.isoformat() if hasattr(today, "isoformat") else str(today)[:10]
    try:
        start = (dt.date.fromisoformat(today_s) - dt.timedelta(days=days)).isoformat()
    except ValueError:
        start = ""
    rows: list[dict] = []
    for path in sorted(glob.glob(str(root / "content_20*.json"))):
        stamp = os.path.basename(path)[8:18]
        if stamp >= today_s or (start and stamp < start):
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for fp in day_fingerprints(data):
            fp["date"] = stamp
            rows.append(fp)
    return rows


def find_collisions(content: dict, history: list[dict] | None = None) -> list[dict]:
    """Collisions that require the named piece to change. Earlier PRIORITY pieces are kept."""
    today = day_fingerprints(content)
    collisions: list[dict] = []
    flagged: set[str] = set()
    for i, keep in enumerate(today):
        for other in today[i + 1:]:
            if other["label"] in flagged:
                continue
            sim = text_similarity(keep["hook"], other["hook"])
            reason = ""
            if sim >= SAME_DAY_HOOK_SIM:
                reason = f"hook {sim:.2f} similar to today's {keep['label']}"
            elif keep["opener"] and keep["opener"] == other["opener"]:
                reason = f"opens with the same words as today's {keep['label']} ('{keep['opener']}')"
            elif keep["angle"] and keep["angle"] == other["angle"] and sim >= SAME_ANGLE_HOOK_SIM:
                reason = f"same angle '{keep['angle']}' and overlapping hook with today's {keep['label']}"
            elif (keep["concept"] and keep["concept"] == other["concept"]
                  and keep["surface"] == other["surface"]):
                reason = f"same idea ('{keep['concept']}') as today's {keep['label']} on {keep['surface']}"
            elif keep["template"] and keep["template"] == other["template"]:
                reason = f"same video template '{keep['template']}' as today's {keep['label']}"
            if reason:
                flagged.add(other["label"])
                collisions.append({"label": other["label"], "kind": "same_day", "with": keep["label"],
                                   "similarity": sim, "reason": reason, "colliding_hook": keep["hook"][:160]})
    for fp in today:
        if fp["label"] in flagged:
            continue
        best = None
        for past in history or []:
            if past.get("surface") != fp["surface"]:
                continue
            sim = text_similarity(fp["hook"], past.get("hook", ""))
            same_open = bool(fp["opener"] and fp["opener"] == past.get("opener") and sim >= 0.35)
            if sim >= HISTORY_HOOK_SIM or same_open:
                if best is None or sim > best[0]:
                    best = (sim, past, bool(same_open))
        if best:
            sim, past, same_open = best
            flagged.add(fp["label"])
            why = "same opening words" if same_open and sim < HISTORY_HOOK_SIM else f"hook {sim:.2f} similar"
            collisions.append({"label": fp["label"], "kind": "recent_repeat", "with": f"{past['label']}@{past['date']}",
                               "similarity": sim, "reason": f"{why} to {past['label']} on {past['date']}",
                               "colliding_hook": str(past.get("hook", ""))[:160]})
        elif fp.get("label") == "linkedin_post" and fp.get("premise"):
            for past in history or []:
                if past.get("label") != "linkedin_post":
                    continue
                if past.get("premise") == fp["premise"]:
                    flagged.add(fp["label"])
                    collisions.append({
                        "label": fp["label"], "kind": "recent_repeat",
                        "with": f"{past['label']}@{past.get('date')}",
                        "similarity": 1.0,
                        "reason": (
                            f"LinkedIn repeated the '{fp['premise']}' premise "
                            f"(failed batch / walked away / label-is-the-contract) used on {past.get('date')}"
                        ),
                        "colliding_hook": str(past.get("hook", ""))[:160],
                    })
                    break
    return collisions


def unused_angles(content: dict, history: list[dict] | None = None, limit: int = 4) -> list[str]:
    used = " ".join([fp["angle"] + " " + fp["hook"] for fp in day_fingerprints(content)]
                    + [str(h.get("angle", "")) for h in (history or [])[-30:]]).lower()
    fresh = [a for a in ANGLE_POOL if not any(w in used for w in re.findall(r"[a-z]{5,}", a.split("(")[0].lower())[:2])]
    return (fresh or list(ANGLE_POOL))[:limit]


def feedback_for(collision: dict, content: dict, history: list[dict] | None = None) -> str:
    angles = "; ".join(unused_angles(content, history))
    return (
        f"DISTINCTNESS REJECTION: {collision['reason']}. "
        f"Colliding opening: \"{collision['colliding_hook']}\". "
        "Write a different idea, not a paraphrase: a new opening line (no shared first four words), "
        f"a different angle and a different visual moment. Angles still unused: {angles}. "
        "Keep every product, price, process and claim rule unchanged."
    )


def _record_lesson(collision: dict) -> None:
    try:
        from content_generator.core.obstacle_lessons import record
        record(SURFACE.get(collision["label"], ""), collision["label"], "distinctness", "novelty",
               collision["reason"], "Every piece needs its own opening, angle and visual; do not repeat a recent hook.",
               fix="Regenerated with a different angle from the unused-angle pool.")
    except Exception as exc:
        logger.debug("[distinctness] lesson skipped: %s", exc)


def _place(content: dict, label: str, piece: dict) -> None:
    if label == "reel_1":
        reels = content.setdefault("reels", [{}])
        if not reels:
            reels.append({})
        reels[0] = piece
    else:
        content[label] = piece


def _current(content: dict, label: str) -> dict:
    return content_pieces(content).get(label) or {}


def enforce_distinctness(content: dict, regenerate: Callable[[str, dict, str], dict | None] | None = None,
                         *, rescore: Callable[[set], None] | None = None, history: list[dict] | None = None,
                         max_rounds: int = MAX_ROUNDS, stage: str = "pre_editorial") -> dict:
    """Detect, regenerate and re-check collisions. Returns the report stored on the content."""
    if history is None:
        try:
            history = load_history(content.get("date"))
        except Exception as exc:
            logger.warning("[distinctness] history unavailable: %s", type(exc).__name__)
            history = []
    first = find_collisions(content, history)
    collisions = list(first)
    changed: set[str] = set()
    rounds = 0
    while collisions and regenerate is not None and rounds < max_rounds:
        rounds += 1
        for collision in collisions:
            label = collision["label"]
            _record_lesson(collision)
            if label in NO_REGEN:
                continue
            piece = _current(content, label)
            try:
                improved = regenerate(label, piece, feedback_for(collision, content, history))
            except Exception as exc:
                logger.warning("[distinctness] regenerate %s failed: %s", label, type(exc).__name__)
                improved = None
            if isinstance(improved, dict) and improved and piece_hook(improved):
                improved.pop("editorial_score", None)
                improved["_distinct_regen"] = int(piece.get("_distinct_regen") or 0) + 1
                _place(content, label, improved)
                changed.add(label)
                logger.info("[distinctness] %s regenerated (%s)", label, collision["reason"])
        collisions = find_collisions(content, history)
    if regenerate is None:
        for collision in collisions:
            _record_lesson(collision)
    if changed and rescore is not None:
        try:
            rescore(set(changed))
        except Exception as exc:
            logger.warning("[distinctness] re-score failed: %s", type(exc).__name__)
    remaining = collisions
    report = {
        "stage": stage,
        "checked": [fp["label"] for fp in day_fingerprints(content)],
        "history_pieces": len(history or []),
        "initial_collisions": first,
        "regenerated": sorted(changed),
        "remaining_collisions": remaining,
        "passes": not remaining,
        "rounds": rounds,
    }
    log = content.setdefault("distinctness", {})
    log[stage] = report
    if remaining:
        logger.warning("[distinctness] %s unresolved after %d round(s): %s", stage, rounds,
                       [(c["label"], c["reason"]) for c in remaining])
    else:
        logger.info("[distinctness] %s: all %d pieces distinct (regenerated %s)", stage,
                    len(report["checked"]), sorted(changed) or "none")
    return report


def novelty_prompt_block(label: str, history: list[dict] | None = None, max_hooks: int = 6) -> str:
    """Prompt text: openings and angles this surface used recently, which must not be reused."""
    surface = SURFACE.get(label)
    if not surface:
        return ""
    if history is None:
        try:
            history = load_history()
        except Exception:
            return ""
    rows = [h for h in history if h.get("surface") == surface and h.get("hook")]
    if not rows:
        return ""
    rows = sorted(rows, key=lambda h: h.get("date", ""), reverse=True)
    lines = [f"NOVELTY RULE ({surface}, last {NOVELTY_DAYS} days): do not reuse or paraphrase these openings:"]
    seen = set()
    for row in rows:
        key = row["opener"] or row["hook"][:40]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  - {row['date']} {row['label']}: \"{row['hook'][:120]}\"")
        if len(seen) >= max_hooks:
            break
    angles: dict[str, int] = {}
    for row in rows:
        if row.get("angle"):
            angles[row["angle"]] = angles.get(row["angle"], 0) + 1
    over = [f"{a} ({n}x)" for a, n in sorted(angles.items(), key=lambda kv: -kv[1]) if n >= 2][:4]
    if over:
        lines.append("Overused angles here — pick another: " + ", ".join(over))
    lines.append("Today's other pieces will use different angles; open with your own idea and your own visual moment.")
    return "\n".join(lines)
