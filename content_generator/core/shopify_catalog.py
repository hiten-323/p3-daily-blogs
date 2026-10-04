"""
Shopify Product & Jar Catalog — Single Source of Truth for Purity Beans Jars.

All product specifications, bean origins, process methods, jar sizes, SKUs,
prices, bundle savings, and chicory disclosures are directly aligned with the
live Shopify store (p3online.in).

Import anywhere:
    from content_generator.core.shopify_catalog import (
        SHOPIFY_PRODUCTS, get_product, get_all_products,
        get_pure_coffee_products, get_bundles, format_catalog_for_prompt,
    )
"""
from __future__ import annotations
import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

FREE_SHIPPING_THRESHOLD_INR = 399

SHOPIFY_PRODUCTS: dict[str, dict[str, Any]] = {
    "bold": {
        "id": "gid://shopify/Product/8358285115579",
        "slug": "bold",
        "title": "PURITY BEANS Bold Pure Instant Coffee | Strong & Full-Bodied | No Chicory | Certified Lead free Food Grade Glass Jar",
        "short_name": "Bold Pure Robusta",
        "handle": "purity-beans-bold-instant-coffee",
        "bean_type": "100% Robusta",
        "process": "Agglomerated instant coffee",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Deep, full-bodied, strong honest kick, naturally high caffeine",
        "packaging": "Certified Lead-free Food Grade Glass Jar",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-BLD-50", "weight": "50g", "cups": "25–50 cups", "price": 239},
            {"sku": "PB-BLD-100", "weight": "100g", "cups": "50–100 cups", "price": 369},
        ],
        "best_for": ["strong black coffee drinkers", "morning energy boost", "moka pot / filter coffee lovers"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/pb13.webp?v=1788008381",
        "highlights": [
            "100% Robusta coffee with zero chicory",
            "Agglomerated instant coffee in a glass jar",
            "No fillers, preservatives, or artificial additives",
            "Dissolves instantly in hot water or milk",
        ],
    },
    "purista": {
        "id": "gid://shopify/Product/8358285246651",
        "slug": "purista",
        "title": "PURITY BEANS Purista Freeze Dried Robusta Instant Coffee Granules | 1 Ingredient Coffee | No Chicory | Certified Lead free Food Grade Glass Jar",
        "short_name": "Purista Gourmet Robusta Granules",
        "handle": "purity-beans-purista-gourmet-instant-coffee-granules",
        "bean_type": "100% Gourmet Robusta",
        "process": "Freeze-dried granules",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Bold yet smooth, locked-in aroma, naturally rich crema",
        "packaging": "Certified Lead-free Food Grade Glass Jar",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-PST-50", "weight": "50g", "cups": "25–50 cups", "price": 319},
            {"sku": "PB-PST-100", "weight": "100g", "cups": "50–100 cups", "price": 509},
        ],
        "best_for": ["connoisseurs", "gourmet coffee drinkers", "afternoon pick-me-up"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/pb22.webp?v=1788008465",
        "highlights": [
            "Freeze-dried Robusta granules",
            "Locks in rich aroma and produces a delicate natural crema",
            "1-ingredient pure coffee — 0% chicory, zero preservatives",
            "Dissolves instantly in hot or cold water/milk",
        ],
    },
    "purica": {
        "id": "gid://shopify/Product/8358286459067",
        "slug": "purica",
        "title": "PURITY BEANS Purica Freeze Dried Arabica Instant Coffee Granules | 1 Ingredient Coffee | No Chicory | Certified Lead free Food Grade Glass Jar",
        "short_name": "Purica Gourmet Arabica Granules",
        "handle": "purity-beans-purica-gourmet-instant-coffee-granules",
        "bean_type": "100% Arabica",
        "process": "Freeze-dried granules",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Smooth, aromatic, natural caramel and chocolatey notes",
        "packaging": "Certified Lead-free Food Grade Glass Jar",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-PCA-50", "weight": "50g", "cups": "25–50 cups", "price": 329},
            {"sku": "PB-PCA-100", "weight": "100g", "cups": "50–100 cups", "price": 559},
        ],
        "best_for": ["café coffee lovers", "black coffee drinkers", "premium gifting", "desserts"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/pb41.webp?v=1774250933",
        "highlights": [
            "100% Arabica beans",
            "Zero chicory, zero bitterness, no roasted-chicory aftertaste",
            "Naturally smooth with subtle cocoa and caramel notes",
            "Dissolves instantly in hot water or cold milk",
        ],
    },
    "ultra_blend": {
        "id": "gid://shopify/Product/8358284918971",
        "slug": "ultra_blend",
        "title": "PURITY BEANS Ultra Blend Premium Instant Coffee | Rich & Smooth | Food Grade Glass Jar",
        "short_name": "Ultra Blend (70% coffee, 30% chicory)",
        "handle": "purity-beans-ultra-blend-instant-coffee",
        "bean_type": "70% coffee",
        "process": "Agglomerated instant blend",
        "chicory": "30% chicory",
        "pure_coffee": False,
        "coffee_percent": 70,
        "chicory_percent": 30,
        "flavor_profile": "Smooth everyday cup; a lower-caffeine description is allowed",
        "packaging": "Certified Lead-free Food Grade Glass Jar",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-ULT-50", "weight": "50g", "cups": "25–50 cups", "price": 209},
            {"sku": "PB-ULT-100", "weight": "100g", "cups": "50–100 cups", "price": 309},
        ],
        "best_for": ["first-time buyers", "everyday milk coffee", "switchers from commercial chicory brands"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/ultra-blend-family.png?v=1788084338",
        "highlights": [
            "70% coffee and 30% chicory",
            "Not a zero-chicory or no-chicory jar",
            "A lower-caffeine description is allowed for this jar only",
            "Do not call it 100% coffee, zero chicory, or no chicory",
        ],
    },
    "variety_box": {
        "id": "gid://shopify/Product/8479902204091",
        "slug": "variety_box",
        "title": "PURITY BEANS Variety Box | Ultra Blend + Bold + Purista + Purica | 4×50g | Certified Lead free Food Grade Glass Jars",
        "short_name": "Variety Box (4 × 50g Jars)",
        "handle": "variety-box",
        "bean_type": "All 4 Signature Blends (Ultra Blend, Bold, Purista, Purica)",
        "process": "Combination (Freeze-Dried Granules & Agglomerated)",
        "chicory": "Three 100% coffee jars plus one Ultra Blend jar (70% coffee, 30% chicory)",
        "pure_coffee": False,
        "flavor_profile": "The complete tasting flight — up to 200 cups total",
        "packaging": "4 × 50g Certified Lead-free Food Grade Glass Jars in gift box",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-VARIETY-4x50", "weight": "4 × 50g", "cups": "Up to 200 cups", "price": 877},
        ],
        "savings": "Save ₹219 (20% off vs ₹1,096 buying separately)",
        "best_for": ["discovering your favorite cup", "coffee tasting flight", "gifting"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/purity-beans-variety-pack-light-background.png?v=1788336510",
        "highlights": [
            "All four blends in one box (Ultra Blend 50g, Bold 50g, Purista 50g, Purica 50g)",
            "Best value — save ₹219 vs buying jars separately",
            "Qualifies automatically for Free Shipping",
        ],
    },
    "gourmet_duo": {
        "id": "gid://shopify/Product/8479931629755",
        "slug": "gourmet_duo",
        "title": "PURITY BEANS Gourmet Duo | Purista 100g + Purica 100g | Freeze Dried Instant Coffee | No Chicory | Certified Lead free Food Grade Glass Jars",
        "short_name": "Gourmet Duo Full Size (100g Purista + 100g Purica)",
        "handle": "gourmet-duo",
        "bean_type": "100% Freeze-Dried Gourmet Robusta + 100% Arabica",
        "process": "Freeze-Dried Granules",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Side-by-side Arabica vs Robusta comparison",
        "packaging": "2 × 100g Certified Lead-free Food Grade Glass Jars",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-GOURMET-DUO-100", "weight": "2 × 100g", "cups": "100–200 cups", "price": 908},
        ],
        "savings": "Save ₹160 (15% off vs ₹1,068 separate)",
        "best_for": ["coffee purists", "premium gifting", "Arabica vs Robusta side-by-side"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/gourmet_duo_8b626ed6-8d98-45f5-9a2d-e312c0e52b53.png?v=1784115472",
        "highlights": [
            "Two full-size 100g freeze-dried gourmet jars",
            "Extra 15% discount on bundle price",
            "Free shipping automatically included",
        ],
    },
    "gourmet_duo_mini": {
        "id": "gid://shopify/Product/8461386875067",
        "slug": "gourmet_duo_mini",
        "title": "PURITY BEANS Gourmet Duo Mini | Purista 50g + Purica 50g | Freeze Dried Instant Coffee | No Chicory | Certified Lead free Food Grade Glass Jars",
        "short_name": "Gourmet Duo Mini (50g Purista + 50g Purica)",
        "handle": "gourmet-duo-mini",
        "bean_type": "100% Freeze-Dried Gourmet Robusta + 100% Arabica",
        "process": "Freeze-Dried Granules",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Mini tasting pair — bold Robusta and smooth Arabica",
        "packaging": "2 × 50g Certified Lead-free Food Grade Glass Jars",
        "status": "ACTIVE",
        "in_stock": True,
        "variants": [
            {"sku": "PB-GOURMET-DUO-50", "weight": "2 × 50g", "cups": "50–100 cups", "price": 570},
        ],
        "savings": "Save ₹78 (12% off vs ₹648 separate)",
        "best_for": ["trying both gourmet granules", "entry-level gourmet tasting"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/mini_gourmet_duo_d463d553-de78-4d68-8667-9394a01af3f2.png?v=1784115472",
        "highlights": [
            "Two 50g freeze-dried jars (Purista + Purica)",
            "Extra 12% discount on bundle price",
            "Qualifies for Free Shipping (> ₹399)",
        ],
    },
    "prima": {
        "id": "gid://shopify/Product/8358286557371",
        "slug": "prima",
        "title": "PURITY BEANS Premium Agglomerate Instant Coffee | No Chicory | Certified Lead Free Food Grade Glass Jar",
        "short_name": "Prima Premium Arabica",
        "handle": "purity-beans-prima-premium-instant-coffee",
        "bean_type": "100% Arabica",
        "process": "Premium Agglomerate",
        "chicory": "0% chicory",
        "pure_coffee": True,
        "flavor_profile": "Naturally smooth, low bitterness",
        "packaging": "Certified Lead-free Food Grade Glass Jar",
        "status": "ACTIVE",
        "in_stock": False,  # Currently out of stock
        "variants": [
            {"sku": "PB-PRM-50", "weight": "50g", "price": 269},
            {"sku": "PB-PRM-100", "weight": "100g", "price": 449},
        ],
        "best_for": ["mindful morning routine", "everyday cafe style"],
        "hero_image": "https://cdn.shopify.com/s/files/1/0712/6315/8459/files/pb51_f23bfc18-0c9d-48fa-aa34-78f8b69b7ffb.webp?v=1774252343",
        "highlights": [
            "100% Arabica, Premium Agglomerate, zero chicory",
            "Not freeze-dried",
            "Currently out of stock (waitlist active)",
        ],
    },
}


def get_product(slug: str) -> dict[str, Any] | None:
    """Lookup a product by its slug (e.g. 'bold', 'purista', 'ultra_blend')."""
    return SHOPIFY_PRODUCTS.get(slug.lower().strip())


def get_all_products() -> list[dict[str, Any]]:
    """Return all products in the Shopify catalog."""
    return list(SHOPIFY_PRODUCTS.values())


def get_pure_coffee_products() -> list[dict[str, Any]]:
    """Return jars that are 100% coffee. Ultra Blend and the variety box are not."""
    return [p for p in SHOPIFY_PRODUCTS.values() if p.get("pure_coffee") is True]


def product_page_url(product: dict[str, Any]) -> str:
    """Public product URL. Only catalog handles are valid internal links."""
    handle = str((product or {}).get("handle") or "").strip().strip("/")
    if not handle:
        return ""
    return f"https://p3online.in/products/{handle}"


def catalog_page_urls() -> set[str]:
    """Product pages the blog may link to. No invented collection URLs."""
    return {url for url in (product_page_url(p) for p in SHOPIFY_PRODUCTS.values()) if url}


def get_bundles() -> list[dict[str, Any]]:
    """Return bundle and multi-pack options."""
    return [p for p in SHOPIFY_PRODUCTS.values() if "box" in p["slug"] or "duo" in p["slug"]]


def format_catalog_for_prompt() -> str:
    """
    Compact, authoritative product catalog block for prompt injection.
    Ensures LLM copy adheres strictly to live Shopify prices, variants, and bean facts.
    """
    lines = [
        "AUTHORITATIVE SHOPIFY PRODUCT CATALOG (Source of Truth for Jars & Pricing):",
        f"- Free Shipping: Orders above ₹{FREE_SHIPPING_THRESHOLD_INR} qualify automatically.",
        "- Packaging: Single jars are food-grade glass jars.",
        "",
        "PRODUCTS:",
    ]
    for slug, p in SHOPIFY_PRODUCTS.items():
        v_str = ", ".join(f"{v['weight']} (₹{v['price']})" for v in p.get("variants", []))
        stock = "IN STOCK" if p.get("in_stock", True) else "OUT OF STOCK — do not tell people to buy it"
        lines.append(f"• {p['short_name']} [{slug}] — {stock}:")
        lines.append(f"  - Bean / Blend: {p['bean_type']} | Chicory: {p['chicory']}")
        lines.append(f"  - Process: {p['process']}")
        lines.append(f"  - Sizes & Prices: {v_str}")
        if "savings" in p:
            lines.append(f"  - Bundle Discount: {p['savings']}")
        lines.append(f"  - Best For: {', '.join(p.get('best_for', []))}")
        lines.append(f"  - Key Notes: {p['flavor_profile']}")
        lines.append("")
    lines.append(
        "MANDATORY PRODUCT TRUTH RULES:\n"
        "1. Never invent prices, percentages, certificates, sourcing stories, or health outcomes.\n"
        "2. Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica. "
        "All three are 100% coffee and zero chicory.\n"
        "3. Prima / Premium Agglomerate is 100% Arabica. It is agglomerated, not freeze-dried.\n"
        "4. Ultra Blend is 70% coffee and 30% chicory. A lower-caffeine description is allowed for Ultra Blend only. "
        "Never call Ultra Blend 100% coffee, zero chicory, no chicory, no-chicory, zero-chicory, chicory-free, or 0% chicory.\n"
        "5. Variety Box is three 100% coffee jars plus Ultra Blend. Do not call the box zero chicory.\n"
        "6. \"India's Cleanest Instant Coffee\" is approved. Never use it alongside a zero-chicory or no-chicory claim about Ultra Blend.\n"
        "7. Samples are only for businesses (cafes, offices, retailers, distributors). "
        "Consumer-facing content must not offer a sample. Point customers to the 50g Variety Box: "
        + product_page_url(SHOPIFY_PRODUCTS["variety_box"]) + "\n"
        "8. The listed prices are correct. Prima is out of stock — do not tell people to buy it."
    )
    return "\n".join(lines)
