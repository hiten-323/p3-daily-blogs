"""One tracked product-page link per post.

Every daily caption points to the featured SKU's own product page
(p3online.in/products/<handle>) with per-platform UTM tags, so site traffic
from social is measurable in Shopify/GA. Clickable where the platform allows
it (Facebook, Threads, LinkedIn, YouTube description). Instagram captions do
not render links, so IG copy says "link in bio" and names the product.

Story link stickers: the Instagram Graph API content-publishing endpoint does
not support adding stickers (link, poll, mention) to Stories. Stories get an
on-image "Link in bio" line instead.

The appended copy is fixed, claim-safe text: product name + link + comment
trigger. No prices, no "100%", no urgency, no purity wording.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlencode

SITE = "https://p3online.in"

# Rotation name -> catalog slug. Display names never call Ultra Blend pure.
_DISPLAY = {
    "bold": "Purity Beans Bold",
    "ultra_blend": "Purity Beans Ultra Blend",
    "purista": "Purity Beans Purista",
    "purica": "Purity Beans Purica",
    "gourmet_duo": "Purity Beans Gourmet Duo",
    "gourmet_duo_mini": "Purity Beans Gourmet Duo Mini",
    "variety_box": "Purity Beans Variety Box",
}

_UTM_SOURCE = {
    "instagram": "instagram", "instagram_story": "instagram", "facebook": "facebook",
    "threads": "threads", "linkedin": "linkedin", "youtube": "youtube",
}
_UTM_CONTENT = {"instagram_story": "story"}


def _enabled() -> bool:
    return os.getenv("PRODUCT_LINKS", "1").strip().lower() not in ("0", "false", "no")


def _slug_for(name: str) -> str:
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    for cand in (key, key.replace("purity_beans_", "")):
        if cand in SHOPIFY_PRODUCTS:
            return cand
    try:
        from content_generator.core.product_truth import named_slugs
        found = named_slugs(raw)
        if found:
            return found[0]
    except Exception:
        pass
    for slug in sorted(SHOPIFY_PRODUCTS, key=len, reverse=True):
        if slug.replace("_", " ") in raw:
            return slug
    return ""


def featured_slug(content: dict | None = None, day: int | None = None) -> str:
    """Featured in-stock SKU slug. Out-of-stock (Prima) never gets a link."""
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS
    name = ""
    if isinstance(content, dict):
        name = str(content.get("featured_product") or content.get("product") or "")
        if not name:
            try:
                from content_generator.core.product_truth import featured_product_name
                name = featured_product_name(content)
            except Exception:
                name = ""
    if not name and day is not None:
        from content_generator.rotation import PRODUCTS, pick
        name = str(pick(PRODUCTS, int(day)))
    slug = _slug_for(name)
    prod = SHOPIFY_PRODUCTS.get(slug) or {}
    if not prod or not prod.get("in_stock", True) or not prod.get("handle"):
        return ""
    return slug


def product_name(slug: str) -> str:
    return _DISPLAY.get(slug, "Purity Beans")


def tracked_url(slug: str, platform: str, campaign: str = "daily") -> str:
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url
    base = product_page_url(SHOPIFY_PRODUCTS.get(slug) or {}) or SITE
    params = {
        "utm_source": _UTM_SOURCE.get(platform, platform),
        "utm_medium": "social",
        "utm_campaign": campaign,
    }
    if platform in _UTM_CONTENT:
        params["utm_content"] = _UTM_CONTENT[platform]
    return f"{base}?{urlencode(params)}"


def _has_product_link(text: str) -> bool:
    return bool(re.search(r"p3online\.in/products/", text or "", re.I))


def link_block(content: dict | None, platform: str, day: int | None = None) -> str:
    if not _enabled():
        return ""
    slug = featured_slug(content, day)
    name = product_name(slug) if slug else "Purity Beans"
    if platform == "instagram":
        return (f"🛒 Shop {name}: link in bio (p3online.in)\n"
                f"Comment TRY if you'd try it, or LINK for the product page 👇")
    url = tracked_url(slug, platform) if slug else f"{SITE}?{urlencode({'utm_source': _UTM_SOURCE.get(platform, platform), 'utm_medium': 'social', 'utm_campaign': 'daily'})}"
    if platform == "threads":
        return f"🛒 {name}: {url}"
    return f"🛒 Shop {name}: {url}\nComment TRY if you'd try it 👇"


def with_product_link(text: str, content: dict | None, platform: str,
                      day: int | None = None, limit: int | None = None) -> str:
    """Append the link block once. Body is trimmed, never the link, to fit `limit`."""
    text = str(text or "").rstrip()
    if not text or not _enabled():
        return text
    if platform == "instagram":
        if re.search(r"link in bio", text, re.I) and re.search(r"comment\s+(try|link)", text, re.I):
            return text
    elif _has_product_link(text):
        return text
    block = link_block(content, platform, day)
    if not block:
        return text
    sep = "\n\n"
    if limit and len(text) + len(sep) + len(block) > limit:
        room = limit - len(sep) - len(block) - 1
        if room < 40:
            return text[:limit]
        text = text[:room].rstrip() + "…"
    return f"{text}{sep}{block}"


def story_link_line(sub: str) -> str:
    """On-image Story CTA (no API link sticker exists)."""
    sub = str(sub or "").strip()
    if not _enabled() or re.search(r"link in bio", sub, re.I):
        return sub
    return f"{sub} · Link in bio" if sub else "Link in bio"
