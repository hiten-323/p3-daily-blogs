"""Fallback ladder: when a gate blocks a piece, try again with a different rung.

Hiten's rule: a blocked platform/type gets a replacement, not an empty slot.
The ladder never lowers a gate and never publishes a failing piece. It only
changes WHAT is being scored:

  rungs 1-3  rewrite with the gate's feedback
  rungs 4-5  rewrite on an alternative angle (and, where allowed, another SKU)
  rung  6    a simpler evergreen format built only from verified facts
             (hand-written template for reel/carousel/IG post/LinkedIn,
             a brew-tip / studio-card product rewrite elsewhere)
  rungs 7+   rewrite that evergreen/alt piece with its feedback

It stops at the first variant that passes every hard gate at >= 8.0. The cap
is QUALITY_LADDER_MAX (default 8, hard ceiling 12) so it can never loop
forever; exhaustion returns status "exhausted" so the caller holds and alerts.
"""
from __future__ import annotations
from content_generator.core import price_truth as _PT

import os

DEFAULT_MAX = 8
HARD_CEILING = 12
PASS_FLOOR = 8.0  # never lowered

ALT_ANGLES = (
    "a brew tip the viewer can try tomorrow (water ~85°C, one level spoon, 30-second pause)",
    "what today's jar label says: bean, process, lead-free glass jar, net weight",
    "a granule test: freeze-dried crystals vs spray-dried powder (Purica is freeze-dried)",
    f"on Ultra Blend days only: at least {_PT.ultra('cups')} cups per 100g jar, about ₹{_PT.ultra('per_cup')} a cup",
    "matching a Purity Beans jar to how you drink coffee (black and strong, milk, the smooth 70/30 Ultra Blend)",
)

EVERGREEN_TYPES = {
    "reel_1": "reel", "reel_2": "reel", "growth_reel": "reel",
    "carousel": "carousel", "instagram_post": "instagram_post",
}

SIMPLE_FORMAT_HINT = (
    "SIMPLER EVERGREEN FORMAT: write a short, warm, platform-native piece built only from verified "
    "catalog facts: either a product spotlight on the official studio jar card or one practical brew tip. "
    "Specific hook, one concrete takeaway, then 'Follow @purepantryprovisions' and 'Shop p3online.in'. "
    "Never attack chicory and never compare zero-chicory jars with Ultra Blend."
)


def max_attempts() -> int:
    try:
        n = int(os.getenv("QUALITY_LADDER_MAX", str(DEFAULT_MAX)))
    except (TypeError, ValueError):
        n = DEFAULT_MAX
    return max(1, min(HARD_CEILING, n))


def rung_for(attempt: int) -> str:
    """attempt is 1-based for the REPLACEMENT being built (attempt 1 = first rewrite)."""
    if attempt <= 3:
        return "feedback"
    if attempt <= 5:
        return "alt_angle"
    if attempt == 6:
        return "evergreen"
    return "feedback"


def angle_hint(attempt: int, day: int = 0) -> str:
    angle = ALT_ANGLES[(int(day or 0) + attempt) % len(ALT_ANGLES)]
    return f"ALTERNATIVE ANGLE (the previous angle could not pass): rebuild this piece around {angle}."


def evergreen_piece(label: str, day: int, attempt: int = 0) -> dict | None:
    kind = EVERGREEN_TYPES.get(label)
    try:
        from content_generator.scheduler import fallback as fb
        if kind:
            piece = fb._pick(kind, day, offset=attempt)
        elif label == "linkedin_post":
            piece = fb._DISTRIBUTOR_TEMPLATES[(int(day or 0) + attempt) % len(fb._DISTRIBUTOR_TEMPLATES)]
        else:
            return None
    except Exception:
        return None
    return dict(piece) if isinstance(piece, dict) and piece else None


def build_feedback(rung: str, feedback: str, attempt: int, day: int = 0) -> str:
    fb = str(feedback or "").strip()
    if rung == "alt_angle":
        return f"{fb}\n{angle_hint(attempt, day)}".strip()
    if rung == "evergreen":
        return f"{fb}\n{SIMPLE_FORMAT_HINT}".strip()
    return fb


def passes(score: float | None, hard_fail: bool, threshold: float) -> bool:
    if hard_fail or score is None:
        return False
    return float(score) >= max(PASS_FLOOR, float(threshold))


def run_ladder(label, piece, evaluate, rewrite, *, day: int = 0, threshold: float = PASS_FLOOR,
               cap: int | None = None, evergreen=evergreen_piece):
    """Generic ladder used by tests and callers.

    evaluate(piece) -> (passed: bool, feedback: str); passed must already mean
        "every hard gate clean AND score >= threshold".
    rewrite(label, piece, feedback) -> dict | None
    Returns (piece, record). record["status"] is "passed" or "exhausted".
    """
    cap = max_attempts() if cap is None else max(1, min(HARD_CEILING, int(cap)))
    history = []
    current = piece
    ok, feedback = evaluate(current)
    history.append({"attempt": 0, "rung": "original", "passed": ok, "feedback": feedback})
    attempt = 0
    while not ok and attempt < cap:
        attempt += 1
        rung = rung_for(attempt)
        candidate = None
        if rung == "evergreen":
            candidate = evergreen(label, day, attempt)
            if candidate is None:
                candidate = rewrite(label, current, build_feedback(rung, feedback, attempt, day))
        else:
            candidate = rewrite(label, current, build_feedback(rung, feedback, attempt, day))
        if not isinstance(candidate, dict) or not candidate:
            history.append({"attempt": attempt, "rung": rung, "passed": False, "feedback": "no candidate"})
            continue
        current = candidate
        ok, feedback = evaluate(current)
        history.append({"attempt": attempt, "rung": rung, "passed": ok, "feedback": feedback})
    record = {"label": label, "status": "passed" if ok else "exhausted",
              "attempts": attempt, "cap": cap, "history": history}
    return current, record


# ── From-scratch regeneration for banned-claim failures ──────────────────────
import json as _json
import re as _re

# Copy-gate findings that mean the draft itself carries a banned claim. Feeding
# such a draft back as "ORIGINAL PIECE" made the model copy the claim again
# (day 286: reel_1/reel_2/carousel/threads kept the banned per-cup price (_RS18) on every rewrite).
_BANNED_CLAIM = _re.compile(
    r"product truth|wrong price|never claim|banned|forbidden|not allowed|fssai|100%|"
    r"rs\.? ?18|₹ ?18|anti-chicory|unverified (?:price|claim)",  # _RS18 detector
    _re.IGNORECASE,
)

_SCRATCH_KEEP = ("featured_product", "objective", "primary_cta", "success_metric", "day_number",
                 "content_type", "format", "platform")


def is_banned_claim_failure(feedback: str) -> bool:
    """True when the copy gate (the "brand:" part) rejected the piece for a banned claim.
    Editorial-score feedback alone never triggers a from-scratch rebuild."""
    text = str(feedback or "")
    if "brand:" not in text:
        return False
    return bool(_BANNED_CLAIM.search(text.split("brand:", 1)[1]))


def scratch_base(piece: dict) -> dict:
    """Only non-copy metadata survives; every text field of the bad draft is dropped."""
    return {k: piece[k] for k in _SCRATCH_KEEP if isinstance(piece, dict) and k in piece}


def _lesson_suffix(label: str) -> str:
    try:
        from content_generator.core.obstacle_lessons import prompt_block
        extra = prompt_block(label)
    except Exception:
        extra = ""
    return f"\n\n{extra}" if extra else ""


def scratch_prompt(label: str, piece: dict, feedback: str, threshold: float, brand: str) -> str:
    """Prompt for a brand-new piece. The rejected copy is NOT included, only its shape."""
    if label == "facebook_post":
        # A saved facebook_post can carry a blog/carousel pack in `_shape`. Asking
        # for those keys again makes every retry an article the native gates reject.
        from content_generator.prompts.facebook import regeneration_prompt
        return regeneration_prompt(piece, feedback, threshold, brand, from_scratch=True)
    keys = (piece or {}).get("_shape") or sorted(
        k for k in (piece or {}) if k not in ("editorial_score", "editorial_error", "needs_regen",
                                              "held", "hold_reason", "_shape"))
    featured = (piece or {}).get("featured_product") or "the featured Purity Beans jar"
    reasons = _re.sub(r"\s+", " ", str(feedback or ""))[:600]
    return (
        f"{brand}\n\n"
        f"TASK: Write a BRAND-NEW {label} from scratch for {featured}. It must pass schema and an "
        f"editorial score of {threshold}.\n"
        f"The previous draft was discarded because it contained a banned claim: {reasons}\n"
        "Do not reuse any sentence, number, or price from that draft. Use only catalog prices and facts "
        "from the brand rules above. Per-cup price and cup count belong only to Ultra Blend, in a sentence "
        "that names Ultra Blend. If the featured jar is anything else, omit the figure.\n"
        f"Return ONE JSON object with these keys: {_json.dumps(keys)}.\n"
        "Reel frames: at least 5 objects, each with on_screen and spoken. Captions at least 50 characters. "
        "Keep STOP, CURIOSITY, VALUE, TRUST, FOLLOW, BUY. End with 'Follow @purepantryprovisions' and "
        "'Shop p3online.in'. Do not include an editorial_score.\n"
        "Return ONLY the JSON object."
    ) + _lesson_suffix(label)
