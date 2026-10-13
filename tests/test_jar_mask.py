"""The product mask keeps the jar. Jagged edges, holes, and eaten labels fail."""
from __future__ import annotations

import numpy as np
from PIL import Image

from content_generator.creative.jar_mask import mask_issues, segment_product


def _rgb(h, w, color=(40, 28, 18)):
    plate = np.zeros((h, w, 3), dtype=np.uint8)
    plate[:] = color
    return plate


def test_a_solid_silhouette_passes():
    alpha = np.zeros((180, 140), dtype=np.uint8)
    alpha[30:150, 30:110] = 255
    assert mask_issues(alpha, alpha, _rgb(180, 140)) == []


def test_a_hole_and_missing_label_fail():
    reference = np.zeros((180, 140), dtype=np.uint8)
    reference[30:150, 30:110] = 255
    eaten = reference.copy()
    eaten[70:100, 50:90] = 0
    issues = mask_issues(eaten, reference, _rgb(180, 140))
    assert "mask_holes" in issues
    assert "jar_pixels_missing" in issues


def test_a_jagged_edge_fails():
    reference = np.zeros((200, 160), dtype=np.uint8)
    reference[40:160, 40:120] = 255
    jagged = reference.copy()
    for y in range(40, 160):
        if (y // 2) % 2 == 0:
            jagged[y, 120:148] = 255
    issues = mask_issues(jagged, reference, _rgb(200, 160))
    assert "jagged_edge" in issues
    assert "jar_pixels_missing" not in issues


def test_bold_front_mask_keeps_the_label():
    path = "brand_assets/puritybeans_bold_50g_front.png"
    cut = segment_product(Image.open(path), cache_key=path)
    assert cut.mode == "RGBA"
    alpha = np.asarray(cut.split()[-1])
    assert int((alpha > 16).sum()) > 80_000
    # The label sits inside the silhouette, so a red composite has no white studio.
    preview = Image.new("RGBA", cut.size, (180, 24, 24, 255))
    preview.alpha_composite(cut)
    rgb = np.asarray(preview.convert("RGB"))
    white = (rgb.min(axis=2) > 245).sum()
    assert white < 200
    alpha = np.asarray(cut.split()[-1])
    foot = np.asarray(cut.convert("RGB")).min(axis=2)
    rows = np.where((alpha > 40).any(axis=1))[0]
    center = foot[rows[-1], cut.width // 2 - 20:cut.width // 2 + 20]
    assert float(np.median(center)) < 120


def test_reel_prompts_do_not_share_a_cta_or_the_roasted_root_line():
    import re
    from content_generator.prompts.reels import build

    first = build("reel_1", ("Curiosity", "label"), "morning", "reel_morning", "", 285)
    second = build("reel_2", ("Curiosity", "label"), "evening", "reel_night", "", 285)
    one = re.search(r'"cta": "([^"]+)"', first).group(1)
    two = re.search(r'"cta": "([^"]+)"', second).group(1)
    assert one != two
    assert "roasted root" not in one.lower()
    assert "roasted root" not in two.lower()
    assert "purepantryprovisions" in one.lower()
