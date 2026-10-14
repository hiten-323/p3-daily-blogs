"""Compare a pasted label with the brand photo. The check is even colour, not a repaint."""
from __future__ import annotations

import os

import numpy as np

_LABEL_DE = 6.0
_QUADRANT_SPREAD = 0.06


def _lum(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _label_crop(image, box):
    """The brand ink, inside the cap and above the glass foot."""
    x0, y0, x1, y1 = [int(v) for v in box]
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    crop = image.crop((
        x0 + int(width * 0.18),
        y0 + int(height * 0.36),
        x0 + int(width * 0.82),
        y0 + int(height * 0.74),
    )).convert("RGB")
    if crop.size[0] < 8 or crop.size[1] < 8:
        return None
    return crop


def label_color_issues(rendered, reference) -> list[str]:
    """Fail when the label drifts from the product photo or is lighter on one side."""
    from PIL import Image, ImageFilter

    if rendered is None or reference is None:
        return []
    if reference.size != rendered.size:
        reference = reference.resize(rendered.size, Image.Resampling.LANCZOS)
    got = np.asarray(rendered.convert("RGB")).astype(np.float32)
    src = np.asarray(reference.convert("RGB")).astype(np.float32)
    # Type edges ring after the downscale. The mean is the colour field, not those halos.
    field = ImageFilter.GaussianBlur(radius=0.8)
    got_c = np.asarray(rendered.convert("RGB").filter(field)).astype(np.float32)
    src_c = np.asarray(reference.convert("RGB").filter(field)).astype(np.float32)
    issues = []
    if float(np.mean(_delta_e(got_c, src_c))) >= _LABEL_DE:
        issues.append("label_color_drift")
    ratios = _quadrant_ratios(got, src)
    if ratios and (max(ratios) / max(min(ratios), 1e-3) - 1.0) > _QUADRANT_SPREAD:
        issues.append("label_uneven")
    return issues


def label_fidelity_issues(image, jar_bbox, source_path, scene_id=None) -> list[str]:
    """Compare the pasted label with the knocked-out brand photo, before the grade."""
    from PIL import Image
    from content_generator.creative.real_jar_composer import knockout_white
    from content_generator.creative.scene_natural import seat_perspective

    if not source_path or not os.path.exists(str(source_path)):
        return []
    rendered = _label_crop(image, jar_bbox)
    if rendered is None:
        return []
    rim = 0.30
    if scene_id:
        from content_generator.creative.lifestyle_scene import scene_by_id
        scene = scene_by_id(scene_id)
        if scene:
            rim = float(scene.get("rim", rim))
    with Image.open(source_path) as source:
        jar = seat_perspective(knockout_white(source), rim)
    reference = _label_crop(jar, (0, 0, jar.width, jar.height))
    return label_color_issues(rendered, reference)


def _quadrant_ratios(rendered: np.ndarray, reference: np.ndarray) -> list[float]:
    got, src = _lum(rendered), _lum(reference)
    height, width = got.shape
    if height < 4 or width < 4:
        return []
    boxes = (
        (0, height // 2, 0, width // 2),
        (0, height // 2, width // 2, width),
        (height // 2, height, 0, width // 2),
        (height // 2, height, width // 2, width),
    )
    ratios = []
    for y0, y1, x0, x1 in boxes:
        base = float(src[y0:y1, x0:x1].mean())
        if base < 1.0:
            continue
        ratios.append(float(got[y0:y1, x0:x1].mean()) / base)
    return ratios


def _delta_e(rendered: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return _ciede2000(_lab(rendered), _lab(reference))


def _lab(rgb: np.ndarray) -> np.ndarray:
    channel = np.clip(rgb / 255.0, 0, 1)
    linear = np.where(channel <= 0.04045, channel / 12.92, ((channel + 0.055) / 1.055) ** 2.4)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ], dtype=np.float32)
    xyz = linear @ matrix.T / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    pivot = np.where(xyz > 0.008856, np.cbrt(xyz), (7.787 * xyz) + (16.0 / 116.0))
    return np.stack([
        116.0 * pivot[..., 1] - 16.0,
        500.0 * (pivot[..., 0] - pivot[..., 1]),
        200.0 * (pivot[..., 1] - pivot[..., 2]),
    ], axis=-1)


def _ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cbar = (c1 + c2) / 2.0
    cbar7 = cbar ** 7
    gee = 0.5 * (1.0 - np.sqrt(cbar7 / (cbar7 + 25.0 ** 7)))
    a1p, a2p = (1.0 + gee) * a1, (1.0 + gee) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    dl, dc = l2 - l1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(dh > 180.0, dh - 360.0, dh)
    dh = np.where(dh < -180.0, dh + 360.0, dh)
    dh = np.where(c1p * c2p == 0, 0.0, dh)
    dhp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh) / 2.0)
    lbar, cbarp = (l1 + l2) / 2.0, (c1p + c2p) / 2.0
    hsum = h1p + h2p
    hmean = np.where(
        c1p * c2p == 0,
        hsum,
        np.where(
            np.abs(h1p - h2p) <= 180.0,
            hsum / 2.0,
            np.where(hsum < 360.0, (hsum + 360.0) / 2.0, (hsum - 360.0) / 2.0),
        ),
    )
    tee = (
        1.0
        - 0.17 * np.cos(np.radians(hmean - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * hmean))
        + 0.32 * np.cos(np.radians(3.0 * hmean + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * hmean - 63.0))
    )
    dtheta = 30.0 * np.exp(-((hmean - 275.0) / 25.0) ** 2)
    rc = 2.0 * np.sqrt(cbarp ** 7 / (cbarp ** 7 + 25.0 ** 7))
    sl = 1.0 + (0.015 * (lbar - 50.0) ** 2) / np.sqrt(20.0 + (lbar - 50.0) ** 2)
    sc = 1.0 + 0.045 * cbarp
    sh = 1.0 + 0.015 * cbarp * tee
    rt = -np.sin(np.radians(2.0 * dtheta)) * rc
    return np.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhp / sh) ** 2 + rt * (dc / sc) * (dhp / sh))
