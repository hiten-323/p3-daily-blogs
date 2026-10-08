"""
Business objective mapper.

Every content piece is assigned a primary business objective so the engine
optimises for REVENUE, not just vanity metrics.

Objectives rotate deterministically by day so the weekly content mix
always drives all revenue levers — not just brand awareness.

Objectives:
  Consumer Purchase     — drive direct buy at p3online.in
  Brand Awareness       — reach new audiences, grow followers
  Distributor Acquisition — attract FMCG distribution partners
  Retailer Lead Gen     — attract retail shelf placement
  Website Traffic       — drive blog / product page visits
  Engagement Growth     — shares, saves, comments for algorithmic reach
"""
from typing import Literal

ObjectiveType = Literal[
    "Consumer Purchase",
    "Brand Awareness",
    "Distributor Acquisition",
    "Retailer Lead Gen",
    "Website Traffic",
    "Engagement Growth",
    "Follower Growth",
]

# For each content type, fallback objectives rotate in priority order (index = day % len)
_ROTATION: dict[str, list[ObjectiveType]] = {
    "reel_1":         ["Follower Growth",         "Engagement Growth",       "Brand Awareness"],
    "reel_2":         ["Brand Awareness",         "Engagement Growth",       "Consumer Purchase"],
    "growth_reel":    ["Follower Growth",         "Engagement Growth"],
    "instagram_post": ["Engagement Growth",       "Follower Growth",         "Brand Awareness"],
    "carousel":       ["Brand Awareness",         "Follower Growth",         "Website Traffic"],
    "linkedin_post":  ["Brand Awareness",         "Distributor Acquisition", "Retailer Lead Gen"],
    "blog_post":      ["Website Traffic",         "Brand Awareness",         "Consumer Purchase"],
    "stories":        ["Engagement Growth",       "Consumer Purchase",       "Brand Awareness"],
    "yt_short":       ["Follower Growth",         "Engagement Growth",       "Brand Awareness"],
    "facebook_post":  ["Engagement Growth",       "Brand Awareness"],
    "threads_post":   ["Engagement Growth",       "Follower Growth"],
}

# KPI targets and CTA copy per objective
_KPI: dict[str, dict] = {
    "Follower Growth": {
        "primary_cta":    "Follow @puritybeans so you never drink roasted root again",
        "success_metric": "follows",
        "target":         250,
    },
    "Consumer Purchase": {
        "primary_cta":    "Buy pure 100% Arabica at p3online.in — Rs 18 per cup",
        "success_metric": "link_clicks",
        "target":         500,
    },
    "Brand Awareness": {
        "primary_cta":    "Save this guide before your next grocery run",
        "success_metric": "saves",
        "target":         300,
    },
    "Distributor Acquisition": {
        "primary_cta":    "DM us for distribution partnership",
        "success_metric": "dm_inquiries",
        "target":         10,
    },
    "Retailer Lead Gen": {
        "primary_cta":    "WhatsApp for bulk / retail pricing",
        "success_metric": "whatsapp_clicks",
        "target":         25,
    },
    "Website Traffic": {
        "primary_cta":    "Full article at p3online.in",
        "success_metric": "link_clicks",
        "target":         300,
    },
    "Engagement Growth": {
        "primary_cta":    "Send this to someone who drinks instant coffee",
        "success_metric": "shares",
        "target":         400,
    },
}

_FUNNEL_MAP = {
    "FOLLOW": {
        "objective":      "Follower Growth",
        "primary_cta":    "Follow @puritybeans so you never drink roasted root again",
        "success_metric": "follows",
        "target":         250,
    },
    "DISCOVERY": {
        "objective":      "Engagement Growth",
        "primary_cta":    "Send this to someone who drinks instant coffee",
        "success_metric": "shares",
        "target":         500,
    },
    "AUTHORITY": {
        "objective":      "Brand Awareness",
        "primary_cta":    "Save this guide before your next grocery run",
        "success_metric": "saves",
        "target":         300,
    },
    "COMMUNITY": {
        "objective":      "Engagement Growth",
        "primary_cta":    "Which one would you choose? Comment below",
        "success_metric": "comments",
        "target":         150,
    },
    "CONVERSION": {
        "objective":      "Consumer Purchase",
        "primary_cta":    "Buy pure 100% Arabica at p3online.in — Rs 18 per cup",
        "success_metric": "link_clicks",
        "target":         50,
    },
}


def assign_objective(content_type: str, day: int) -> dict:
    """
    Return stage-aware objective metadata for one content piece.

    Integrates with Growth Director to ensure follower growth and viral
    discovery are prioritized in early stages (Million Follower Mode).
    """
    try:
        from content_generator.core.growth_director import get_todays_objectives
        objs = get_todays_objectives(day)
        funnel_pair = objs.get(content_type)
        if funnel_pair and funnel_pair[0] in _FUNNEL_MAP:
            f_name = funnel_pair[0]
            mapped = _FUNNEL_MAP[f_name]
            return {
                "funnel_objective": f_name,
                "objective":        mapped["objective"],
                "primary_cta":      mapped["primary_cta"],
                "success_metric":   mapped["success_metric"],
                "target":           mapped["target"],
            }
    except Exception:
        pass

    rotation = _ROTATION.get(content_type, ["Brand Awareness"])
    objective: ObjectiveType = rotation[day % len(rotation)]
    kpis = _KPI.get(objective, {})
    return {
        "funnel_objective": "DISCOVERY" if objective in ("Engagement Growth", "Brand Awareness") else "CONVERSION",
        "objective":        objective,
        "primary_cta":      kpis.get("primary_cta", ""),
        "success_metric":   kpis.get("success_metric", ""),
        "target":           kpis.get("target", 0),
    }


def assign_all(content: dict, day: int) -> dict:
    """
    Stamp business and funnel objectives onto every content piece in the output dict.
    Non-destructive: existing keys are preserved, objective keys are added.
    """
    out = dict(content)

    # Flat content types across all platforms
    all_flat = (
        "instagram_post", "carousel", "linkedin_post", "blog_post",
        "stories", "yt_short", "facebook_post", "threads_post", "growth_reel"
    )
    for key in all_flat:
        if key in out and isinstance(out[key], dict):
            out[key] = {**out[key], **assign_objective(key, day)}

    # Reels array
    if "reels" in out and isinstance(out["reels"], list):
        reel_keys = ["reel_1", "reel_2"]
        out["reels"] = [
            {**reel, **assign_objective(reel_keys[i], day)}
            if i < len(reel_keys) else reel
            for i, reel in enumerate(out["reels"])
        ]

    return out
