"""Regression tests for seamless vertical story composition and cutout mattes."""

import numpy as np
from PIL import Image

from content_generator.creative.cinematic_frame import _gradient_bg
from content_generator.creative.real_jar_composer import knockout_white


def test_tall_story_background_has_no_hard_horizontal_seam():
    image = np.asarray(_gradient_bg(96, 192, is_tall=True))
    row_means = image.astype(float).mean(axis=1)
    row_steps = np.abs(np.diff(row_means, axis=0))
    assert float(row_steps.max()) <= 2.5
    assert float(row_means.std()) > 8.0


def test_jar_cutout_has_feathered_alpha_edges_without_losing_opaque_body():
    source = Image.new("RGB", (80, 100), (255, 255, 255))
    from PIL import ImageDraw
    ImageDraw.Draw(source).rounded_rectangle((20, 15, 60, 85), radius=8, fill=(150, 30, 20))
    result = knockout_white(source)
    alpha = np.asarray(result.getchannel("A"))
    assert alpha.max() == 255
    assert np.any((alpha > 0) & (alpha < 255))
    assert np.any(alpha == 0)
