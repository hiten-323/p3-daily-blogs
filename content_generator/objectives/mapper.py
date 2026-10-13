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
        "primary_cta":    "Follow for the line on the jar",
        "success_metric": "follows",
        "target":         250,
    },
    "Consumer Purchase": {
        "primary_cta":    "Shop the jar at p3online.in",
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
        "primary_cta":    "Follow for the line on the jar",
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
        "primary_cta":    "Shop the jar at p3online.in",
        "success_metric": "link_clicks",
        "target":         50,
    },
}


def assign_objective(content_type: str, day: int, text: str = "") -> dict:
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
            cta = mapped["primary_cta"]
            if f_name == "FOLLOW":
                cta = _follow_cta(day, content_type, text)
            return {
                "funnel_objective": f_name,
                "objective":        mapped["objective"],
                "primary_cta":      cta,
                "success_metric":   mapped["success_metric"],
                "target":           mapped["target"],
            }
    except Exception:
        pass

    rotation = _ROTATION.get(content_type, ["Brand Awareness"])
    objective: ObjectiveType = rotation[day % len(rotation)]
    kpis = dict(_KPI.get(objective, {}))
    if objective == "Follower Growth":
        kpis["primary_cta"] = _follow_cta(day, content_type, text)
    return {
        "funnel_objective": "DISCOVERY" if objective in ("Engagement Growth", "Brand Awareness") else "CONVERSION",
        "objective":        objective,
        "primary_cta":      kpis.get("primary_cta", ""),
        "success_metric":   kpis.get("success_metric", ""),
        "target":           kpis.get("target", 0),
    }


def _follow_cta(day: int, content_type: str = "", text: str = "") -> str:
    """Chicory in the featured jar or in this copy gets the 70/30 line."""
    from content_generator.core.product_truth import follow_cta_for
    from content_generator.rotation import PRODUCTS, pick
    variant = "alt" if str(content_type) == "reel_2" else "primary"
    return follow_cta_for(str(pick(PRODUCTS, int(day))), text=text, variant=variant)


def assign_all(content: dict, day: int) -> dict:
    """
    Stamp business and funnel objectives onto every content piece in the output dict.
    Non-destructive: existing keys are preserved, objective keys are added.
    """
    from content_generator.core.product_truth import piece_copy_text, repair_content

    content = repair_content(content) if isinstance(content, dict) else content
    out = dict(content)

    # Flat content types across all platforms
    all_flat = (
        "instagram_post", "carousel", "linkedin_post", "blog_post",
        "stories", "yt_short", "facebook_post", "threads_post", "growth_reel"
    )
    for key in all_flat:
        if key in out and isinstance(out[key], dict):
            out[key] = {**out[key], **assign_objective(key, day, piece_copy_text(out[key]))}

    # Reels array
    if "reels" in out and isinstance(out["reels"], list):
        reel_keys = ["reel_1", "reel_2"]
        out["reels"] = [
            {**reel, **assign_objective(reel_keys[i], day, piece_copy_text(reel))}
            if i < len(reel_keys) else reel
            for i, reel in enumerate(out["reels"])
        ]

    _separate_reel_ctas(out, day)
    _drop_roasted_root_ctas(out, day)
    return out


def _norm_cta(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _separate_reel_ctas(content: dict, day: int) -> None:
    """reel_2 must not ship the same call to action as reel_1."""
    reels = content.get("reels")
    if not isinstance(reels, list) or len(reels) < 2:
        return
    first, second = reels[0], reels[1]
    if not isinstance(first, dict) or not isinstance(second, dict):
        return
    if not _norm_cta(second.get("cta")) or _norm_cta(second.get("cta")) != _norm_cta(first.get("cta")):
        return
    from content_generator.core.product_truth import piece_copy_text
    second["cta"] = _follow_cta(day, "reel_2", piece_copy_text(second))
    if _norm_cta(second.get("primary_cta")) == _norm_cta(first.get("primary_cta")):
        second["primary_cta"] = second["cta"]


def _drop_roasted_root_ctas(content: dict, day: int) -> None:
    """An asset that names Ultra Blend cannot keep an anti-chicory follow line."""
    from content_generator.core.product_truth import chicory_in_scope, piece_copy_text

    def clean(piece: dict, content_type: str) -> None:
        if not isinstance(piece, dict):
            return
        text = piece_copy_text(piece)
        blob = f"{piece.get('cta') or ''} {piece.get('primary_cta') or ''}"
        if "roasted root" not in blob.lower():
            return
        if not chicory_in_scope(text, str(piece.get("featured_product") or piece.get("product") or "")):
            return
        fresh = _follow_cta(day, content_type, text)
        if "roasted root" in str(piece.get("cta") or "").lower():
            piece["cta"] = fresh
        if "roasted root" in str(piece.get("primary_cta") or "").lower():
            piece["primary_cta"] = fresh

    for key in (
        "instagram_post", "carousel", "linkedin_post", "blog_post",
        "stories", "yt_short", "facebook_post", "threads_post", "growth_reel",
    ):
        clean(content.get(key), key)
    for index, reel in enumerate(content.get("reels") or []):
        clean(reel, "reel_1" if index == 0 else "reel_2")
