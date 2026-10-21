"""Pre-publish VIRAL POTENTIAL gate (LLM-scored, 8.0 pass mark, per platform/format).

Builds on the existing growth framework (core/growth_engine.py, core/viral_readiness.py,
prompts/growth_engine). Those stay as they are; this adds a free-LLM judge, routed through
providers/llm_router (label "viral_<piece>", so provider_budget rotation applies).

Order in the editorial loop (scheduler/daily.py): schema -> copy/claim gate -> editorial 8.0
-> THIS gate. It only scores pieces that already passed every honesty rule, and its own
honesty screen hard-fails fabricated urgency, reviews, metrics or health claims. Virality
never overrides honesty: a piece cannot pass here by adding anything the copy gate forbids.

A failing piece goes back into the mandatory regeneration ladder with this gate's feedback
plus a different hook template, then is rescored. PASS_MARK is never lowered.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

PASS_MARK = 8.0  # never lowered

DIMENSIONS = {
    "hook": "first 1-2 seconds / first line stops the scroll (pattern interrupt, specific, not generic)",
    "curiosity_gap": "open loop or curiosity gap that is paid off inside the piece",
    "relatability": "emotional pull from Indian coffee life: the morning ritual, the office cup, filter-coffee homes, chai-vs-coffee households",
    "shareability": "save/share value: a usable tip, a myth-buster, a 'send this to a coffee lover' reason",
    "comment_trigger": "a real question or this-or-that that invites a comment",
    "format_fit": "native format mechanics for this platform (see FORMAT RULES)",
    "follow_cta": "a clear reason + CTA to follow @purepantryprovisions",
}

FORMAT_RULES = {
    "reel": "cut/new on-screen beat every 1-2s, hook in frame 1, ending that loops back into the opening",
    "yt_short": "hook in the first second, 3-beat pace, loopable ending, title that opens a loop",
    "carousel": "slide-1 promise, swipe tension on every slide (each slide teases the next), save-worthy final slide",
    "instagram_post": "one bold idea, caption first line works as a headline, save/share reason",
    "story": "one idea per frame, tap-forward tension, interactive prompt (poll/question/this-or-that)",
    "threads_post": "a confident hot take or contrarian-but-true opener that invites replies",
    "linkedin_post": "founder story: first line hook, a real lesson from building the brand, a question to the network",
    "facebook_post": "conversational, relatable household angle, a question that is easy to answer",
    "blog_post": "title and first paragraph open a loop, scannable useful answers, a shareable takeaway",
}

LABEL_FORMAT = {
    "reel_1": "reel", "reel_2": "reel", "growth_reel": "reel", "yt_short": "yt_short",
    "carousel": "carousel", "instagram_post": "instagram_post", "story": "story",
    "instagram_story": "story", "stories": "story", "threads_post": "threads_post",
    "linkedin_post": "linkedin_post", "facebook_post": "facebook_post", "blog_post": "blog_post",
}

# Proven hook templates per format. Filled only with verified facts; never with invented numbers.
HOOK_TEMPLATES = {
    "reel": [
        "Stop stirring your coffee like this ↓ (pattern interrupt + fix)",
        "POV: it's 9:40 at the office and the cup actually tastes good",
        "I read the label so you don't have to: <one real label fact>",
        "You've been making instant coffee wrong. Here's the 30-second fix",
        "Freeze-dried vs spray-dried: watch what happens in hot water",
    ],
    "yt_short": [
        "One spoon, 85°C water, wait 30 seconds. Watch.",
        "The coffee mistake almost every Indian kitchen makes",
        "What's actually inside this jar? Let's read it",
    ],
    "carousel": [
        "5 coffee myths your office still believes (swipe → #3 surprises everyone)",
        "Save this: the 4-step cup that tastes like a café's",
        "Which coffee person are you? Swipe to find your jar",
    ],
    "instagram_post": [
        "Unpopular opinion: the best cup of the day is the 4 PM one",
        "Send this to the friend who drinks 3 cups before lunch",
        "Black, milky or smooth blend? Pick one ↓",
    ],
    "story": [
        "Quick poll: filter coffee or instant on a weekday?",
        "Tap → the 30-second trick for a better morning cup",
        "This or that: strong & black / smooth with milk",
    ],
    "threads_post": [
        "Hot take: most people never taste their coffee, they just drink it.",
        "Unpopular opinion: water temperature matters more than the brand.",
        "Things nobody tells you about instant coffee, a thread:",
    ],
    "linkedin_post": [
        "The first jar we sold taught me more than any plan did.",
        "We almost launched with the wrong label. Here's what changed it.",
        "Building a coffee brand from India: one lesson from this week.",
    ],
    "facebook_post": [
        "Who makes the coffee in your house, and who complains about it?",
        "Morning question: how many spoons do you actually use?",
    ],
    "blog_post": [
        "Is instant coffee 'real' coffee? What the label tells you",
        "How to make instant coffee taste like a café cup (tested at home)",
    ],
}

# Founder-confirmed campaign facts. The deadline is the gift-pack line only,
# and only through 2 Nov 2026. Other urgency stays a hard fail.
_CONFIRMED_CODES = ("FREESHIP", "BUNDLE10")
_CONFIRMED_ORDER_BY = re.compile(r"\border by 2 nov\b", re.I)
_ANY_ORDER_BY = re.compile(r"\border\s+by\b", re.I)
_ORDER_BY_UNTIL = _dt.date(2026, 11, 2)

# Fabrication screen: virality must never come from invented urgency, social proof, metrics or health.
_DISHONEST = [
    (re.compile(r"\b(only \d+ (left|jars?|units?)|last chance|ends (tonight|today|in \d+)|hurry|selling out|sold out fast|limited stock|few hours left)\b", re.I), "fabricated urgency"),
    (re.compile(r"\b(\d[\d,.]*\s*(k|lakh|million)?\+?\s*(happy )?(customers|reviews|buyers|followers|orders)|5[- ]star reviews?|rated #?1|india'?s #?1|best[- ]selling|bestseller|\d(\.\d)? ?(stars?|★))\b", re.I), "fabricated reviews/metrics"),
    (re.compile(r"\b(went viral|million views|everyone is switching|\d+% of (people|indians|customers))\b", re.I), "fabricated metrics"),
    (re.compile(r"\b(boosts? (immunity|metabolism)|burns? fat|weight loss|detox|cures? \w+|prevents? (cancer|disease|diabetes|heart)|lowers? (blood|sugar|cholesterol)|anti[- ]?oxidant[- ]rich|healthy heart|doctor[- ]recommended)\b", re.I), "health claim"),
    (re.compile(r"100\s*%", re.I), "'100%' is not allowed (FSSAI)"),
]


def format_for(label: str) -> str:
    return LABEL_FORMAT.get(label, label)


def _text(piece) -> str:
    try:
        return json.dumps(piece, ensure_ascii=False)
    except Exception:
        return str(piece)


def _piece_day(piece: dict) -> _dt.date:
    for key in ("date", "on", "asset_date", "on_date"):
        raw = str((piece or {}).get(key) or "").strip()[:10]
        try:
            return _dt.date.fromisoformat(raw)
        except ValueError:
            continue
    return _dt.date.today()


def _without_confirmed(text: str, day: _dt.date) -> str:
    """Drop founder-confirmed codes, and the 2 Nov line while it is still open."""
    cleaned = text
    for code in _CONFIRMED_CODES:
        cleaned = re.sub(rf"\buse\s+code\s+{code}\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(rf"\b{code}\b", " ", cleaned, flags=re.I)
    if day <= _ORDER_BY_UNTIL:
        cleaned = _CONFIRMED_ORDER_BY.sub(" ", cleaned)
    return cleaned


def honesty_issues(piece: dict) -> list[str]:
    """Deterministic screen; any hit is a hard fail no matter how 'viral' the piece is."""
    raw = _text({k: v for k, v in (piece or {}).items()
                 if not str(k).startswith(("editorial", "viral", "_")) and k not in ("fallback_ladder",)})
    text = _without_confirmed(raw, _piece_day(piece or {}))
    issues = {why for rx, why in _DISHONEST if rx.search(text)}
    if _ANY_ORDER_BY.search(text):
        issues.add("fabricated urgency")
    return sorted(issues)


def build_prompt(label: str, piece: dict) -> str:
    fmt = format_for(label)
    dims = "\n".join(f"- {k}: {v}" for k, v in DIMENSIONS.items())
    body = _text({k: v for k, v in (piece or {}).items()
                  if not str(k).startswith(("editorial", "viral", "_"))})[:6000]
    return (
        "You are a strict short-form growth editor for Purity Beans (Instagram @purepantryprovisions, shop p3online.in), "
        "an Indian instant-coffee brand. Score the VIRAL POTENTIAL of this piece honestly; most first drafts score 5-7.\n"
        f"Platform/format: {label} ({fmt}). FORMAT RULES: {FORMAT_RULES.get(fmt, 'platform-native pacing')}\n"
        f"Score each dimension 0-10:\n{dims}\n"
        "Honesty overrides virality: never reward or suggest fake urgency, invented reviews/metrics/follower counts, "
        "health claims, '100%', anti-chicory wording, bean varieties for Bold, or prices not already in the piece.\n"
        f"PIECE JSON:\n{body}\n\n"
        'Return ONLY JSON: {"scores": {<each dimension>: number}, "overall": number, '
        '"weakest": [dimension names], "feedback": "concrete fixes", "better_hook": "one stronger honest opening line"}'
    )


def _num(v):
    try:
        return max(0.0, min(10.0, float(v)))
    except (TypeError, ValueError):
        return None


def normalize(raw: dict) -> dict:
    """overall = the LOWER of the model's overall and the dimension mean (no inflation)."""
    raw = raw if isinstance(raw, dict) else {}
    scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
    dims = {k: _num(scores.get(k)) for k in DIMENSIONS}
    missing = [k for k, v in dims.items() if v is None]
    if missing:
        raise ValueError(f"viral score missing dimensions: {missing}")
    mean = sum(dims.values()) / len(dims)
    model_overall = _num(raw.get("overall"))
    overall = round(min(mean, model_overall) if model_overall is not None else mean, 2)
    return {"scores": dims, "overall": overall,
            "weakest": [w for w in (raw.get("weakest") or []) if w in DIMENSIONS] or
                       sorted(dims, key=dims.get)[:2],
            "feedback": str(raw.get("feedback") or "")[:600],
            "better_hook": str(raw.get("better_hook") or "")[:200]}


def enabled() -> bool:
    return os.getenv("VIRAL_GATE", "1").strip().lower() not in ("0", "false", "off")


def evaluate(label: str, piece: dict, *, call=None) -> dict:
    """Returns {"passed", "overall", "scores", "feedback", "honesty", ...}. Fails closed."""
    issues = honesty_issues(piece)
    if issues:
        return {"passed": False, "overall": 0.0, "scores": {}, "honesty": issues, "pass_mark": PASS_MARK,
                "feedback": "HONESTY: remove " + "; ".join(issues) + ". Earn attention with a true, specific hook instead."}
    if call is None:
        from content_generator.providers.llm_router import call as _call
        call = _call
    try:
        res = normalize(call(build_prompt(label, piece), label=f"viral_{label}", max_tokens=700))
    except Exception as e:
        logger.warning("[viral] %s scoring failed: %s", label, e)
        return {"passed": False, "overall": None, "scores": {}, "honesty": [], "pass_mark": PASS_MARK,
                "error": f"viral_scoring_failed: {type(e).__name__}", "feedback": ""}
    res.update(passed=res["overall"] >= PASS_MARK, honesty=[], pass_mark=PASS_MARK)
    return res


def feedback_for(label: str, result: dict, attempt: int = 0) -> str:
    """Regeneration instruction: the judge's notes + a DIFFERENT proven hook template."""
    fmt = format_for(label)
    templates = HOOK_TEMPLATES.get(fmt) or HOOK_TEMPLATES["instagram_post"]
    tmpl = templates[int(attempt) % len(templates)]
    weak = ", ".join(result.get("weakest") or [])
    parts = [f"viral: score {result.get('overall')} < {PASS_MARK} (weakest: {weak or 'n/a'}).",
             str(result.get("feedback") or "").strip()]
    if result.get("better_hook"):
        parts.append(f"Suggested hook: {result['better_hook']}")
    parts.append(f"Use a DIFFERENT hook and angle from the last draft, e.g. this template: \"{tmpl}\". "
                 f"Format rules: {FORMAT_RULES.get(fmt, '')}. Add a comment trigger and a clear "
                 "'Follow @purepantryprovisions' reason. Never invent urgency, reviews, metrics, health "
                 "claims, '100%', or prices; never knock chicory.")
    return " ".join(p for p in parts if p)


def hook_block(label: str) -> str:
    fmt = format_for(label)
    t = HOOK_TEMPLATES.get(fmt)
    if not t:
        return ""
    return ("VIRAL HOOK TEMPLATES (pick one, fill only with verified facts, never invented numbers): "
            + " | ".join(t) + f"\nFORMAT MECHANICS: {FORMAT_RULES.get(fmt, '')}. "
            "Include a curiosity gap that pays off, a comment trigger (question or this-or-that), a "
            "save/share reason, and a clear follow CTA for @purepantryprovisions.")
