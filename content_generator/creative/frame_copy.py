"""On-image copy. One catalog price, no invented money claims, configured handle."""
from __future__ import annotations

import re

_MONEY_HOOK = re.compile(
    r"(?:₹|rs\.?\s*)\s*\d|\b\d+\s*(?:%|percent)\b|\bwaste\b|\bevery\s+week\b",
    re.I,
)


def frame_cta() -> str:
    from config.brand_config import platform_handle
    handle = platform_handle("instagram")
    if handle:
        return f"Follow {handle}  ·  p3online.in"
    return "Shop p3online.in"


def _catalog(product):
    from content_generator.creative.jar_frame import product_slug
    slug = product_slug(product)
    if not slug:
        return None
    try:
        from content_generator.core.shopify_catalog import get_product
        return get_product(slug)
    except Exception:
        return None


def _clean_hook(headline: str, featured: str) -> str:
    from content_generator.creative.real_jar_composer import _sanitize_text
    from content_generator.core.product_truth import product_truth_findings

    custom = _sanitize_text(headline).strip()
    if not custom or _MONEY_HOOK.search(custom) or product_truth_findings(custom, featured=featured):
        return ""
    words = custom.split()[:8]
    trail = {"on", "a", "an", "the", "this", "to", "for", "of", "and", "with", "your", "in", "at", "from", "by", "its", "it's", "is", "how", "was", "are"}
    while words and words[-1].lower().strip(".,:;!") in trail:
        words.pop()
    return " ".join(words)


def conversion_copy(product, headline: str = "", sub: str = "") -> dict:
    """One hook, one true benefit, a catalog price only when the jar is in stock."""
    from content_generator.creative.cinematic_frame import _product_class
    from content_generator.creative.jar_frame import product_slug
    from content_generator.creative.real_jar_composer import _sanitize_text
    from content_generator.core.product_truth import product_truth_findings

    kind = _product_class(product)
    catalog = _catalog(product)
    in_stock = bool(catalog and catalog.get("in_stock"))
    offer = ""
    if in_stock:
        variants = [v for v in (catalog.get("variants") or []) if v.get("price")]
        if variants:
            variant = min(variants, key=lambda item: item["price"])
            offer = f"{variant.get('weight', '')}  Rs {variant['price']}".strip()

    if kind == "ultra":
        hook, benefit = "The ratio is on the jar", "70% coffee and 30% chicory. Smooth milk coffee."
    elif product_slug(product) == "prima" or (catalog and not catalog.get("in_stock") and product_slug(product) == "prima"):
        hook, benefit = "Prima is out of stock", "100% Arabica. Not available to order."
        offer = ""
    elif product_slug(product) == "purista":
        hook, benefit = "One ingredient on the label", "Freeze-dried 100% Robusta. Zero chicory."
    elif product_slug(product) == "purica":
        hook, benefit = "Turn the jar around", "Freeze-dried 100% Arabica. Zero chicory."
    elif product_slug(product) == "bold" or kind == "pure":
        hook, benefit = "Turn the jar around", "100% Robusta. Zero chicory."
    else:
        hook, benefit = "Read the label", "India's cleanest instant coffee."
        offer = ""

    featured = str(product or "")
    custom = _clean_hook(headline, featured)
    if custom:
        hook = custom
    benefit_custom = _sanitize_text(sub).strip()
    if (
        benefit_custom
        and len(benefit_custom.split()) <= 12
        and not _MONEY_HOOK.search(benefit_custom)
        and not product_truth_findings(benefit_custom, featured=featured)
    ):
        benefit = benefit_custom

    cta = frame_cta()
    blob = " ".join(part for part in (hook, benefit, offer, cta) if part)
    if product_truth_findings(blob, featured=featured):
        if kind == "ultra":
            hook, benefit = "The ratio is on the jar", "70% coffee and 30% chicory."
        else:
            hook, benefit = "Read the label", "See the jar at p3online.in."
            offer = "" if kind != "pure" else offer
    return {
        "hook": _sanitize_text(hook),
        "benefit": _sanitize_text(benefit),
        "offer": _sanitize_text(offer),
        "cta": _sanitize_text(cta),
    }
