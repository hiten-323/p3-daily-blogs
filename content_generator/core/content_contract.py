"""
The Growth Director output contract + the north-star shareability gate.

NORTH STAR
  "Every piece of content must be valuable enough that a viewer would willingly
   send it to one friend. If it is not worth sharing privately, it is not worth
   publishing."

Two things live here:

1. shareability() — a deterministic gate against that north star. It is a
   HEURISTIC, not a prediction, and says so. It asks the questions the spec
   asks: is this specific, is it surprising, could it belong to any coffee
   brand, does it teach something a person could act on.

2. build_contract() — the 14-field output the spec requires per idea.

On the prediction fields (viral score, confidence, expected follows/shares/
saves): this account has no measured posts, so there is nothing to predict
from. Emitting "expected follows: 47" would be an invented statistic, which
the spec's own HONESTY POLICY forbids. Those fields therefore return None with
confidence 0.0 and an explicit basis string, and begin returning real numbers
automatically once viral_scorer has an account baseline. Absence is honest;
a confident-looking guess is not.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# Below this, the piece fails the north star and should not publish.
SHAREABILITY_THRESHOLD = 55.0

_GENERIC = (
    "coffee lovers", "start your day", "perfect cup", "rich aroma",
    "premium quality", "best coffee", "coffee time", "morning fuel",
    "taste the difference", "brewed to perfection", "your daily dose",
)
_SPECIFIC = (
    "chicory", "label", "ingredient", "gram", "seconds", "minutes", "rupee",
    "price", "percent", "temperature", "water", "spoon", "jar", "freeze",
    "roast", "arabica", "robusta", "instant", "filter",
)
_SURPRISE = (
    "actually", "isn't", "is not", "wrong", "myth", "nobody", "most people",
    "truth", "hidden", "check", "test", "difference", "mistake", "why",
)
_ACTIONABLE = (
    "check", "read", "try", "test", "look for", "next time", "swap",
    "stop", "start", "compare", "ask",
)


def shareability(piece: dict) -> dict:
    """
    Would a viewer send this to one friend? 0-100 with named reasons.

    Deterministic heuristic over the piece's own copy — no model call, no
    network, same answer every run.
    """
    text_parts = [str(piece.get(k) or "") for k in ("hook", "hook_text", "headline", "title", "caption", "body", "text")]
    
    # Also extract copy from scenes list if present (e.g. for yt_short or reels)
    if "scenes" in piece and isinstance(piece["scenes"], list):
        for s in piece["scenes"]:
            if isinstance(s, dict):
                text_parts.append(str(s.get("on_screen") or ""))
                text_parts.append(str(s.get("spoken") or ""))
                
    # Also extract from script list if present
    if "script" in piece and isinstance(piece["script"], list):
        for s in piece["script"]:
            if isinstance(s, dict):
                text_parts.append(str(s.get("on_screen") or ""))
                text_parts.append(str(s.get("voiceover") or ""))
                text_parts.append(str(s.get("spoken") or ""))

    text = " ".join(text_parts).lower()
    if not text.strip():
        return {"score": 0.0, "passes": False, "reasons": ["no copy to judge"]}

    score = 45.0
    reasons: list[str] = []

    specific = sum(1 for w in _SPECIFIC if w in text)
    if specific:
        score += min(20, specific * 7)
        reasons.append(f"specific and checkable ({specific} concrete detail(s))")
    else:
        reasons.append("no concrete detail — nothing for a friend to verify")

    surprise = sum(1 for w in _SURPRISE if w in text)
    if surprise:
        score += min(18, surprise * 6)
        reasons.append("carries a surprise or contrarian turn")

    actionable = sum(1 for w in _ACTIONABLE if w in text)
    if actionable:
        score += min(12, actionable * 6)
        reasons.append("gives the viewer something to do")

    generic = [g for g in _GENERIC if g in text]
    if generic:
        score -= min(35, len(generic) * 18)
        reasons.append(f"generic phrasing — could belong to any coffee brand: {generic[:2]}")

    # The spec's own test: would this be worth sending privately? Pure product
    # description never is.
    try:
        from content_generator.core.content_balance import classify_asset
        if classify_asset(piece) == "product" and specific < 2:
            score -= 15
            reasons.append("product-led with little to teach")
    except Exception as e:
        logger.debug("[contract] balance classify unavailable: %s", e)

    score = max(0.0, min(100.0, score))
    return {"score": round(score, 1), "passes": score >= SHAREABILITY_THRESHOLD,
            "reasons": reasons, "basis": "heuristic — not a performance prediction"}


def _predictions() -> dict:
    """
    Expected follows/shares/saves and a viral score.

    Returns nulls with confidence 0.0 until the account has enough measured
    history for viral_scorer to build a baseline. See the module docstring:
    a number here with no data behind it is a fabricated statistic.
    """
    try:
        from content_generator.analytics.viral_scorer import (
            get_account_baseline, MIN_POSTS_FOR_BASELINE,
        )
        baseline = get_account_baseline()
    except Exception as e:
        logger.debug("[contract] viral scorer unavailable: %s", e)
        baseline, MIN_POSTS_FOR_BASELINE = None, 5

    if baseline is None:
        return {
            "viral_score": None,
            "confidence": 0.0,
            "expected_follows": None,
            "expected_shares": None,
            "expected_saves": None,
            "prediction_basis": (
                f"no account baseline yet — needs {MIN_POSTS_FOR_BASELINE} measured "
                f"posts. Any number here would be invented."),
        }

    # With a baseline, the honest prior for a new post is the account's own
    # recent median — stated as a typical outcome, not a forecast for this piece.
    return {
        "viral_score": None,
        "confidence": 0.25,
        "expected_follows": round(baseline.get("follows_gained", 0), 1),
        "expected_shares": round(baseline.get("shares", 0), 1),
        "expected_saves":  round(baseline.get("saves", 0), 1),
        "prediction_basis": (
            "account p90 baseline used as a prior; not yet modelled per-hook. "
            "Confidence stays low until hook-level outcomes accumulate."),
    }


def build_contract(piece: dict, asset_id: str = "", day: int = 0) -> dict:
    """
    The 14-field Growth Director output for one content idea.
    Fields that cannot be known honestly are None with a stated basis.
    """
    piece = piece or {}
    share = shareability(piece)

    risks: list[str] = []
    try:
        from content_generator.analytics.hook_selector import hook_violations
        risks += hook_violations(str(piece.get("hook") or piece.get("hook_text") or ""))
    except Exception as e:
        logger.debug("[contract] hook checks unavailable: %s", e)
    if not share["passes"]:
        risks.append(f"fails north-star shareability ({share['score']}/100)")
    try:
        from content_generator.core.content_balance import check as balance_check
        bal = balance_check(piece, asset_id)
        if not bal["allowed"]:
            risks.append(bal["reason"])
    except Exception as e:
        logger.debug("[contract] balance check unavailable: %s", e)
        bal = {"kind": "unknown"}

    best_time = ""
    try:
        from content_generator.core.founder_policy import policy
        best_time = str(policy().get("posting_times") or "")
    except Exception as e:
        logger.debug("[contract] policy posting times unavailable: %s", e)

    contract = {
        "asset_id":        asset_id,
        "content_kind":    bal.get("kind", "unknown"),
        "why_this_works":  share["reasons"],
        "risks":           risks or ["none detected by the deterministic checks"],
        "suggested_hook":  str(piece.get("hook") or piece.get("hook_text") or ""),
        "caption":         str(piece.get("caption") or ""),
        "cta":             str(piece.get("cta") or piece.get("primary_cta") or ""),
        "hashtags":        piece.get("hashtags") or "",
        "seo_keywords":    _seo_keywords(piece),
        "suggested_thumbnail": str(piece.get("thumbnail") or piece.get("hook_visual_concept") or ""),
        "best_posting_time":   best_time,
        "shareability":    share,
    }
    preds = _predictions()
    contract.update(preds)
    contract["actual_viral_score"] = preds.get("viral_score")

    try:
        from content_generator.core.viral_readiness import evaluate_viral_readiness
        readiness = evaluate_viral_readiness(piece)
        contract["viral_readiness_score"] = readiness["score"]
        contract["readiness_breakdown"] = readiness["dimensions"]
    except Exception as e:
        logger.debug("[contract] viral readiness unavailable: %s", e)
        contract["viral_readiness_score"] = None
        contract["readiness_breakdown"] = {}

    return contract


def _seo_keywords(piece: dict) -> list[str]:
    """Keywords actually present in the copy — not invented search volume."""
    text = " ".join(str(piece.get(k) or "") for k in
                    ("hook", "headline", "caption", "body")).lower()
    seeds = ("instant coffee", "chicory", "pure coffee", "arabica", "robusta",
             "freeze dried", "coffee india", "no additives", "coffee label",
             "black coffee", "coffee price")
    return [s for s in seeds if s in text]


def check_objective_alignment(piece: dict, objective: str | None = None) -> dict:
    """
    Validates that an asset's CTA and conclusion align with its funnel objective.
    e.g., An asset assigned FOLLOW must have an explicit follow/subscribe cue.
    """
    import re
    obj = str(objective or piece.get("funnel_objective") or piece.get("objective") or "").upper()
    cta = str(piece.get("cta") or piece.get("primary_cta") or "").lower()
    caption = str(piece.get("caption") or "").lower()
    spoken = ""
    if "frames" in piece and isinstance(piece["frames"], list):
        spoken = " ".join(str(f.get("spoken") or "") for f in piece["frames"]).lower()
    elif "scenes" in piece and isinstance(piece["scenes"], list):
        spoken = " ".join(str(s.get("spoken") or "") for s in piece["scenes"]).lower()
    text = f"{cta} {caption} {spoken}"

    if "FOLLOW" in obj:
        has_follow = bool(re.search(r"\b(follow|subscriber?|subscribing|tap follow)\b", text))
        return {
            "passes": has_follow,
            "objective": "FOLLOW",
            "reason": "Follow CTA cue present" if has_follow else "Asset objective is FOLLOW but CTA lacks follow/subscribe invitation",
            "suggested_cta": "Follow @puritybeans so you never drink roasted root again.",
        }
    elif "DISCOVERY" in obj:
        has_share = bool(re.search(r"\b(share|send|tag|forward|pass this)\b", text))
        return {
            "passes": has_share,
            "objective": "DISCOVERY",
            "reason": "Discovery share cue present" if has_share else "Asset objective is DISCOVERY but CTA lacks share/send trigger",
            "suggested_cta": "Send this to someone who drinks instant coffee.",
        }
    elif "AUTHORITY" in obj:
        has_save = bool(re.search(r"\b(save|bookmark|keep|screenshot|note)\b", text))
        return {
            "passes": has_save,
            "objective": "AUTHORITY",
            "reason": "Authority save cue present" if has_save else "Asset objective is AUTHORITY but CTA lacks save/bookmark cue",
            "suggested_cta": "Save this before your next grocery run.",
        }
    elif "COMMUNITY" in obj:
        has_comment = bool(re.search(r"\b(comment|tell|thoughts|which|vote|drop)\b", text))
        return {
            "passes": has_comment,
            "objective": "COMMUNITY",
            "reason": "Community comment cue present" if has_comment else "Asset objective is COMMUNITY but CTA lacks discussion question/prompt",
            "suggested_cta": "Which one would you choose? Comment below.",
        }
    return {"passes": True, "objective": obj, "reason": "No strict alignment constraints", "suggested_cta": ""}


def check_objective_compliance(piece: dict, objective: str | None = None) -> dict:
    """
    Deep creative compliance check:
    Distinguishes CTA compliance from Objective compliance.
    An asset assigned FOLLOW or DISCOVERY must NOT be a product pitch with a follow CTA
    tacked on. If the creative is product-first, it FAILS objective compliance and cannot
    be auto-healed simply by prepending a follow CTA.
    """
    from content_generator.core.content_balance import classify_asset
    obj = str(objective or piece.get("funnel_objective") or piece.get("objective") or "").upper()
    kind = classify_asset(piece)

    if ("FOLLOW" in obj or "DISCOVERY" in obj) and kind == "product":
        return {
            "passes": False,
            "creative_compliant": False,
            "cta_compliant": False,
            "reason": f"Asset assigned {obj} objective is primarily promotional/commercial copy — selling to strangers wastes viral reach",
            "suggested_cta": "",
        }

    cta_align = check_objective_alignment(piece, objective)
    return {
        "passes": cta_align["passes"],
        "creative_compliant": True,
        "cta_compliant": cta_align["passes"],
        "reason": cta_align["reason"],
        "suggested_cta": cta_align.get("suggested_cta", ""),
    }

