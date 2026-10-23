import pytest
from content_generator.core.brand_validator import validate_asset, validate_language, validate_asset_copy
from content_generator.core.content_balance import classify_asset, _PRODUCT_SIGNALS
from content_generator.scheduler.fallback import _EVERGREEN

def test_language_detection_ignores_handles_and_urls():
    text = "FOLLOW @PUREPANTRYPROVISIONS FOR DAILY COFFEE TRUTH"
    # Should be True because handles are stripped and clean text is under threshold or clean english
    assert validate_language(text) is True

def test_reel_frame_overlay_bypasses_language_detector():
    reel_piece = {
        "caption": "Purity Beans brings you the truth about milk coffee. Read the label at p3online.in to know your cup.",
        "frames": [
            {"on_screen": "Lumps in milk coffee?"},
            {"on_screen": "FOLLOW @PUREPANTRYPROVISIONS FOR DAILY COFFEE TRUTH"}
        ]
    }
    is_valid, issues = validate_asset("reel_1", reel_piece)
    # The overlay shouldn't raise "Language is not English"
    assert not any("Language is not English" in issue for issue in issues)

def test_content_balance_ignores_non_commercial_order():
    tech_post = {
        "caption": "Lumps in your milk coffee are an order problem, not a coffee problem. Lumps are an order problem. Hot water onto the granules first.",
        "objective": "FOLLOW"
    }
    hits = _PRODUCT_SIGNALS.findall(tech_post["caption"])
    assert len(hits) == 0, f"Expected 0 product hits, got: {hits}"
    # Should not classify as commercial product
    # Note: if value hits are present (or absent), it shouldn't be forced into product by 'order'
    commercial_post = {
        "caption": "Order your jar of Ultra Blend today on our website. Best price now available.",
        "objective": "CONVERSION"
    }
    assert classify_asset(commercial_post) == "product"

def test_fallback_ultra_blend_carousel_hook():
    carousels = [p for p in _EVERGREEN if p.get("type") == "carousel"]
    ultra_carousels = [c for c in carousels if "70/30" in c.get("hook", "")]
    assert len(ultra_carousels) > 0
    for c in ultra_carousels:
        assert c["hook"] == "Why your milk coffee actually needs a 70/30 ratio"
