
"""
Instagram product tagging — makes posts shoppable (tap product -> product page).

Requires (one-time, founder-side setup — see README / SETUP_SHOPPING.md):
  1. Instagram Business account with an APPROVED Instagram Shop
  2. A product catalog connected (Shopify's "Facebook & Instagram" channel
     syncs your products to Meta Commerce Manager automatically)
  3. The account approved for Instagram Shopping

Config (GitHub Secrets, all optional — absent = posts stay non-shoppable):
  IG_PRODUCT_ID    a single default product id to tag on every post, OR
  IG_CATALOG_ID    catalog id — the engine then resolves a product per post
                   by matching keywords (bold/ultra/purista/purica) in the text

This module resolves product ids and builds the product_tags payload the
Graph API expects. Everything degrades to "no tags" on any failure so a
mis-set catalog never blocks publishing.
"""
from __future__ import annotations
from config.api_versions import META_GRAPH_BASE
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_GRAPH_API = META_GRAPH_BASE
_TIMEOUT   = 30

# text keyword -> Purity Beans product (for catalog search)
_PRODUCT_KEYWORDS = {
    "bold":        ["bold"],
    "ultra blend": ["ultra blend", "ultrablend", "ultra"],
    "purista":     ["purista"],
    "purica":      ["purica"],
}


def shopping_enabled() -> bool:
    return bool(os.getenv("IG_PRODUCT_ID") or os.getenv("IG_CATALOG_ID"))


def _graph_get(path: str, params: dict) -> dict | None:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return None
    url = f"{_GRAPH_API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "PurityBeans/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("[product_tags] catalog lookup failed: %s", e)
        return None


def _resolve_product_id(text: str) -> str | None:
    """
    Pick a product id for this post.
    Priority: explicit IG_PRODUCT_ID > catalog keyword match > first catalog item.
    """
    explicit = os.getenv("IG_PRODUCT_ID")
    if explicit:
        return explicit

    catalog_id = os.getenv("IG_CATALOG_ID")
    acct_id    = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not catalog_id or not acct_id:
        return None

    low = (text or "").lower()
    wanted = None
    for product, kws in _PRODUCT_KEYWORDS.items():
        if any(k in low for k in kws):
            wanted = product
            break

    # Instagram catalog product search scoped to the IG user
    data = _graph_get(f"{acct_id}/catalog_product_search",
                      {"catalog_id": catalog_id, "q": wanted or "purity beans"})
    items = (data or {}).get("data") or []
    if not items:
        # fall back to any product in the catalog
        data = _graph_get(f"{acct_id}/catalog_product_search", {"catalog_id": catalog_id})
        items = (data or {}).get("data") or []
    if items:
        return items[0].get("product_id") or items[0].get("id")
    return None


def build_image_product_tags(text: str) -> str | None:
    """
    Return a JSON string for the media API `product_tags` param (feed IMAGE),
    or None when shopping is not configured/resolvable.
    Image tags need x/y in 0..1 — placed lower-centre over the jar.
    """
    if not shopping_enabled():
        return None
    pid = _resolve_product_id(text)
    if not pid:
        logger.info("[product_tags] shopping configured but no product resolved — posting untagged")
        return None
    tags = [{"product_id": str(pid), "x": 0.5, "y": 0.75}]
    logger.info("[product_tags] tagging post with product %s", pid)
    return json.dumps(tags)


def build_reel_product_tags(text: str) -> str | None:
    """Return JSON for `product_tags` on a REEL/VIDEO (no x/y needed)."""
    if not shopping_enabled():
        return None
    pid = _resolve_product_id(text)
    if not pid:
        return None
    return json.dumps([{"product_id": str(pid)}])
