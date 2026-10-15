"""Discard saved drafts that carry a banned claim or a price mismatch.

Day 286 (2026-10-14): reel_2 kept coming back with the wrong per-cup price (_RS18) because the
saved pack was reloaded on every retry and, when a from-scratch rewrite failed
(providers rate-limited), the ladder "kept the current piece". A draft that
fails a banned-claim / price check is now never retried as-is: its copy is
dropped, only non-copy metadata survives, and it is marked needs_regen so the
ladder rebuilds it from scratch. Gates and the 8.0 bar are unchanged.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

PIECE_KEYS = ("reels", "instagram_post", "carousel", "linkedin_post", "blog_post", "stories",
              "yt_short", "growth_reel", "threads_post", "facebook_post")

_BANNED_REASON = re.compile(r"^(wrong price|shopify price truth|fssai|bold is pure|per-cup price)", re.I)
_RS18 = re.compile(r"(?:\brs\.?|₹|\binr)\s*18(?![\d,.]?\d)|\beighteen\s+rupees", re.I)


def banned_reasons(piece: dict) -> list[str]:
    if not isinstance(piece, dict) or piece.get("needs_regen"):
        return []
    reasons: list[str] = []
    raw = json.dumps({k: v for k, v in piece.items() if k not in ("editorial_score", "editorial_error",
                                                                  "hold_reason", "growth_review")},
                     ensure_ascii=False)
    if _RS18.search(raw):
        reasons.append("Wrong price: Rs 18 / ₹18 a cup")  # _RS18
    try:
        from content_generator.core.product_truth import asset_product_truth_findings
        for f in asset_product_truth_findings(piece):
            r = str(f.get("reason") or f.get("issue") or f)
            if _BANNED_REASON.search(r) and r not in reasons:
                reasons.append(r)
    except Exception as e:  # truth check unavailable: the raw ₹18 scan still applies  # _RS18
        logger.debug("[purge] product truth unavailable: %s", e)
    return reasons


def purged_piece(piece: dict, reasons: list[str]) -> dict:
    from content_generator.core.fallback_ladder import scratch_base
    base = {k: v for k, v in scratch_base(piece).items()
            if not _RS18.search(json.dumps(v, ensure_ascii=False))}
    for k in ("id",):
        if k in piece:
            base[k] = piece[k]
    base["_shape"] = piece.get("_shape") or sorted(
        k for k in piece if k not in ("editorial_score", "editorial_error", "hold_reason", "held",
                                      "needs_regen", "growth_review", "_growth_attempts"))
    base.update({"needs_regen": True, "held": True,
                 "hold_reason": _RS18.sub("[banned price]",
                                          "purged banned-claim draft: " + "; ".join(reasons))[:400]})
    return base


def purge_banned_drafts(content: dict) -> list[str]:
    """Replace every banned draft in the pack in place. Returns purged labels."""
    purged: list[str] = []
    if not isinstance(content, dict):
        return purged
    for key in PIECE_KEYS:
        val = content.get(key)
        if isinstance(val, list):
            for i, piece in enumerate(val):
                reasons = banned_reasons(piece)
                if reasons:
                    val[i] = purged_piece(piece, reasons)
                    purged.append(f"reel_{i + 1}" if key == "reels" else f"{key}[{i}]")
        elif isinstance(val, dict):
            reasons = banned_reasons(val)
            if reasons:
                content[key] = purged_piece(val, reasons)
                purged.append(key)
    prompts = content.get("video_prompts")
    if isinstance(prompts, dict):
        for k in [k for k, v in prompts.items() if _RS18.search(json.dumps(v, ensure_ascii=False))]:
            prompts.pop(k)
            purged.append(f"video_prompts.{k}")
    log = content.get("fallback_ladder")
    if isinstance(log, (dict, list)):
        text = json.dumps(log, ensure_ascii=False)
        if _RS18.search(text):
            content["fallback_ladder"] = json.loads(_RS18.sub("[purged price]", text))
    if purged:
        logger.warning("[purge] discarded banned-claim drafts (will regenerate from scratch): %s", purged)
    return purged
