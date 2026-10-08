"""
Content balance — enforces the 80/20 rule from the Growth Director spec.

  "Product promotion should never exceed 20% of total content.
   80% should provide value before asking for anything."

The existing content_mix_optimizer splits by AUDIENCE (consumer / distributor /
retailer). That is a different axis: it decides who a post is aimed at, not
whether the post gives something away or asks for something. Both can be true at
once, so this lives alongside it rather than replacing it.

Classification is deliberately conservative: an asset counts as PRODUCT unless
it clearly teaches, demonstrates or tells a story. Over-counting promotion is the
safe direction to be wrong in — it makes the engine publish more value, not less.
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_LEDGER = os.path.join(_LEARNING_DIR, "content_balance.json")

# Rolling window the ratio is measured over. Short enough to correct within a
# fortnight, long enough that one product post doesn't trip the gate.
WINDOW = 20
MAX_PRODUCT_SHARE = 0.20

# Language that makes a post an ask rather than a gift.
_PRODUCT_SIGNALS = re.compile(
    r"\b(buy|shop|order|cart|checkout|purchase|price|discount|offer|deal|sale|"
    r"launch|now available|in stock|grab your|get yours|link in bio|"
    r"free shipping|use code|limited)\b", re.I)

# Language that marks genuine value delivery.
_VALUE_SIGNALS = re.compile(
    r"\b(how to|why|what happens|the difference|myth|actually|test|check|"
    r"read the label|ingredient|learn|mistake|reason|truth|explain|guide|"
    r"story|started|behind|journey|lesson)\b", re.I)


def classify_asset(piece: dict) -> str:
    """Return 'product' or 'value' for one content piece."""
    if not isinstance(piece, dict):
        return "product"
    text = " ".join(str(piece.get(k) or "") for k in
                    ("hook", "hook_text", "headline", "title", "caption",
                     "body", "cta", "objective", "angle", "type"))
    # An explicit conversion objective is a product post regardless of wording.
    if str(piece.get("objective") or "").upper() in ("CONVERSION", "SELL", "PURCHASE"):
        return "product"
    product_hits = len(_PRODUCT_SIGNALS.findall(text))
    value_hits   = len(_VALUE_SIGNALS.findall(text))
    # Every post carries a CTA, so one product phrase alone doesn't make it an
    # ad. It's promotion when the ask outweighs the teaching.
    if value_hits >= 2 and value_hits >= product_hits:
        return "value"
    if product_hits >= 2:
        return "product"
    return "value" if value_hits else "product"


def _load() -> list[dict]:
    if not os.path.exists(_LEDGER):
        return []
    try:
        with open(_LEDGER, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[balance] could not read ledger: %s", e)
        return []


def record(asset_id: str, kind: str) -> None:
    """Log what was actually published, so the ratio reflects reality."""
    rows = _load()
    rows.append({"asset_id": asset_id, "kind": kind,
                 "date": today_ist().isoformat()})
    os.makedirs(_LEARNING_DIR, exist_ok=True)
    with open(_LEDGER, "w", encoding="utf-8") as f:
        json.dump(rows[-200:], f, indent=2)


def current_share(window: int = WINDOW) -> dict:
    """Product share over the trailing window."""
    rows = _load()[-window:]
    if not rows:
        return {"product": 0, "value": 0, "share": 0.0, "n": 0}
    product = sum(1 for r in rows if r.get("kind") == "product")
    return {"product": product, "value": len(rows) - product,
            "share": product / len(rows), "n": len(rows)}


def check(piece: dict, asset_id: str = "") -> dict:
    """
    Would publishing this piece breach the 20% product cap?

    Returns {"allowed": bool, "kind": str, "share_after": float, "reason": str}.
    The gate only blocks PRODUCT posts — value content is never rate-limited.
    """
    kind = classify_asset(piece)
    stats = current_share()
    n_after = stats["n"] + 1
    product_after = stats["product"] + (1 if kind == "product" else 0)
    share_after = product_after / n_after

    if kind == "value":
        return {"allowed": True, "kind": kind, "share_after": round(share_after, 3),
                "reason": "value content is never capped"}

    # Don't gate until there's a meaningful window, or a cold start would block
    # the very first product post outright.
    if stats["n"] < 5:
        return {"allowed": True, "kind": kind, "share_after": round(share_after, 3),
                "reason": f"cold start ({stats['n']} posts logged) — cap not yet enforced"}

    allowed = share_after <= MAX_PRODUCT_SHARE
    return {
        "allowed": allowed,
        "kind": kind,
        "share_after": round(share_after, 3),
        "reason": (f"product share would be {share_after:.0%} of the last {n_after} "
                   f"posts, cap is {MAX_PRODUCT_SHARE:.0%} — publish value content instead"
                   if not allowed else
                   f"product share {share_after:.0%} is within the {MAX_PRODUCT_SHARE:.0%} cap"),
    }


def get_stage_product_cap(followers: int | None = None) -> float:
    """Return the stage-dependent product ratio (e.g. 0.05 in IGNITION, 0.15 in TRACTION)."""
    try:
        from content_generator.core.growth_director import get_growth_stage
        stage = get_growth_stage(followers)
        return float(stage.get("sell_pct", 20)) / 100.0
    except Exception:
        return MAX_PRODUCT_SHARE


def enforce_portfolio_commercial_cap(valid_keys: list[str], content: dict) -> list[str]:
    """
    Level 1 Portfolio Gate:
    Enforce hard portfolio ratio: commercial_assets <= floor(total_assets * max_sell_pct).
    In IGNITION (0-1K), sell_pct is 5%:
    If total_assets <= 19, floor(total_assets * 0.05) == 0.
    Meaning commercial/product assets are strictly prohibited on ordinary days.
    """
    import math
    if not valid_keys:
        return []

    max_share = get_stage_product_cap()
    allowed_commercial = math.floor(len(valid_keys) * max_share)

    from content_generator.core.editorial_engine import _piece_for
    commercial_keys = []

    for k in valid_keys:
        piece = _piece_for(content, k)
        kind = classify_asset(piece)
        obj = str(piece.get("funnel_objective") or piece.get("objective") or "").upper()
        if kind == "product" or obj in ("CONVERSION", "CONSUMER PURCHASE"):
            commercial_keys.append(k)

    if len(commercial_keys) <= allowed_commercial:
        return valid_keys

    # Drop excess commercial assets to strictly enforce the portfolio invariant
    dropped_commercial = commercial_keys[allowed_commercial:]
    logger.warning(
        "[portfolio_gate] Dropped %d commercial asset(s) %s: stage cap allows max %d commercial in portfolio of %d (%.0f%% limit)",
        len(dropped_commercial),
        dropped_commercial,
        allowed_commercial,
        len(valid_keys),
        max_share * 100,
    )
    return [k for k in valid_keys if k not in dropped_commercial]
