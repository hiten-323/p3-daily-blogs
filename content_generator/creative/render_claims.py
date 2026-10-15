"""On-image claim guard: every string drawn into a template passes here.

FSSAI: never "100%". Ultra Blend (70% coffee / 30% chicory) never "pure",
"zero chicory", "no chicory" or "chicory-free". Unknown / range-level frames
never claim the whole range is pure coffee or zero chicory.
"""
from __future__ import annotations

import contextvars
import re

ULTRA_STRIP = "Coffee + chicory blend"
PURE_STRIP = "Pure coffee \u2022 Zero chicory"
RANGE_STRIP = "India's Cleanest Instant Coffee"

_SKU = contextvars.ContextVar("render_sku", default=None)  # None = no frame scope

_HUNDRED = re.compile(r"\b100\s*(?:%|percent|per\s*cent)\s*", re.I)
_PURE_CLAIM = re.compile(
    r"\bpure\b|zero[\s-]*chicory|no[\s-]*chicory|chicory[\s-]*free|\b0\s*%\s*chicory|zero\s+fillers?", re.I)


def sku_class(product) -> str:
    k = " ".join(str(product or "").lower().replace("_", " ").replace("-", " ").split())
    if not k:
        return "unknown"
    if "ultra" in k:
        return "ultra"
    if any(s in k for s in ("bold", "purica", "purista", "prima", "duo", "mini")):
        return "pure"
    return "unknown"


def set_sku(product):
    return _SKU.set(sku_class(product))


def reset_sku(token):
    _SKU.reset(token)


def current() -> str | None:
    return _SKU.get()


def strip_for(product=None) -> str:
    k = sku_class(product) if product is not None else current()
    return {"ultra": ULTRA_STRIP, "pure": PURE_STRIP}.get(k, RANGE_STRIP)


def footer_for(product=None) -> str:
    k = sku_class(product) if product is not None else current()
    mid = {"ultra": "70% COFFEE + 30% CHICORY", "pure": "PURE COFFEE"}.get(k, "INSTANT COFFEE")
    return f"PURITY BEANS  |  {mid}  |  p3online.in"


def violations(text: str, sku: str | None = None) -> list[str]:
    sku = sku or current()
    t = str(text or "")
    out = []
    if _HUNDRED.search(t):
        out.append("on_image_100_percent")
    if sku in ("ultra", "unknown") and _PURE_CLAIM.search(t):
        out.append(f"on_image_pure_claim_on_{sku}")
    return out


def guard(text: str, sku: str | None = None) -> str:
    """Rewrite a render string so it can never carry a banned claim."""
    sku = sku or current()
    t = _HUNDRED.sub("", str(text or ""))
    if sku in ("ultra", "unknown") and _PURE_CLAIM.search(t):
        return ULTRA_STRIP if sku == "ultra" else RANGE_STRIP
    return re.sub(r"\s{2,}", " ", t).strip()
