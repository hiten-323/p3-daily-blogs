"""Shared hook, tension-arc, lesson, and follow-growth rules for Shorts and reels.

The 8.0 editorial and viral gates are unchanged. This only tells the next
attempt what the judge already rejected.
"""
from __future__ import annotations

ARC_RULES = """HOOK AND ARC (required):
- Hook: specific, surprising, and awe-inspiring. Name a concrete object, clock time, or contradiction a coffee drinker has actually seen.
- Banned openers: "Most people never", "Most people don't", "Did you know", "You won't believe", "Stop scrolling".
- Scene arc is tension then payoff, in this order: a problem with stakes, tension rising, an unexpected turn, then the payoff that settles the hook BEFORE the CTA.
- A product dump with no tension fails. Do not repeat a hook used in the last 7 days."""

VALUE_FIRST = """FOLLOW-GROWTH (value first):
- Teach one specific craft point, myth, or ritual before any brand mention.
- No shop, price, offer, discount, buy, or order language in the body.
- The product appears only as a soft end card: jar name, one true fact, then Follow @purepantryprovisions.
- A sales caption with a follow line tacked on fails the follow-growth slot."""

_VALUE_LABELS = ("instagram_post", "carousel", "growth_reel")
_ARC_LABELS = ("yt_short", "reel_1", "reel_2", "growth_reel", "instagram_post", "carousel")


def craft_block(label: str) -> str:
    """Arc, week-long hook ban, and obstacle lessons for this asset."""
    parts: list[str] = []
    if label in _ARC_LABELS:
        parts.append(ARC_RULES)
    if label in _VALUE_LABELS:
        parts.append(VALUE_FIRST)
    try:
        from content_generator.analytics.hook_selector import week_hook_ban
        parts.append(week_hook_ban())
    except Exception:
        parts.append("HOOK BAN: do not repeat or lightly rephrase a hook used in the last 7 days.")
    try:
        from content_generator.core.obstacle_lessons import prompt_block
        extra = prompt_block(label)
        if extra:
            parts.append(extra)
    except Exception:
        pass
    return "\n\n".join(part for part in parts if part)
