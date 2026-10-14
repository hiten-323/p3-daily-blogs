"""Motion Story: 9:16, 8-12s, audio, jar in frame, Shopify-safe copy, follow CTA."""
import os
import shutil

import pytest

from content_generator.creative import story_motion as sm

pytestmark = pytest.mark.skipif(not sm._ffmpeg(), reason="ffmpeg required")


def test_story_copy_is_gate_safe_and_has_cta():
    c = sm.story_copy("bold", "Bold is 100% coffee!!", "")
    assert "100%" not in c["headline"]
    assert c["cta"] == "Follow @purepantryprovisions"
    assert "p3online.in" in c["shop"]
    u = sm.story_copy("ultra_blend")
    assert "Ultra Blend" in u["chip"] and "a cup" in u["chip"]
    assert "pure" not in u["sub"].lower()


def test_render_motion_story(tmp_path, monkeypatch):
    out = sm.render_story_motion("purica", day=3, label="t", out_dir=str(tmp_path), seconds=8)
    assert out and out["video"] and not out["qa"], out
    assert os.path.getsize(out["video"]) > 100_000
    assert os.path.exists(out["poster"])
    from PIL import Image
    assert Image.open(out["poster"]).size == (1080, 1920)


def test_jar_cutout_keeps_true_colours():
    import numpy as np
    from content_generator.creative import approved_photos as ap
    it = ap.items("ig_story", "ultra_blend", ("cutout",))[0]
    jar = sm.jar_cutout(it)
    a = np.asarray(jar)
    assert a[..., 3].mean() > 60          # mostly opaque jar, not empty
    assert (a[..., 3] == 255).any()
