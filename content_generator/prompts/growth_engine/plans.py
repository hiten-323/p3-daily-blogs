"""Declared objective, audience, angle, and follow promise for one asset."""
from __future__ import annotations

OBJECTIVES = (
    "reach new relevant coffee drinkers",
    "earn qualified followers",
    "drive product-page visits/purchases",
    "B2B inquiries (retailer, cafe, office, wholesale, distributor)",
    "repeat purchase/recall",
)

BANNED_OPENERS = (
    "hello everyone",
    "are you a coffee lover",
    "introducing our amazing product",
    "your morning just got better",
    "you won't believe this",
    "you wont believe this",
)

# One job per platform. Angles and follow promises do not repeat each other.
_PLANS = {
    "reel": {
        "primary_objective": OBJECTIVES[0],
        "secondary_objective": OBJECTIVES[1],
        "audience": "people who buy instant coffee and have never turned the jar around",
        "angle": "visual discovery of one label fact",
        "follow_promise": "Follow for the next thing the label is hiding.",
        "rationale": "A Reel is discovery. The first frame has to stop a stranger.",
    },
    "carousel": {
        "primary_objective": OBJECTIVES[2],
        "secondary_objective": OBJECTIVES[1],
        "audience": "buyers comparing jars in a grocery aisle or a comment section",
        "angle": "a saveable framework for one buying decision",
        "follow_promise": "Follow for one buying check you can save.",
        "rationale": "A carousel is the reference someone screenshots.",
    },
    "ig_single": {
        "primary_objective": OBJECTIVES[4],
        "secondary_objective": OBJECTIVES[2],
        "audience": "people who already know the jar and need one reason to remember it",
        "angle": "one sensory moment with the real jar",
        "follow_promise": "Follow for the jar that matches how you actually drink.",
        "rationale": "A single image is recall, not a second copy of the Reel.",
    },
    "stories": {
        "primary_objective": OBJECTIVES[2],
        "secondary_objective": OBJECTIVES[1],
        "audience": "people already watching who will answer one real question",
        "angle": "a connected sequence from a hook to one next step",
        "follow_promise": "Follow for a short answer and the honest next step.",
        "rationale": "Stories are a sequence, not four unrelated posters.",
    },
    "facebook": {
        "primary_objective": OBJECTIVES[0],
        "secondary_objective": OBJECTIVES[2],
        "audience": "households who talk about the morning cup with someone else",
        "angle": "a situation the reader has already had this week",
        "follow_promise": "Follow for the coffee conversation without the pitch.",
        "rationale": "Facebook is shared in a conversation, so the opener is a situation.",
    },
    "threads": {
        "primary_objective": OBJECTIVES[1],
        "secondary_objective": OBJECTIVES[0],
        "audience": "people who will reply to one precise coffee question",
        "angle": "one honest question, not a caption pasted short",
        "follow_promise": "Follow for one honest coffee question a day.",
        "rationale": "Threads earns a reply. It does not carry the Instagram caption.",
    },
    "linkedin": {
        "primary_objective": OBJECTIVES[3],
        "secondary_objective": OBJECTIVES[1],
        "audience": "cafe owners, office buyers, retailers, and distributors",
        "angle": "a business lesson from how the label is written",
        "follow_promise": "Follow for how a coffee brand is actually built.",
        "rationale": "LinkedIn is a B2B conversation with a named next step.",
    },
    "yt_short": {
        "primary_objective": OBJECTIVES[0],
        "secondary_objective": OBJECTIVES[1],
        "audience": "viewers who will watch one complete answer with the sound off",
        "angle": "a standalone payoff that ends without needing another post",
        "follow_promise": "Subscribe for the next short payoff, and follow for label checks.",
        "rationale": "A Short has to pay off on its own, then ask for the next one.",
    },
    "blog": {
        "primary_objective": OBJECTIVES[2],
        "secondary_objective": OBJECTIVES[4],
        "audience": "someone who searched a specific coffee question",
        "angle": "the full search answer, with the catalog difference stated once",
        "follow_promise": "Follow for the short version after the long answer.",
        "rationale": "The blog answers the query. It is not a caption with headings.",
    },
    "whatsapp": {
        "primary_objective": OBJECTIVES[3],
        "secondary_objective": None,
        "audience": "a verified lead who asked about wholesale, a cafe, or an office",
        "angle": "why this note is relevant to that lead, then one next step",
        "follow_promise": "One relevant next step. No false familiarity.",
        "rationale": "Outreach only happens when a real lead and an opt-in exist.",
    },
}

LABEL_PLATFORM = {
    "reel_1": "reel",
    "reel_2": "reel",
    "growth_reel": "reel",
    "carousel": "carousel",
    "instagram_post": "ig_single",
    "stories": "stories",
    "facebook_post": "facebook",
    "threads_post": "threads",
    "linkedin_post": "linkedin",
    "yt_short": "yt_short",
    "blog_post": "blog",
    "whatsapp": "whatsapp",
}


def asset_plan(platform: str, day: int = 0, sku: str = "", *, variant: int = 0) -> dict:
    """The code owns the plan. A model may not swap in a second objective."""
    base = dict(_PLANS[platform])
    if variant:
        base["angle"] = f"{base['angle']} — variant {variant + 1}, different hook"
        base["follow_promise"] = base["follow_promise"].rstrip(".") + f" (part {variant + 1})."
    base["platform"] = platform
    base["sku"] = sku
    base["day"] = int(day or 0)
    if base["secondary_objective"] == base["primary_objective"]:
        base["secondary_objective"] = None
    return base
