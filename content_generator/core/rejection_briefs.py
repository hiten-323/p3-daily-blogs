"""Turn a specific gate rejection into a targeted regeneration brief.

The gates themselves are never relaxed here. This only decides HOW the next
attempt is regenerated so it addresses the reason the last one failed.
"""
from __future__ import annotations

import re

VALUE_FORMATS = (
    "a brew tip (exact water temperature, ratio or technique for a better instant cup)",
    "a myth-buster (one common coffee myth, debunked with a verifiable fact)",
    "a ritual (a calm, relatable daily coffee moment the viewer will recognise)",
    "freeze-dried vs agglomerated instant coffee (how each is made and why it changes taste)",
)

STOCK_RE = re.compile(r"\b(out[ -]of[ -]stock|in[ -]stock|back in stock|restock\w*|wait[- ]?list|sold out|"
                      r"stock (status|levels?)|currently (un)?available|availability)\b", re.I)

_PROMO = re.compile(r"objective compliance|promotional|commercial|sales-led|portfolio gate|80/20 cap", re.I)
_PAYOFF = re.compile(r"payoff gate|hook decomposition|promise is never settled|hook promises", re.I)
_DRY = re.compile(r"dry|inventory|stock|catalog|listing|spec sheet", re.I)

VIDEO = ("reel_1", "reel_2", "growth_reel", "yt_short")


def category(label: str, reason: str) -> str:
    r = str(reason or "")
    if label == "blog_post" and (_DRY.search(r) or STOCK_RE.search(r)):
        return "blog_dry"
    if _PROMO.search(r):
        return "promotional"
    if _PAYOFF.search(r):
        return "payoff"
    return ""


def value_format(attempt: int, day: int = 0) -> str:
    return VALUE_FORMATS[(int(attempt) + int(day)) % len(VALUE_FORMATS)]


def brief(label: str, reason: str, attempt: int = 0, day: int = 0) -> tuple[str, bool]:
    """Return (feedback brief, regenerate_from_scratch)."""
    cat = category(label, reason)
    if cat == "promotional":
        fmt = value_format(attempt, day)
        return (
            f"REJECTED AS SALES-LED ({reason}). Build a brand-new NON-SALES value piece from scratch: {fmt}. "
            "Every frame/slide must teach, debunk or show a ritual; no prices, no offers, no 'buy', 'shop', "
            "'order' or discount language in the body. The product appears ONLY as a soft end card "
            "(jar + brand name + 'Follow @purepantryprovisions for more'). The objective is FOLLOW/DISCOVERY, "
            "not CONVERSION. Keep every brand and claim rule.",
            True,
        )
    if cat == "payoff":
        return (
            f"HOOK/PAYOFF MISMATCH ({reason}). The hook makes a promise the body never settles. Either rewrite "
            "the hook so it promises exactly what the body delivers, or rewrite the body so it explicitly delivers "
            "what the hook promises (name the answer on screen and in the spoken line before the CTA). If the hook "
            "says 'alternative', the body must name the alternative and show why. The on-screen text, spoken line "
            "and caption hooks must each do different work but point at the same payoff.",
            label in VIDEO and attempt >= 2,
        )
    if cat == "blog_dry":
        angle = ("a story angle: open with one real-feeling morning-coffee scene and build to what makes a cleaner cup"
                 if attempt % 2 == 0 else
                 "a practical guide angle: a step-by-step 'how to choose and brew better instant coffee' with headed steps")
        return (
            f"BLOG TOO DRY / INVENTORY-LIKE ({reason[:200]}). Rewrite from scratch with {angle}. Write for a reader, "
            "not a catalogue: no product-list sections, no spec-sheet tone. NEVER mention stock status, availability, "
            "waitlists, restocks or 'out of stock'. Mention products only where they help the story or guide.",
            True,
        )
    return reason, False


_COPY_KEYS = ("title", "introduction", "body", "conclusion", "caption", "meta_description", "excerpt",
              "sections", "faq", "text", "hook", "cta")


def stock_mentions(piece: dict) -> list[str]:
    """Stock-status phrases in the publishable copy only (not scores/metadata)."""
    import json
    if not isinstance(piece, dict):
        return []
    text = " ".join(json.dumps(piece.get(k), ensure_ascii=False) for k in _COPY_KEYS if piece.get(k))
    return sorted({m.group(0).lower() for m in STOCK_RE.finditer(text)})
