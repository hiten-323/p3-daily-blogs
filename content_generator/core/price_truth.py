"""Shopify-derived prices: the single source of truth for every ₹ figure in content.

Order of sources for `refresh()`:
  1. Shopify Admin API (SHOPIFY_STORE_DOMAIN + SHOPIFY_ADMIN_TOKEN repo secrets)
  2. Public storefront feed https://p3online.in/products.json
The result is written to config/shopify_prices.json, which every other module
reads (offline, deterministic, testable). Run `python -m
content_generator.core.price_truth --refresh` at the start of a pipeline run.

Per-cup math (only for SKUs whose serving size is confirmed in product facts):
    cups     = floor(grams / serving_g)          -> "makes at least N cups"
    per_cup  = ceil(price / (grams / serving_g)) -> "about ₹X a cup"
Other SKUs: price only; `flags()` lists them so a human can confirm a serving.

`price_findings(text)` rejects any ₹/Rs amount or per-cup / cup-count figure that
does not match these derived values, so hardcoded numbers cannot sneak in.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT = Path(__file__).resolve().parents[2] / "config" / "shopify_prices.json"
PUBLIC_FEED = "https://p3online.in/products.json"

# Confirmed serving sizes (grams per cup) from product facts. Hiten confirmed
# Ultra Blend at 1-1.5g (₹309/100g); the 1.5g upper bound gives the
# conservative "at least" cup count. Add a SKU here ONLY once its serving is
# confirmed by the founder.
CONFIRMED_SERVING_G: dict[str, float] = {"ultra_blend": 1.5}

HANDLE_TO_SLUG = {
    "purity-beans-bold-instant-coffee": "bold",
    "purity-beans-purista-gourmet-instant-coffee-granules": "purista",
    "purity-beans-purica-gourmet-instant-coffee-granules": "purica",
    "purity-beans-ultra-blend-instant-coffee": "ultra_blend",
    "purity-beans-prima-premium-instant-coffee": "prima",
    "variety-box": "variety_box",
    "gourmet-duo": "gourmet_duo",
    "gourmet-duo-mini": "gourmet_duo_mini",
}

# Non-product amounts copy may mention: they are not our prices.
_CONTEXT_EXEMPT = re.compile(
    r"\b(?:caf[eé]s?|coffee\s*shops?|starbucks|barista|espresso\s+bar|takeaway|cafe\s+cup|"
    r"free\s+shipping|shipping|orders?\s+(?:above|over))\b", re.I)
_AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)", re.I)
_PER_CUP = re.compile(r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)(?:\s*[–-]\s*\d+)?\s*(?:/|a|per|each)\s*cup", re.I)
_CUP_COUNT = re.compile(r"\b(\d{1,4})\s*(?:\+\s*)?cups\b", re.I)


def _grams(title: str, fallback: float = 0) -> float:
    t = (title or "").lower()
    m = re.search(r"(\d+)\s*[x×]\s*(\d+)\s*g", t)
    if m:
        return float(m.group(1)) * float(m.group(2))
    nums = [float(n) for n in re.findall(r"(\d+)\s*g(?:m|ms|rams?)?\b", t)]
    if nums:
        return sum(nums)
    return float(fallback or 0)


def _normalise(products: list[dict]) -> dict:
    out: dict = {}
    for p in products:
        slug = HANDLE_TO_SLUG.get(p.get("handle", ""))
        if not slug:
            continue
        rows = []
        for v in p.get("variants", []):
            title = v.get("title") or ""
            grams = _grams(title, (v.get("grams") or 0))
            price = float(v.get("price") or 0)
            cmp_ = v.get("compare_at_price")
            rows.append({"title": title, "grams": grams, "price": round(price, 2),
                         "compare_at": round(float(cmp_), 2) if cmp_ else None})
        out[slug] = {"handle": p.get("handle"), "title": p.get("title"), "variants": rows}
    return out


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "p3-daily-blogs", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_live() -> tuple[dict, str]:
    """Return (normalised prices, source). Raises if every source fails."""
    domain = (os.getenv("SHOPIFY_STORE_DOMAIN") or "").strip().replace("https://", "").strip("/")
    token = (os.getenv("SHOPIFY_ADMIN_TOKEN") or "").strip()
    if domain and token:
        try:
            from config.api_versions import SHOPIFY_API_VERSION
            data = _get_json(f"https://{domain}/admin/api/{SHOPIFY_API_VERSION}/products.json?limit=250&status=active",
                             {"X-Shopify-Access-Token": token})
            prices = _normalise(data.get("products", []))
            if prices:
                return prices, "shopify_admin_api"
        except Exception as exc:  # never log the token
            logger.warning("[prices] Admin API fetch failed (%s); using public feed", type(exc).__name__)
    data = _get_json(PUBLIC_FEED)
    prices = _normalise(data.get("products", []))
    if not prices:
        raise RuntimeError("public products.json returned no known products")
    return prices, "public_products_json"


def refresh(path: Path = SNAPSHOT) -> dict:
    prices, source = fetch_live()
    import datetime
    payload = {"source": source, "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "products": prices}
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    load.cache_clear()
    logger.info("[prices] refreshed %d products from %s", len(prices), source)
    return payload


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["products"]


def cup_figures(slug: str, grams: float, price: float) -> dict | None:
    serving = CONFIRMED_SERVING_G.get(slug)
    if not serving or not grams:
        return None
    servings = grams / serving
    return {"cups": int(math.floor(servings)), "per_cup": int(math.ceil(price / servings)),
            "serving_g": serving}


def table() -> list[dict]:
    rows = []
    for slug, p in load().items():
        for v in p["variants"]:
            c = cup_figures(slug, v["grams"], v["price"])
            rows.append({"slug": slug, "variant": v["title"], "grams": v["grams"], "price": v["price"],
                         "compare_at": v["compare_at"],
                         "cups": c["cups"] if c else None, "per_cup": c["per_cup"] if c else None,
                         "flag": None if c else "serving size not confirmed: price only"})
    return rows


def flags() -> list[str]:
    return sorted({f"{r['slug']}: {r['flag']}" for r in table() if r["flag"]})


def variant_price(slug: str, grams: float) -> float | None:
    for v in (load().get(slug) or {}).get("variants", []):
        if abs(v["grams"] - grams) < 0.5:
            return v["price"]
    return None


def cup_phrase(slug: str = "ultra_blend", grams: float = 100) -> str:
    """'about ₹5 a cup (100g = ₹309, makes at least 66 cups)' or '' if not derivable."""
    price = variant_price(slug, grams)
    c = cup_figures(slug, grams, price or 0) if price else None
    if not c:
        return ""
    return f"about ₹{c['per_cup']} a cup ({int(grams)}g = ₹{int(price)}, makes at least {c['cups']} cups)"


def ultra(field: str, grams: float = 100) -> int:
    """Shopify-derived Ultra Blend figure: 'per_cup', 'cups' or 'price'."""
    price = variant_price("ultra_blend", grams) or 0
    if field == "price":
        return int(round(price))
    c = cup_figures("ultra_blend", grams, price) or {}
    return int(c.get(field) or 0)


def allowed_amounts() -> set[int]:
    vals: set[int] = set()
    for r in table():
        vals.add(int(round(r["price"])))
        if r["compare_at"]:
            vals.add(int(round(r["compare_at"])))
            vals.add(int(round(r["compare_at"] - r["price"])))  # Shopify-derived bundle saving
        if r["per_cup"]:
            vals.add(r["per_cup"])
    return vals


def _num(s: str) -> int:
    return int(round(float(s.replace(",", ""))))


def price_findings(text: str) -> list[str]:
    """Reasons a sentence's ₹ / per-cup / cup-count figures disagree with Shopify."""
    if not text:
        return []
    rows = table()
    per_cup_ok = {r["per_cup"] for r in rows if r["per_cup"]}
    cups_ok = {r["cups"] for r in rows if r["cups"]}
    amounts_ok = allowed_amounts()
    issues: list[str] = []
    exempt = bool(_CONTEXT_EXEMPT.search(text))
    for m in _PER_CUP.finditer(text):
        n = _num(m.group(1))
        if n not in per_cup_ok and not exempt:
            issues.append(f"per-cup ₹{n} does not match Shopify-derived per-cup "
                          f"{sorted('₹%d' % x for x in per_cup_ok)}")
    for m in _CUP_COUNT.finditer(text):
        n = int(m.group(1))
        if n not in cups_ok and not exempt:
            issues.append(f"'{n} cups' does not match the Shopify-derived cup count {sorted(cups_ok)} (1.5g serving)")
    if not exempt:
        per_cup_spans = [m.span() for m in _PER_CUP.finditer(text)]
        for m in _AMOUNT.finditer(text):
            if any(a <= m.start() < b for a, b in per_cup_spans):
                continue
            n = _num(m.group(1))
            if n not in amounts_ok:
                issues.append(f"price ₹{n} is not a live Shopify price")
    return issues


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--refresh" in sys.argv:
        try:
            refresh()
        except Exception as exc:
            logger.warning("[prices] refresh failed (%s); keeping committed snapshot", exc)
    for r in table():
        print(r)
