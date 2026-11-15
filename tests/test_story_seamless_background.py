"""Regression tests for seamless vertical story composition and cutout mattes."""

import numpy as np
from PIL import Image

from content_generator.creative.cinematic_frame import _gradient_bg
from content_generator.creative.real_jar_composer import knockout_white
from content_generator.creative.premium_cards import PALETTES, background


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

def test_premium_story_background_has_no_horizontal_horizon_line():
    image, _horizon = background(96, 170, PALETTES["purica"][0], seed=12)
    assert _max_row_step(image) <= 4.5


def _max_row_step(image) -> float:
    """Largest mean-brightness jump between adjacent rows (RGB only).

    np.diff must run down the rows (axis=0); without an axis it compares the
    R/G/B/A channels of each row with each other, which is not a seam.
    """
    rgb = np.asarray(image.convert("RGB")).astype(float)
    rows = rgb.mean(axis=1)
    return float(np.abs(np.diff(rows, axis=0)).max())


def test_row_step_measure_catches_a_hard_horizon_line():
    image, _horizon = background(96, 170, PALETTES["purica"][0], seed=12)
    arr = np.asarray(image.convert("RGB")).copy()
    arr[119, :, :] = 255  # a hard metallic horizon line like the old renderer drew
    assert _max_row_step(Image.fromarray(arr)) > 4.5
