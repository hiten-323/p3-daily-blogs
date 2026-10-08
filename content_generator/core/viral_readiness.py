"""
Viral Readiness Engine — evaluates pre-publication creative quality across
platform-native distribution mechanics and viral follower levers.

Distinguishes:
  - viral_readiness_score: pre-publish creative quality gate (0-100)
  - actual_viral_score:    post-publish empirical performance (computed from measured insights)

An asset must earn the right to publish by passing all core creative dimensions:
  HOOK | NOVELTY | RETENTION | PAYOFF | SHARE REASON | FOLLOW REASON | PLATFORM NATIVENESS | TRUTH
"""
from __future__ import annotations
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

READINESS_THRESHOLD = 60.0

_GENERIC_HOOKS = re.compile(
    r"\b(start your day|coffee lovers|coffee time|morning fuel|best coffee|"
    r"rich aroma|taste the difference|perfect cup|premium quality|your daily dose)\b",
    re.I,
)

_SPECIFIC_DETAILS = re.compile(
    r"\b(chicory|arabica|robusta|freeze[- ]dried|spray[- ]dried|label|ingredient|"
    r"sublimation|degrees|85°c|100°c|rs 18|price per cup|tannins|chlorogenic|inulin|"
    r"ultra blend|purica|prima|bold|purista)\b",
    re.I,
)

_SHARE_TRIGGERS = re.compile(
    r"\b(share|send this to|forward|pass this|tag someone|show this to)\b",
    re.I,
)

_FOLLOW_TRIGGERS = re.compile(
    r"\b(follow @?puritybeans|follow hiten|follow for|subscribe for|tap follow|"
    r"follow — tomorrow|follow so you never)\b",
    re.I,
)

_FAKE_PROOF_PATTERNS = re.compile(
    r"\b(\d{1,3},\d{3} customers|over \d{4} happy|dr\. [a-z]+ recommends|cures [a-z]+|prevents cancer)\b",
    re.I,
)


def evaluate_viral_readiness(
    piece: dict,
    platform: str = "",
    objective: str = "",
) -> dict[str, Any]:
    """
    Evaluate creative readiness of a generated asset before publication.

    Returns:
        {
            "score": float (0-100),
            "passes": bool,
            "dimensions": dict[str, float],
            "reasons": list[str],
            "basis": "pre-publication creative viral-readiness evaluation"
        }
    """
    if not isinstance(piece, dict) or not piece:
        return {
            "score": 0.0,
            "passes": False,
            "dimensions": {},
            "reasons": ["empty or invalid asset payload"],
            "basis": "pre-publication creative viral-readiness evaluation",
        }

    # Extract all textual content
    hook = " ".join(
        str(piece.get(k) or "")
        for k in ("hook", "hook_text", "hook_line", "headline", "title", "chosen_hook")
    ).strip()

    caption = str(piece.get("caption") or piece.get("body") or piece.get("text") or "").strip()
    cta = str(piece.get("cta") or piece.get("primary_cta") or "").strip()

    spoken = ""
    if "frames" in piece and isinstance(piece["frames"], list):
        spoken = " ".join(str(f.get("spoken") or "") for f in piece["frames"])
    elif "scenes" in piece and isinstance(piece["scenes"], list):
        spoken = " ".join(str(s.get("spoken") or "") for s in piece["scenes"])
    elif "script" in piece and isinstance(piece["script"], list):
        spoken = " ".join(str(s.get("spoken") or s.get("voiceover") or "") for s in piece["script"])

    full_copy = f"{hook} {caption} {cta} {spoken}".strip()
    if not full_copy:
        return {
            "score": 0.0,
            "passes": False,
            "dimensions": {},
            "reasons": ["no copy found in asset"],
            "basis": "pre-publication creative viral-readiness evaluation",
        }

    dimensions: dict[str, float] = {}
    reasons: list[str] = []

    # 1. HOOK (0-15): stops thumb in <2s, creates tension or counterintuitive curiosity
    hook_score = 10.0
    if not hook:
        hook_score = 4.0
        reasons.append("weak or missing dedicated hook")
    elif _GENERIC_HOOKS.search(hook):
        hook_score = 3.0
        reasons.append("generic advertising hook")
    else:
        if re.search(r"\b(why|wrong|actually|turns out|don't|stop|truth|turn the jar|check)\b", hook, re.I):
            hook_score = 15.0
            reasons.append("high-curiosity tension hook")
        else:
            hook_score = 11.0
    dimensions["hook"] = hook_score

    # 2. NOVELTY & SPECIFICITY (0-15): concrete, checkable details vs generic filler
    details_found = len(_SPECIFIC_DETAILS.findall(full_copy))
    if details_found >= 3:
        novelty_score = 15.0
        reasons.append(f"high factual novelty ({details_found} specific details)")
    elif details_found >= 1:
        novelty_score = 11.0
    else:
        novelty_score = 4.0
        reasons.append("lacks concrete, verifyable coffee details")
    dimensions["novelty"] = novelty_score

    # 3. RETENTION & PACING (0-15): structured progression, not unbroken text block
    retention_score = 4.0
    if "frames" in piece or "scenes" in piece:
        items = piece.get("frames") or piece.get("scenes") or []
        if len(items) >= 5:
            retention_score = 15.0
        elif len(items) >= 3:
            retention_score = 12.0
    elif "\n\n" in caption and len(caption.split(".")) >= 4:
        retention_score = 10.0
    elif len(caption.split(".")) >= 3:
        retention_score = 7.0
    dimensions["retention"] = retention_score

    # 4. PAYOFF (0-15): closes curiosity with concrete insight
    payoff_score = 0.0
    try:
        from content_generator.core.scroller_psychology import payoff_strength
        p_check = payoff_strength(piece)
        if p_check.get("passes"):
            payoff_score = 15.0
        else:
            payoff_score = 0.0
            reasons.append(f"payoff deficit: {p_check.get('reason', 'incomplete curiosity loop')}")
    except Exception:
        if details_found >= 2:
            payoff_score = 12.0
    dimensions["payoff"] = payoff_score

    # 5. SHARE REASON (0-10): private DM shareability
    if _SHARE_TRIGGERS.search(full_copy) or piece.get("share_trigger"):
        share_score = 10.0
    elif re.search(r"\b(chicory|adulterat|40%|filler|ingredient list)\b", full_copy, re.I):
        share_score = 8.0
    else:
        share_score = 2.0
    dimensions["share_reason"] = share_score

    # 6. FOLLOW REASON (0-10): clear selfish reason to follow
    obj_str = str(objective or piece.get("funnel_objective") or piece.get("objective") or "").upper()
    if _FOLLOW_TRIGGERS.search(full_copy):
        follow_score = 10.0
        reasons.append("explicit follower incentive present")
    elif "FOLLOW" in obj_str:
        follow_score = 1.0
        reasons.append("FOLLOW objective assigned but no follow incentive in copy")
    else:
        follow_score = 4.0
    dimensions["follow_reason"] = follow_score

    # 7. PLATFORM NATIVENESS (0-10): format compliance
    platform_clean = platform.lower()
    native_score = 10.0
    if "threads" in platform_clean:
        if len(full_copy) > 480:
            native_score = 4.0
            reasons.append("Threads post exceeds 480 characters")
        elif "http" in full_copy or "p3online.in" in full_copy:
            native_score = 6.0
            reasons.append("Threads post contains promotional link (penalized by algorithm)")
    elif "youtube" in platform_clean:
        if not ("scenes" in piece or "frames" in piece or piece.get("script")):
            native_score = 4.0
            reasons.append("YouTube Short lacks native video scene breakdown")
    dimensions["platform_nativeness"] = native_score

    # 8. TRUTH & INTEGRITY (0-10): zero fake social proof or medical claims
    if _FAKE_PROOF_PATTERNS.search(full_copy):
        truth_score = 0.0
        reasons.append("contains fabricated social proof or medical claims")
    else:
        truth_score = 10.0
    dimensions["truth_and_integrity"] = truth_score

    total_score = round(sum(dimensions.values()), 1)
    passes = total_score >= READINESS_THRESHOLD and truth_score > 0 and dimensions.get("payoff", 0) >= 8.0

    return {
        "score": total_score,
        "passes": passes,
        "dimensions": dimensions,
        "reasons": reasons,
        "basis": "pre-publication creative viral-readiness evaluation",
    }
