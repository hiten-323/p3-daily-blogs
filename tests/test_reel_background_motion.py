import numpy as np

from content_generator.creative import reel_video
from content_generator.creative.visual_gate import MIN_BG_MOTION, background_motion


def test_featured_product_routes_to_cinematic(monkeypatch):
    seen = {}

    def fake(beats, product, *a, **k):
        seen["product"] = product
        return "out.mp4"

    monkeypatch.setattr(reel_video, "_cinematic", fake)
    monkeypatch.setenv("ENABLE_REEL_VIDEO", "true")
    reel = {"featured_product": "Ultra Blend", "frames": [{"on_screen": "A", "spoken": "b"}],
            "reel_inspiration": {"mode": "style_cues", "publish_source_video": False}}
    assert reel_video.build_reel_video(reel, day=292) == "out.mp4"
    assert seen["product"] == "Ultra Blend"


def test_resolve_from_growth_plan():
    assert reel_video.resolve_reel_product({"growth_plan": {"sku": "Bold"}}) == "Bold"
    assert reel_video.resolve_reel_product({"growth_review": {"plan": {"sku": "Purica"}}}) == "Purica"
    assert reel_video.resolve_reel_product({}) is None


def test_static_background_rejected():
    flat = np.full((192, 108, 3), 90, np.uint8)
    assert background_motion([flat, flat.copy()]) < MIN_BG_MOTION
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, (192, 108, 3), dtype=np.uint8)
    b = rng.integers(0, 255, (192, 108, 3), dtype=np.uint8)
    assert background_motion([a, b]) >= MIN_BG_MOTION
