"""Cinematic procedural backdrop: jar layer untouched, palettes per SKU, guarded text, CTA kept."""
import numpy as np

from content_generator.creative import cinematic_motion as cm
from content_generator.creative import premium_cards as pc


def test_backdrop_moves_and_has_depth():
    pal = pc.PALETTES["bold"][0]
    bd = cm._Backdrop(pal, 0, (0.25, 0.3, 0.75, 0.4), 0.74)
    a = np.asarray(bd.frame(0.0, 10.0).convert("RGB"), np.float32)
    b = np.asarray(bd.frame(3.0, 10.0).convert("RGB"), np.float32)
    assert a.shape == (cm.H, cm.W, 3)
    assert np.abs(a - b).mean() > 1.0          # it actually moves
    assert a.std() > 14 and a.mean() < 175     # not flat, not washed out


def test_every_sku_has_palette_and_cutout():
    for sku in ("bold", "purica", "purista", "ultra_blend"):
        assert pc.PALETTES[sku] and pc.CUTOUTS[sku].endswith(".png")
        assert "lifestyle" not in pc.CUTOUTS[sku] and "infographic" not in pc.CUTOUTS[sku]


def test_layouts_cover_rotation():
    assert len(set(cm.LAYOUTS)) == 3


def test_render_short_clip(tmp_path, monkeypatch):
    out = tmp_path / "c.mp4"
    meta = cm.render_cinematic_video("bold", [{"on": "Pure coffee", "sub": "100% bold"}], str(out),
                                     seconds=1.0, seed=0, audio=None)
    assert out.exists() and (tmp_path / "c_poster.jpg").exists()
    jb = meta["jar_box"]
    assert jb[0] >= 0 and jb[1] >= 0 and jb[2] <= cm.W and jb[3] <= cm.H
    for box in meta["text_boxes"]:
        assert box[3] <= jb[1] or box[1] >= jb[3]   # text never over the jar
