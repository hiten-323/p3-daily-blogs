"""
Hook A/B Selector + Creative Fatigue Detector.

Hook A/B:
  Every reel arrives with a primary hook (hook_text) and an alternate
  (alt_hook). Growth reels arrive with up to 10 hook_options.
  score_hook() rates each candidate 0-100 on curiosity, emotional impact,
  scroll-stop power, simplicity, and shareability; the winner is promoted
  to hook_text before publishing. Heuristic scoring — zero extra LLM calls,
  so it never costs TPM budget or adds latency.

Fatigue detection:
  Tracks the hooks/CTAs used in the last 60 days (from the learning log and
  published-post tracker). get_fatigue_block() returns an avoid-list block
  injected into generation prompts so the engine never repeats itself.
"""
from __future__ import annotations
import datetime
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))

# ── Hook scoring (heuristic, 0-100) ──────────────────────────────────────────

_CURIOSITY_WORDS = [
    "why", "what", "how", "secret", "nobody", "never", "hidden", "truth",
    "wrong", "mistake", "lied", "lying", "actually", "really", "won't tell",
    "don't know", "didn't know", "before you", "stop",
]
_EMOTION_WORDS = [
    "shocked", "betrayed", "refuse", "hate", "love", "wish", "regret",
    "finally", "warning", "danger", "exposed", "cheated", "fooled", "wasted",
]
_IDENTITY_WORDS = [
    "you", "your", "you've", "you're", "everyone", "people like",
    "real coffee", "coffee lovers", "if you",
]
_WEAK_OPENERS = ["hey", "hello", "welcome", "today we", "in this", "let me", "i want to"]

# 2026 (heyDominik): conversational "doesn't-sound-like-a-hook" openers slip past
# the ad-blindness shield and outperform clever/bait hooks.
#
# NOTE: "did you know" and "ever wondered" were previously in this REWARDED list
# on the strength of that external research. The founder's Growth Director spec
# bans them outright, with the caveat "unless data proves they outperform" — and
# this account has no data to arbitrate with. The explicit instruction wins; they
# now sit in _BANNED_OPENERS below. Revisit only with own-account evidence.
_CONVERSATIONAL = [
    "here's something", "here's what", "i noticed", "turns out",
    "nobody told me", "the other day", "so i", "i just realised", "i just realized",
    "little known", "most people don't realise", "most people don't realize",
]

# Growth Director spec — formats that read as generic content-marketing. These
# are a hard penalty, not a nudge: a hook opening this way should lose to almost
# any specific alternative.
_BANNED_OPENERS = [
    "did you know", "ever wondered", "here's why", "heres why",
    "the reason why", "let's talk about", "lets talk about",
]
# "5 tips", "7 ways", "3 things to..." — listicle framing.
_LISTICLE = re.compile(
    r"^\s*\d+\s+(tips?|ways?|things?|reasons?|steps?|hacks?|secrets?|facts?)\b", re.I)
# Over-used bait patterns that now read as "this is an ad, skip".
_BAIT_PATTERNS = [
    "shocking", "you won't believe", "this one trick", "gone wrong", "!!!",
    "mind-blowing", "insane", "must watch", "watch till the end",
]


def score_hook(hook: str) -> float:
    """
    Score a hook 0-100 across the five criteria. Deterministic heuristic.
    """
    if not hook or not hook.strip():
        return 0.0
    h = hook.lower().strip()
    words = h.split()
    score = 50.0

    # Curiosity gap (+ up to 20)
    score += min(20, sum(6 for w in _CURIOSITY_WORDS if w in h))
    # Emotional impact (+ up to 15)
    score += min(15, sum(5 for w in _EMOTION_WORDS if w in h))
    # Identity pull (+ up to 10)
    score += min(10, sum(4 for w in _IDENTITY_WORDS if w in h))
    # Simplicity: ideal 4-9 words
    if 4 <= len(words) <= 9:
        score += 10
    elif len(words) > 14:
        score -= 15
    # Scroll-stop: question or bold claim
    if h.endswith("?"):
        score += 5
    if any(h.startswith(w) for w in ("this ", "your ", "stop ", "most ", "nobody ")):
        score += 5
    # Conversational, non-baity opener (2026 — reward feeling real, not "hook-y")
    if any(c in h for c in _CONVERSATIONAL):
        score += 12
    # Penalties: weak openers, numbers pretending to be stats, over-used bait
    if any(h.startswith(w) for w in _WEAK_OPENERS):
        score -= 30
    if re.search(r"\d+%|\d+ out of \d+", h):
        score -= 20  # fabricated-stat risk
    if any(b in h for b in _BAIT_PATTERNS):
        score -= 18  # ad-blindness triggers — reads as bait
    # Growth Director spec: generic openers and listicle framing. Heavier than
    # the bait penalty because these are explicitly named as disqualifying.
    if any(h.startswith(b) for b in _BANNED_OPENERS):
        score -= 35
    if _LISTICLE.match(h):
        score -= 35

    return max(0.0, min(100.0, score))


def hook_violations(hook: str) -> list[str]:
    """
    Named spec violations for a hook — used by the editorial gate so a rejection
    can say WHY rather than just returning a low number.
    """
    h = str(hook or "").lower().strip()
    out = []
    for b in _BANNED_OPENERS:
        if h.startswith(b):
            out.append(f'opens with banned phrase "{b}"')
    if _LISTICLE.match(h):
        out.append("listicle framing (\"5 tips\", \"3 ways\")")
    for b in _BAIT_PATTERNS:
        if b in h:
            out.append(f'bait pattern "{b}"')
    if re.search(r"\d+%|\d+ out of \d+", h):
        out.append("numeric claim in hook — fabricated-stat risk")
    return out


def select_best_hook(piece: dict) -> dict:
    """
    A/B/C hook selection for one content piece, in place.

    Candidates: hook_text, alt_hook, and any hook_options list.
    The winner becomes hook_text; the runner-up is kept as alt_hook.
    Adds piece["hook_ab"] = scoring breakdown for the learning log.
    """
    candidates: list[str] = []
    for key in ("hook_text", "chosen_hook", "alt_hook"):
        v = piece.get(key)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())
    opts = piece.get("hook_options")
    if isinstance(opts, list):
        candidates.extend(str(o).strip() for o in opts if str(o).strip())

    # De-dup preserving order
    seen: set[str] = set()
    unique = [c for c in candidates if not (c.lower() in seen or seen.add(c.lower()))]
    if len(unique) < 2:
        return piece  # nothing to test

    ranked = sorted(unique, key=score_hook, reverse=True)
    winner, runner_up = ranked[0], ranked[1]

    field = "chosen_hook" if "chosen_hook" in piece else "hook_text"
    if piece.get(field, "").strip().lower() != winner.lower():
        logger.info("[hooks] A/B winner: %r (%.0f) over %r (%.0f)",
                    winner, score_hook(winner), piece.get(field, ""), score_hook(piece.get(field, "")))
    piece[field]    = winner
    piece["alt_hook"] = runner_up
    piece["hook_ab"] = [
        {"hook": h, "score": round(score_hook(h), 1)} for h in ranked[:5]
    ]
    return piece


def run_hook_ab(content: dict) -> None:
    """Apply A/B hook selection to every reel-type asset in the day's content."""
    for reel in content.get("reels") or []:
        if isinstance(reel, dict) and reel:
            select_best_hook(reel)
    growth = content.get("growth_reel")
    if isinstance(growth, dict) and growth:
        select_best_hook(growth)


# ── Creative fatigue detection ────────────────────────────────────────────────

_FATIGUE_WINDOW_DAYS = 60


def _recent_creative_history() -> list[dict]:
    """Collect hooks/topics/formats used in the last 60 days from both logs."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=_FATIGUE_WINDOW_DAYS)
    items: list[dict] = []

    for fname in ("performance_log.json", "published_posts.json"):
        path = os.path.join(_LEARNING_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            continue
        for e in entries:
            ts = e.get("posted_at") or e.get("published_at") or ""
            try:
                when = datetime.datetime.fromisoformat(ts[:19])
            except Exception:
                continue
            if when >= cutoff:
                items.append(e)
    return items


def hooks_within_days(days: int = 7) -> list[str]:
    """Hooks posted inside `days`, newest window first, duplicates removed."""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    found: list[str] = []
    for entry in _recent_creative_history():
        ts = entry.get("posted_at") or entry.get("published_at") or ""
        try:
            when = datetime.datetime.fromisoformat(str(ts)[:19])
        except Exception:
            continue
        hook = str(entry.get("hook") or "").strip()
        if hook and when >= cutoff:
            found.append(hook)
    return list(dict.fromkeys(found))


def week_hook_ban(days: int = 7) -> str:
    """Hard ban: do not repeat a hook used in the last week."""
    lines = [f"HOOK BAN: do not repeat or lightly rephrase a hook used in the last {days} days."]
    hooks = hooks_within_days(days)
    if hooks:
        lines.append("Hooks already used this week:")
        lines.extend(f"- {hook[:160]}" for hook in hooks[:30])
    return "\n".join(lines)


def get_fatigue_block(max_items: int = 15) -> str:
    """
    Prompt-injectable block listing recently used hooks/topics so the
    LLM generates something different. Empty string when history is thin.
    """
    history = _recent_creative_history()
    if len(history) < 3:
        return ""

    hooks  = [e.get("hook", "")  for e in history if e.get("hook")]
    topics = [e.get("topic", "") for e in history if e.get("topic")]

    lines = ["CREATIVE FATIGUE GUARD — used in the last 60 days, do NOT repeat or closely imitate:"]
    if hooks:
        lines.append("Hooks already used: " + " | ".join(dict.fromkeys(hooks))[:800])
    if topics:
        lines.append("Topics/angles already used: " + " | ".join(dict.fromkeys(topics))[:400])
    lines.append("Generate something structurally different — new angle, new emotion, new format.")
    return "\n".join(lines)
