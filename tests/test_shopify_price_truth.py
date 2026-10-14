"""Every ₹ figure in content must match Shopify-derived prices (config/shopify_prices.json)."""
import json

from content_generator.core import price_truth as pt
from content_generator.core.product_truth import product_truth_findings


def _price_issues(text):
    return [f for f in product_truth_findings(text) if "price" in f.get("reason", "").lower()
            or "cup" in f.get("reason", "").lower()]


def test_grams_parsed_from_variant_titles():
    assert pt._grams("100 gms") == 100
    assert pt._grams("4 × 50g") == 200
    assert pt._grams("Purista 100g + Purica 100g") == 200


def test_ultra_blend_per_cup_math_uses_1_5g_serving_rounded_up():
    price = pt.variant_price("ultra_blend", 100)
    c = pt.cup_figures("ultra_blend", 100, price)
    import math
    assert c["cups"] == math.floor(100 / 1.5)
    assert c["per_cup"] == math.ceil(price / (100 / 1.5))
    assert pt.cup_phrase() == f"about ₹{c['per_cup']} a cup (100g = ₹{int(price)}, makes at least {c['cups']} cups)"


def test_unconfirmed_serving_skus_get_price_only_and_are_flagged():
    for row in pt.table():
        if row["slug"] != "ultra_blend":
            assert row["per_cup"] is None and row["cups"] is None
            assert row["flag"]
    assert any(f.startswith("bold:") for f in pt.flags())


def test_matching_shopify_figures_pass():
    ub = pt.ultra("price")
    assert not _price_issues(f"Ultra Blend 100g is ₹{ub}, {pt.cup_phrase()}.")
    assert not _price_issues(f"Bold 100g is ₹{int(pt.variant_price('bold', 100))} on p3online.in.")


def test_hardcoded_wrong_price_rejected():
    assert _price_issues("Bold 100g is just ₹299 today.")
    assert _price_issues("Ultra Blend 100g for Rs 349.")


def test_wrong_per_cup_and_cup_count_rejected():
    assert _price_issues("Ultra Blend is about ₹6 a cup.")
    assert _price_issues("Ultra Blend makes at least 50 cups per 100g jar.")
    assert _price_issues("Ultra Blend at ₹3 per cup.")


def test_per_cup_on_other_jars_still_rejected():
    assert _price_issues(f"Purica is about ₹{pt.ultra('per_cup')} a cup.")


def test_cafe_comparison_amounts_are_not_product_prices():
    assert not [f for f in _price_issues("A cafe cup often costs Rs 180.") if "Shopify" in f["reason"]]


def test_snapshot_is_the_source_for_catalog_prices():
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS
    snap = json.loads(pt.SNAPSHOT.read_text())["products"]
    for slug in ("bold", "ultra_blend", "purica", "purista"):
        live = {int(v["grams"]): int(v["price"]) for v in snap[slug]["variants"]}
        for v in SHOPIFY_PRODUCTS[slug]["variants"]:
            assert v["price"] == live[int(v["weight"].rstrip("g"))]


def test_refresh_falls_back_to_public_feed(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPIFY_ADMIN_TOKEN", raising=False)
    feed = {"products": [{"handle": "purity-beans-ultra-blend-instant-coffee", "title": "UB",
                          "variants": [{"title": "100 gms", "price": "309.00", "grams": 0}]}]}
    seen = []
    monkeypatch.setattr(pt, "_get_json", lambda url, headers=None: seen.append(url) or feed)
    out = tmp_path / "p.json"
    try:
        payload = pt.refresh(out)
    finally:
        pt.load.cache_clear()
    assert seen == [pt.PUBLIC_FEED]
    assert payload["source"] == "public_products_json"
    assert payload["products"]["ultra_blend"]["variants"][0]["price"] == 309


def test_hundred_percent_rule_still_holds():
    assert any("100%" in f["reason"] for f in product_truth_findings("Bold is 100% coffee."))
