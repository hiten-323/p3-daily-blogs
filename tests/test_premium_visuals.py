"""Part B: premium cards + visual-quality gate."""
import os

import pytest
from PIL import Image, ImageDraw

from content_generator.creative import premium_cards as pc
from content_generator.creative import visual_gate as vg
from content_generator.creative import render_claims as rc

PASS = lambda path: {"provider": "fake", "score": 8.6, "issues": []}
LOW = lambda path: {"provider": "fake", "score": 6.1, "issues": ["flat"]}


@pytest.mark.parametrize("sku", list(pc.CUTOUTS))
def test_each_sku_renders_and_passes_heuristics(tmp_path, sku):
    meta = pc.render(sku, "A clear honest headline", "One line of support copy.", seed=1,
                     out_path=str(tmp_path / f"{sku}.jpg"))
    reasons, m = vg.heuristic_checks(Image.open(meta["path"]), meta)
    assert reasons == [], (reasons, m)


def test_layouts_rotate_and_palettes_differ(tmp_path):
    lays = {pc.render("bold", "Hello there", seed=i, out_path=str(tmp_path / f"{i}.jpg"))["layout"] for i in range(4)}
    assert lays == set(pc.LAYOUTS)
    assert pc.PALETTES["bold"][0]["mid"] != pc.PALETTES["purica"][0]["mid"]


def test_flat_pale_background_fails(tmp_path):
    p = tmp_path / "flat.jpg"
    Image.new("RGB", (1080, 1350), (225, 215, 200)).save(p)
    reasons, _ = vg.heuristic_checks(Image.open(p), {"path": str(p), "requires_jar": False})
    assert any(r.startswith(("flat_background", "pale_background")) for r in reasons)


def test_low_contrast_and_weak_hierarchy_fail(tmp_path):
    p = tmp_path / "lc.jpg"
    im = Image.new("RGB", (1080, 1350), (90, 60, 120))
    ImageDraw.Draw(im).rectangle((100, 100, 900, 200), fill=(100, 70, 130))
    im.save(p)
    meta = {"path": str(p), "text_boxes": [(100, 100, 900, 200)], "headline_px": 30, "body_px": 28,
            "requires_jar": False}
    reasons, _ = vg.heuristic_checks(im, meta)
    assert any(r.startswith("low_contrast") for r in reasons)
    assert any(r.startswith("weak_hierarchy") for r in reasons)
    assert any(r.startswith("headline_too_small") for r in reasons)


def test_jar_overlap_and_out_of_frame(tmp_path):
    meta = pc.render("purica", "Headline here", seed=0, out_path=str(tmp_path / "a.jpg"))
    bad = dict(meta, text_boxes=[meta["jar_box"]])
    reasons, _ = vg.heuristic_checks(Image.open(meta["path"]), bad)
    assert any(r.startswith("text_overlaps_jar") for r in reasons)
    oof = dict(meta, jar_box=(-10, 0, 200, 200))
    assert "jar_out_of_frame" in vg.heuristic_checks(Image.open(meta["path"]), oof)[0]


def test_layout_variety_vs_last_nine():
    meta = {"layout": "hero_center"}
    img = Image.new("RGB", (10, 10))
    recent = ["hero_center", "split_left", "hero_center", "editorial_top", "hero_center"]
    reasons, _ = vg.heuristic_checks(img, dict(meta, requires_jar=False), recent)
    assert any("layout_overused" in r for r in reasons)
    reasons, _ = vg.heuristic_checks(img, dict(meta, requires_jar=False), ["split_left", "hero_center"])
    assert any("same_layout_as_last_tile" in r for r in reasons)


def test_vision_score_bar_is_8(tmp_path):
    meta = pc.render("purista", "Deep Robusta, gently made", "Freeze-dried.", seed=2, out_path=str(tmp_path / "p.jpg"))
    assert vg.AESTHETIC_PASS == 8.0
    assert vg.evaluate(meta, vision=PASS)["passed"]
    out = vg.evaluate(meta, vision=LOW)
    assert not out["passed"] and out["reasons"][0].startswith("aesthetic_below_8.0")


def test_vision_unavailable_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("VISUAL_VISION_REQUIRED", "1")
    meta = pc.render("bold", "Strong coffee", seed=0, out_path=str(tmp_path / "b.jpg"))
    out = vg.evaluate(meta, vision=lambda p: {"score": None, "errors": ["none"]})
    assert not out["passed"]


def test_failing_piece_rerenders_with_other_template_then_holds(tmp_path):
    seen = []

    def gate(meta, recent_layouts=()):
        seen.append((meta["layout"], meta["palette"]))
        return {"passed": len(seen) >= 3, "reasons": [] if len(seen) >= 3 else ["x"]}
    meta = pc.render_until_pass("ultra_blend", "Comfort cup", seed=0, gate=gate, out_path=str(tmp_path / "u.jpg"))
    assert not meta.get("held") and len({l for l, _ in seen}) == 3
    held = pc.render_until_pass("ultra_blend", "Comfort cup", seed=0, max_tries=2,
                                gate=lambda m, recent_layouts=(): {"passed": False, "reasons": ["x"]},
                                out_path=str(tmp_path / "h.jpg"))
    assert held["held"]


def test_ultra_card_text_is_honest(tmp_path, monkeypatch):
    seen = []
    orig = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text",
                        lambda self, xy, t, *a, **k: (seen.append((str(t), rc.current())), orig(self, xy, t, *a, **k))[1])
    pc.render("ultra_blend", "100% pure comfort, zero chicory", "pure coffee", cta="FOLLOW", seed=3,
              out_path=str(tmp_path / "u.jpg"))
    for t, sku in seen:
        assert not rc.violations(t, "ultra"), t
    assert any("CHICORY BLEND" in t for t, _ in seen)
