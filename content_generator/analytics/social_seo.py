"""
Social Search SEO — Instagram/YouTube are search engines now (IG ~6.5B
searches/day). People type full QUESTIONS, and the platform matches them
against your caption, on-screen text, and spoken words (audio transcript).

The engine already uses hashtags; this adds the missing layer: seed each day's
content with the real questions Purity Beans' avatar types into search, so the
content becomes the ANSWER the algorithm surfaces before intent even forms.

Sources: Neil Patel (Social Media SEO 2026), heyDominik (hooks).
"""
from __future__ import annotations

# Real long-tail questions an Indian coffee buyer types into IG/YouTube/TikTok
# search. Rotated daily; the day's question drives the caption first line +
# on-screen text + a spoken line so all three match how people actually search.
SEARCH_QUESTIONS = [
    "which instant coffee has no chicory",
    "which instant coffee in India lists no chicory",
    "how to check if my coffee has chicory",
    "is instant coffee actually coffee",
    "how to make cafe like coffee at home",
    "freeze dried vs agglomerated coffee which is better",
    "how to tell if instant coffee is 100% coffee",
    "how to see if chicory is listed on Indian instant coffee",
    "what to stock in an office coffee pantry in India",
    "how to make strong black coffee at home",
    "premium instant coffee brands in India",
    "how to read a coffee label",
    "why does my instant coffee taste bitter",
    "healthiest instant coffee in India",
    "best coffee to gift in India",
    "how to make coffee without a machine",
    "what is 100 percent coffee",
    "cheapest way to drink good coffee daily",
    "how to store instant coffee to keep it fresh",
    "which coffee has the most caffeine India",
]


def get_todays_search_question(day: int) -> str:
    return SEARCH_QUESTIONS[day % len(SEARCH_QUESTIONS)]


def social_seo_directive(day: int) -> str:
    """Prompt-injectable block: make today's content answer a real search query."""
    q = get_todays_search_question(day)
    return (
        "SOCIAL SEARCH SEO (Instagram is a search engine — match how people type):\n"
        f"- TODAY'S TARGET SEARCH QUERY: \"{q}\"\n"
        "- Put a natural-language version of this query in the FIRST line of the "
        "caption, in the on-screen hook text, AND say it out loud in the reel "
        "(the platform reads all three).\n"
        "- Answer it FAST — deliver the payoff in the first few seconds (people "
        "search a question and want the answer, not a tease).\n"
        "- Phrase like a real person searching (full question), not keyword soup.\n"
        "- SAFE ZONE: keep on-screen text in the top ~75% of the frame — the "
        "bottom and right edges are covered by Instagram's UI (caption, buttons)."
    )
