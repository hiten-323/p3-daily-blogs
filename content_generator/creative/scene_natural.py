"""Seat a real jar in a photograph: scale, perspective, and the scene's light.

The label is not redrawn. Brand hue stays put. Exposure, saturation, and a
directional shade move the glass toward the table.
"""
from __future__ import annotations

import numpy as np

# The jar is the foreground hero. It sits closer than the mug, so it reads larger.
JAR_CM = 8.8
EDGE_X = 0.08
_LUM_TOL = 36.0
_CAST_TOL = 24.0
# Laplacian on the label crop. The whole-jar score stays in jar_frame.
LABEL_LAPLACIAN_MIN = 180.0
_HERO = {"story": (0.35, 0.50), "feed": (0.30, 0.45), "landscape": (0.40, 0.64)}


def frame_crop(scene, width: int, height: int) -> tuple[float, float, float]:
    """Cover crop. Short frames slide so the reference prop stays on the table."""
    src_w, src_h = (scene or {}).get("size", (720, 1280))
    scale = max(width / src_w, height / src_h)
    left = (src_w * scale - width) / 2
    top = (src_h * scale - height) / 2
    ref = scale_ref(scene)
    if not ref:
        return scale, left, top
    if height < width * 0.85:
        # Keep the prop in the upper half. The jar stands in front of it.
        anchored = ref["box"][3] * scale - height * 0.48
        top = min(max(0.0, anchored), max(0.0, src_h * scale - height))
        return scale, left, top
    y0 = ref["box"][1] * scale - top
    y1 = ref["box"][3] * scale - top
    if y0 >= height * 0.02 and y1 <= height * 0.98:
        return scale, left, top
    anchored = ref["box"][3] * scale - height * 0.62
    anchored = min(anchored, ref["box"][1] * scale - height * 0.04)
    top = min(max(0.0, anchored), max(0.0, src_h * scale - height))
    return scale, left, top


def map_box(scene, box, width: int, height: int) -> tuple[float, float, float, float]:
    """The same cover-crop load_plate uses, without clipping to the frame."""
    scale, left, top = frame_crop(scene, width, height)
    x0, y0, x1, y1 = box
    return (x0 * scale - left, y0 * scale - top, x1 * scale - left, y1 * scale - top)


def hero_bounds(width: int, height: int) -> tuple[float, float]:
    """Story/Reel 35–50% of the frame. Feed/square 30–45%. Landscape stays a hero too."""
    if height > width * 1.3:
        return _HERO["story"]
    if width > height * 1.2:
        return _HERO["landscape"]
    return _HERO["feed"]


def hero_height(width: int, height: int, ref_h: float, native_h: int) -> int:
    """Foreground size: inside the hero band, at least 1.15× the prop, never above native."""
    lo, hi = hero_bounds(width, height)
    native_h = max(1, int(native_h))
    mid = int(round(height * ((lo + hi) / 2.0)))
    # Closer to the camera than the prop, so the jar is larger than the cup.
    ahead = int(round(max(1.0, ref_h) * 1.28))
    cap = min(native_h, int(height * hi))
    floor = min(cap, max(int(height * lo), int(ref_h) + 1))
    return max(floor, min(max(mid, ahead), cap))


def scale_ref(scene) -> dict | None:
    if not scene:
        return None
    if scene.get("scale_ref"):
        return scene["scale_ref"]
    for prop in scene.get("props", ()):
        if prop.get("height_cm"):
            return prop
    return None


def seat_perspective(jar, rim_aspect: float = 0.30):
    """Flatten the cap ellipse toward the scene camera. The label is not warped."""
    from PIL import Image

    image = jar.convert("RGBA")
    width, height = image.size
    squash = max(0.75, min(1.0, float(rim_aspect) / 0.34))
    band = max(8, int(height * 0.11))
    cap = image.crop((0, 0, width, band))
    cap_h = max(4, int(round(band * squash)))
    cap = cap.resize((width, cap_h), Image.Resampling.LANCZOS)
    narrowed = max(4, int(round(width * (0.92 + 0.08 * squash))))
    pinched = Image.new("RGBA", (width, cap_h), (0, 0, 0, 0))
    cap = cap.resize((narrowed, cap_h), Image.Resampling.LANCZOS)
    pinched.paste(cap, ((width - narrowed) // 2, 0), cap)
    body = image.crop((0, band, width, height))
    out = Image.new("RGBA", (width, cap_h + body.size[1]), (0, 0, 0, 0))
    out.paste(pinched, (0, 0), pinched)
    out.paste(body, (0, cap_h), body)
    return out


def _rgb(image) -> np.ndarray:
    return np.asarray(image.convert("RGB")).astype(np.float32)


def _lum(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _chroma(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=-1) - rgb.min(axis=-1)


def grade_to_scene(jar, plate, rect, light: str = "left"):
    """Match the glass to the table. High-chroma label hue is not rotated."""
    from PIL import Image

    image = jar.convert("RGBA")
    arr = np.asarray(image).astype(np.float32)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    opaque = alpha > 16
    if int(opaque.sum()) < 32 or plate is None:
        return image
    height, width = rgb.shape[:2]
    rgb = _flatten_columns(rgb, opaque)
    surround = _surround(plate, rect)
    if surround is None:
        out = np.concatenate([np.clip(rgb, 0, 255), alpha[..., None]], axis=2).astype(np.uint8)
        return Image.fromarray(out, "RGBA")
    target = float(_lum(surround).mean())
    body = opaque.copy()
    body[: int(height * 0.16), :] = False
    body[int(height * 0.90) :, :] = False
    sample = _lum(rgb)[body] if int(body.sum()) > 30 else _lum(rgb)[opaque]
    bright = sample[sample > 70] if np.any(sample > 70) else sample
    gain = float(np.clip(target / max(float(np.median(bright)), 1.0), 0.55, 1.22))
    # Dark glass stays dark glass. Only the lit label and metal take the exposure.
    protect = np.clip((_lum(rgb) - 36.0) / 80.0, 0.0, 1.0)
    rgb = rgb * (1.0 + (gain - 1.0) * protect[..., None])
    _rolloff_cap(rgb, opaque, target)
    # Pull neon chroma in. Scaling around luminance keeps the hue angle.
    chroma = _chroma(rgb)
    sat = np.where(chroma >= 46.0, 0.64, 0.94).astype(np.float32)
    lum = _lum(rgb)[..., None]
    rgb = lum + (rgb - lum) * sat[..., None]
    clear = _clear_mask(rgb, opaque)
    _warm_clear(rgb, clear, surround)
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)
    shade = (1.06 - 0.14 * xs) if light != "right" else (0.92 + 0.14 * xs)
    rgb = rgb * shade[None, :, None]
    streak = np.exp(-((xs - (0.16 if light != "right" else 0.84)) ** 2) / 0.0035)
    rgb = rgb + streak[None, :, None] * clear[..., None] * 9.0
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)
    ao = 1.0 - 0.22 * np.clip((ys - 0.84) / 0.16, 0.0, 1.0)
    rgb = np.clip(rgb * ao[:, None, None], 0, 255)
    out = np.concatenate([rgb, alpha[..., None]], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _flatten_columns(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """Take out the packshot's left-to-right studio exposure. Hue stays."""
    height, width = rgb.shape[:2]
    lum = _lum(rgb)
    col = np.full(width, np.nan, dtype=np.float32)
    for x in range(width):
        mask = opaque[:, x]
        if int(mask.sum()) > 12:
            col[x] = float(np.median(lum[:, x][mask]))
    if not np.isfinite(col).any():
        return rgb
    filled = col.copy()
    good = np.isfinite(filled)
    filled[~good] = np.interp(np.flatnonzero(~good), np.flatnonzero(good), filled[good])
    kernel = max(9, width // 14)
    smooth = np.convolve(filled, np.ones(kernel, dtype=np.float32) / kernel, mode="same")
    base = float(np.median(smooth))
    factor = np.clip(base / np.maximum(smooth, 1.0), 0.55, 1.35)
    protect = np.clip((_lum(rgb) - 36.0) / 80.0, 0.0, 1.0)
    applied = 1.0 + (factor[None, :] - 1.0) * protect
    return rgb * applied[..., None]


def _clear_mask(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """Glass and metal. Skips brand ink and white label type."""
    lum = _lum(rgb)
    return opaque & (_chroma(rgb) < 34.0) & (lum > 42.0) & (lum < 176.0)


def _rolloff_cap(rgb: np.ndarray, opaque: np.ndarray, target: float) -> None:
    """Pull the packshot's specular cap down into the scene. The label is left alone."""
    height = rgb.shape[0]
    cap = np.zeros(opaque.shape, dtype=bool)
    cap[: max(4, int(height * 0.16)), :] = True
    lum = _lum(rgb)
    ceiling = max(28.0, target * 1.08)
    hot = cap & opaque & (lum > ceiling)
    if not np.any(hot):
        return
    scale = np.ones(lum.shape, dtype=np.float32)
    scale[hot] = ceiling / np.maximum(lum[hot], 1.0)
    rgb *= (1.0 + (scale - 1.0) * 0.92)[..., None]


def _warm_clear(rgb: np.ndarray, clear: np.ndarray, surround: np.ndarray) -> None:
    if int(clear.sum()) < 40:
        return
    src = rgb[clear].mean(axis=0)
    dst = surround.mean(axis=(0, 1))
    delta = (dst - dst.mean()) - (src - src.mean())
    rgb[clear] = np.clip(rgb[clear] + delta, 0, 255)


def _surround(plate, rect):
    """Table pixels beside the jar, not the backdrop above it."""
    rgb = _rgb(plate)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in rect]
    y_a = max(0, y1 - max(24, int((y1 - y0) * 0.28)))
    y_b = min(height, max(y_a + 8, y1 - 4))
    span = max(16, int((x1 - x0) * 0.45))
    patches = []
    if x0 - 8 > 12:
        patches.append(rgb[y_a:y_b, max(0, x0 - span): max(0, x0 - 6)])
    if x1 + 8 < width - 12:
        patches.append(rgb[y_a:y_b, min(width, x1 + 6): min(width, x1 + span)])
    patches = [patch for patch in patches if patch.size > 48]
    if not patches:
        return None
    return patches[0] if len(patches) == 1 else np.concatenate(patches, axis=1)


def _sample(image, box) -> np.ndarray | None:
    rgb = _rgb(image)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 - x0 < 6 or y1 - y0 < 4:
        return None
    return rgb[y0:y1, x0:x1]


def _nearest_prop_height(scene, width: int, height: int) -> float:
    """Tallest photographed prop in the frame. A synthetic scale box is not a prop."""
    from content_generator.creative.lifestyle_scene import frame_props

    tallest = 0.0
    for prop in frame_props(scene, width, height):
        _x0, y0, _x1, y1 = prop["box"]
        visible = min(float(y1), float(height)) - max(float(y0), 0.0)
        if visible > tallest:
            tallest = visible
    return tallest


def _label_sharpness(image, box) -> float:
    """Laplacian variance of the label, where the words have to stay readable."""
    from PIL import ImageFilter, ImageStat

    x0, y0, x1, y1 = [int(v) for v in box]
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    crop = image.crop((
        x0 + int(width * 0.18),
        y0 + int(height * 0.36),
        x0 + int(width * 0.82),
        y0 + int(height * 0.74),
    )).convert("L")
    if crop.size[0] < 8 or crop.size[1] < 8:
        return 0.0
    kernel = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)
    return float(ImageStat.Stat(crop.filter(kernel)).var[0])


def naturalism_issues(image, jar_bbox, scene) -> list[str]:
    """Fail when the jar ignores the prop's size, the frame edge, or the local light."""
    issues = []
    if image is None or not scene:
        return issues
    width, height = image.size
    try:
        x0, y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return ["jar_bbox_invalid"]
    if x0 < width * EDGE_X or x1 > width * (1 - EDGE_X):
        issues.append("jar_at_frame_edge")
    if y0 < height * 0.03 or y1 > height * 0.97:
        issues.append("jar_at_frame_edge")
    lo, hi = hero_bounds(width, height)
    frac = (y1 - y0) / max(1, height)
    if frac < lo - 0.005 or frac > hi + 0.02:
        issues.append("jar_not_hero")
    prop_h = _nearest_prop_height(scene, width, height)
    if prop_h > 8 and (y1 - y0) < prop_h:
        issues.append("smaller_than_prop")
    label = _label_sharpness(image, (x0, y0, x1, y1))
    if label < LABEL_LAPLACIAN_MIN:
        issues.append("label_soft")
    glass = _glass(image, (x0, y0, x1, y1))
    table = _surround(image, (x0, y0, x1, y1))
    if glass is not None and table is not None:
        table_lum = float(_lum(table).mean())
        if abs(float(_lum(glass).mean()) - table_lum) > _LUM_TOL:
            issues.append("light_mismatch")
        jar_cast = float(glass[..., 0].mean() - glass[..., 2].mean())
        tab_cast = float(table[..., 0].mean() - table[..., 2].mean())
        if abs(jar_cast - tab_cast) > _CAST_TOL:
            issues.append("white_balance_mismatch")
    if not _shadow_agrees(image, (x0, y0, x1, y1), scene.get("light", "left")):
        issues.append("shadow_direction")
    return issues


def _glass(image, box):
    """Clear glass and metal inside the jar. Brand ink is not the white balance."""
    rgb = _rgb(image)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    crop = rgb[y0:y1, x0:x1]
    rows, cols = crop.shape[:2]
    cap = crop[: max(6, int(rows * 0.10)), int(cols * 0.12): max(int(cols * 0.12) + 6, int(cols * 0.88))]
    if cap.size < 30:
        return None
    lit = _lum(cap)
    # Lit metal only. The side columns are brand ink and stay out of the check.
    picked = cap[lit >= float(np.percentile(lit, 60))]
    if picked.shape[0] < 20:
        picked = cap.reshape(-1, 3)
    return picked.reshape(-1, 1, 3)


def _blur_axis(arr: np.ndarray, sigma: float, axis: int) -> np.ndarray:
    sigma = max(0.6, float(sigma))
    radius = max(1, int(round(sigma * 3)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    if axis == 1:
        return np.stack([
            np.convolve(np.pad(arr[y], radius, mode="edge"), kernel, mode="valid")
            for y in range(arr.shape[0])
        ])
    return np.stack([
        np.convolve(np.pad(arr[:, col], radius, mode="edge"), kernel, mode="valid")
        for col in range(arr.shape[1])
    ], axis=1)


def paint_contact_shadow(canvas, cx: int, by: int, foot_w: int, light: str = "left"):
    """Ellipse under the glass foot, Gaussian-feathered, plus a cast lobe off the key light."""
    from PIL import Image, ImageDraw

    image = canvas.convert("RGBA")
    foot_w = max(12, int(foot_w))
    contact = Image.new("L", image.size, 0)
    cast = Image.new("L", image.size, 0)
    rx = max(8, int(foot_w * 0.48))
    ry = max(4, int(foot_w * 0.04))
    # Back half tucks under the glass so the base touches the darkest point.
    ImageDraw.Draw(contact).ellipse([cx - rx, by - ry, cx + rx, by + 4], fill=255)
    direction = -1 if light == "right" else 1
    shift = int(foot_w * 0.34) * direction
    crx = max(8, int(foot_w * 0.28))
    cry = max(8, int(foot_w * 0.11))
    ImageDraw.Draw(cast).ellipse([cx + shift - crx, by - 2, cx + shift + crx, by + cry], fill=220)
    sx = max(3.5, foot_w * 0.035)
    core = np.asarray(contact).astype(np.float32) / 255.0
    lobe = np.asarray(cast).astype(np.float32) / 255.0
    core = _blur_axis(_blur_axis(core, 2.6, 0), sx, 1)
    lobe = _blur_axis(_blur_axis(lobe, 3.4, 0), sx * 1.15, 1)
    shade = np.clip(np.maximum(core, lobe * 0.82), 0, 1)
    arr = np.asarray(image).astype(np.float32)
    arr[..., :3] *= (1.0 - shade[..., None] * 0.78)
    arr[..., :3] = np.clip(arr[..., :3], 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def shadow_hard_edge(image, jar_bbox) -> bool:
    """A straight luminance cliff under the base. A feathered ellipse does not spike."""
    try:
        x0, _y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return False
    lum = _lum(_rgb(image))
    height, width = lum.shape
    jar_w = max(1, x1 - x0)
    y_a = min(height - 2, max(0, y1 + 1))
    y_b = min(height, y_a + max(12, min(18, int(jar_w * 0.045))))
    x_a = max(0, x0)
    x_b = min(width, x1)
    if y_b - y_a < 6 or x_b - x_a < 16:
        return False
    crop = lum[y_a:y_b, x_a:x_b]
    gy = np.abs(np.diff(crop, axis=0))
    gx = np.abs(np.diff(crop, axis=1))

    def _run(flags) -> int:
        best = run = 0
        for value in flags:
            run = run + 1 if value else 0
            if run > best:
                best = run
        return best

    span = x_b - x_a
    horiz = max(_run(row > 22.0) for row in gy) / span
    vert = max(_run(col > 22.0) for col in gx.T)
    return horiz > 0.40 or vert >= (y_b - y_a - 2)


def _shadow_agrees(image, box, light: str) -> bool:
    x0, _y0, x1, y1 = box
    width = max(1, x1 - x0)
    off = max(8, int(width * 0.20))
    cx = (x0 + x1) // 2
    y_a, y_b = y1 + 2, y1 + 16
    half = max(6, int(width * 0.09))
    shadow_x = cx + off if light != "right" else cx - off
    lit_x = cx - off if light != "right" else cx + off
    shadow = _sample(image, (shadow_x - half, y_a, shadow_x + half, y_b))
    lit = _sample(image, (lit_x - half, y_a, lit_x + half, y_b))
    if shadow is None or lit is None:
        return True
    return float(_lum(shadow).mean()) + 3.0 < float(_lum(lit).mean())
