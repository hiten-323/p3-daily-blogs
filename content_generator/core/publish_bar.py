"""Shared 8.0 editorial + LLM viral bar for every publish path.

The morning Facebook mirror used to publish a piece whose editorial score
was 8.6 while the viral judge had rejected it at 7.0, and an exhausted
fallback ladder only held the blog. This module is the one check those
paths share. PASS_MARK is never lowered.
"""
from __future__ import annotations


def ladder_block(piece: dict | None) -> str:
    """Non-empty when the fallback ladder gave up on this piece."""
    if not isinstance(piece, dict):
        return ""
    if piece.get("ladder_exhausted") or piece.get("publish_blocked") == "ladder_exhausted":
        return "FALLBACK LADDER EXHAUSTED"
    reason = str(piece.get("hold_reason") or "")
    if piece.get("held") and reason.startswith("FALLBACK LADDER"):
        return "FALLBACK LADDER EXHAUSTED"
    return ""


def viral_block(piece: dict | None) -> str:
    """LLM viral readiness. Missing scores fail closed while the gate is on."""
    from content_generator.core.viral_gate import PASS_MARK, enabled

    if not enabled():
        return ""
    if not isinstance(piece, dict):
        return "viral readiness gate: no LLM viral score"
    vp = piece.get("viral_potential")
    if not isinstance(vp, dict):
        return "viral readiness gate: no LLM viral score"
    honesty = [str(item) for item in (vp.get("honesty") or []) if str(item).strip()]
    if honesty:
        return "viral readiness gate: honesty " + "; ".join(honesty[:3])
    overall = vp.get("overall")
    if overall is None or overall == "":
        return "viral readiness gate: LLM viral score missing"
    try:
        score = float(overall)
    except (TypeError, ValueError):
        return "viral readiness gate: LLM viral score missing"
    if not vp.get("passed") or score < PASS_MARK:
        return f"viral readiness gate ({score:.1f}/10 < {PASS_MARK:.1f})"
    return ""


def quality_block(piece: dict | None, label: str = "") -> str:
    """Editorial threshold, then the LLM viral judge. Ladder exhaustion wins."""
    del label  # callers pass the asset name for logs; the bar itself is shared
    if not isinstance(piece, dict) or not piece:
        return "missing piece"
    ladder = ladder_block(piece)
    if ladder:
        return ladder
    from content_generator.core.editorial_engine import get_current_pass_score

    score = piece.get("editorial_score")
    try:
        overall = float(score.get("overall")) if isinstance(score, dict) else None
    except (TypeError, ValueError):
        overall = None
    threshold = float(get_current_pass_score())
    if overall is None or overall < threshold:
        shown = "missing" if overall is None else f"{overall:.1f}"
        return f"editorial gate ({shown}/10 < {threshold:.1f})"
    return viral_block(piece)


def reason_code(block: str) -> str:
    text = str(block or "")
    if "LADDER" in text:
        return "ladder_exhausted"
    if text.startswith("viral"):
        return "llm_viral_readiness_failed"
    if text.startswith("editorial"):
        return "editorial_below_8"
    if text == "missing piece":
        return "missing_piece"
    return "quality_gate"


def hold_exhausted(piece: dict, reason: str) -> None:
    """An exhausted ladder stays unpublished and eligible for another regen."""
    if not isinstance(piece, dict):
        return
    piece["ladder_exhausted"] = True
    piece["publish_blocked"] = "ladder_exhausted"
    piece["needs_regen"] = True
    piece["held"] = True
    piece["hold_reason"] = ("FALLBACK LADDER EXHAUSTED: " + str(reason or "below threshold"))[:500]


def clear_ladder_hold(piece: dict) -> None:
    """A new draft is not stuck on the previous ladder exhaustion."""
    if not isinstance(piece, dict):
        return
    if piece.get("publish_blocked") != "ladder_exhausted" and not piece.get("ladder_exhausted"):
        if not str(piece.get("hold_reason") or "").startswith("FALLBACK LADDER"):
            return
    piece.pop("ladder_exhausted", None)
    if piece.get("publish_blocked") == "ladder_exhausted":
        piece.pop("publish_blocked", None)
    piece.pop("needs_regen", None)
    if str(piece.get("hold_reason") or "").startswith("FALLBACK LADDER"):
        piece.pop("held", None)
        piece.pop("hold_reason", None)
