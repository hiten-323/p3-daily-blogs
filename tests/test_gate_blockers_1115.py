"""15 Nov 2026: deterministic gate failures that held the YouTube Short and Story."""
from content_generator.core.brand_validator import validate_asset, validate_brand_facts
from content_generator.core.product_truth import asset_product_truth_findings
from content_generator.scheduler.daily import _ensure_story_brand_fact, _inject_brand_into_piece


def _utm(piece):
    return [f for f in asset_product_truth_findings(piece) if "utm_source" in f["reason"]]


def test_links_inside_yt_short_scenes_and_script_lists_get_tagged():
    piece = {
        "product": "Purista",
        "cta": "Shop Purity Beans",
        "description": "Purista is pure Robusta.",
        "scenes": [{"on_screen": "Link: https://p3online.in/products/purista", "spoken": "x"}],
        "script": ["Find it at https://p3online.in/collections/all."],
    }
    assert _utm(piece)
    out = _inject_brand_into_piece("yt_short", piece)
    assert "utm_source=youtube" in out["scenes"][0]["on_screen"]
    assert out["script"][0].endswith("utm_campaign=202610.")
    assert _utm(out) == []


def test_story_gets_a_matching_fact_only_when_missing():
    story = {"headline": "Read the jar before you buy", "featured_product": "Ultra Blend"}
    out = _inject_brand_into_piece("stories", story)
    assert "70% coffee" in out["sub"] and "pure" not in out["sub"].lower()
    assert validate_brand_facts(out["sub"])

    bold = _ensure_story_brand_fact({"headline": "Two jars, one swap", "featured_product": "Bold"})
    assert bold["sub"] == "Bold is pure coffee."
    purica = _ensure_story_brand_fact({"hook": "Smell this first", "product": "Purica 50g"})
    assert purica["sub"] == "Purica is pure Arabica."

    already = {"headline": "Purista is pure Robusta", "sub": "Tap to see"}
    assert _ensure_story_brand_fact(dict(already)) == already


def test_story_fact_does_not_break_product_truth():
    for jar in ("Bold", "Purista", "Purica", "Prima", "Ultra Blend", ""):
        story = _ensure_story_brand_fact({"headline": "Read the label", "featured_product": jar})
        assert asset_product_truth_findings(story, featured=jar or None) == [], jar
