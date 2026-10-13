"""Photographic lifestyle plates. The product jar is never redrawn onto them."""
from __future__ import annotations

import os

SCENES = (
    {"id": "kitchen_morning", "file": "brand_assets/scenes/kitchen_morning.jpg"},
    {"id": "cafe_table", "file": "brand_assets/scenes/cafe_table.jpg"},
    {"id": "work_desk", "file": "brand_assets/scenes/work_desk.jpg"},
    {"id": "balcony_sunrise", "file": "brand_assets/scenes/balcony_sunrise.jpg"},
)
_IDS = {scene["id"] for scene in SCENES}
_MIN_TEXTURE = 9.0


def scene_for_day(day: int) -> dict:
    """Rotate the setting each day. The jar photo does not change with the scene."""
    return SCENES[int(day or 0) % len(SCENES)]


def _root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_plate(width: int, height: int, day: int = 0, blur: float = 1.15):
    """Cover-crop a real plate, soften only the background, and scrim the type zones."""
    from PIL import Image, ImageFilter

    scene = scene_for_day(day)
    path = os.path.join(_root(), scene["file"])
    if not os.path.exists(path):
        return None, None
    plate = Image.open(path).convert("RGB")
    scale = max(width / plate.width, height / plate.height)
    resized = (
        plate.resize((max(1, int(round(plate.width * scale))), max(1, int(round(plate.height * scale)))), Image.Resampling.LANCZOS)
        if scale < 0.999 or scale > 1.001
        else plate
    )
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    frame = resized.crop((left, top, left + width, top + height))
    if blur and blur > 0.2:
        frame = frame.filter(ImageFilter.GaussianBlur(radius=blur))
    return _scrim(frame), scene["id"]


def _scrim(image):
    """Darken only the top and bottom bands so type reads. The jar is pasted after this."""
    from PIL import Image

    width, height = image.size
    mask = Image.new("L", (1, height), 0)
    top_end = int(height * 0.34)
    bot_start = int(height * 0.86)
    span = max(1, height - bot_start)
    for y in range(height):
        if y < top_end:
            alpha = int(200 * (1 - y / max(1, top_end)))
        elif y > bot_start:
            alpha = int(160 * (y - bot_start) / span)
        else:
            alpha = 0
        mask.putpixel((0, y), alpha)
    mask = mask.resize((width, height))
    dark = Image.new("RGB", (width, height), (12, 8, 6))
    return Image.composite(dark, image, mask)


def match_light(jar, plate):
    """Tint the real jar toward the counter light. No blur, no redraw."""
    from PIL import Image, ImageStat

    if jar is None or plate is None:
        return jar
    width, height = plate.size
    sample = plate.crop((width // 4, int(height * 0.62), 3 * width // 4, int(height * 0.82)))
    mean = ImageStat.Stat(sample).mean
    warmth = tuple(max(0.94, min(1.06, channel / 150.0)) for channel in mean[:3])
    bands = jar.convert("RGBA").split()
    shifted = [
        band.point(lambda value, gain=warmth[index]: max(0, min(255, int(value * gain))))
        for index, band in enumerate(bands[:3])
    ]
    return Image.merge("RGBA", (*shifted, bands[3]))


def product_rect(width: int, height: int, text_bottom: int, cta_top: int, zone) -> tuple[int, int, int, int]:
    """Cap the jar and sit its base on the counter, above the CTA."""
    story = height > width * 1.3
    max_h = int(height * (0.38 if story else 0.44))
    max_w = int(width * 0.40)
    base = int(height * (0.815 if story else 0.78))
    base = min(base, int(cta_top) - 36, height - 52)
    top = max(int(text_bottom) + 16, base - max_h)
    if base - top < int(height * 0.30):
        top = max(int(text_bottom) + 8, base - int(height * 0.30))
    left = max(int(zone[0]), (width - max_w) // 2)
    right = min(int(zone[2]), left + max_w)
    return (left, top, right, max(top + 80, base))


def seat_base(fitted):
    """Darken only the glass foot so it meets the counter. The label is not filtered."""
    fitted = fitted.convert("RGBA")
    band = max(8, int(fitted.height * 0.05))
    pixels = fitted.load()
    start = fitted.height - band
    for y in range(start, fitted.height):
        gain = 1 - 0.28 * ((y - start) / band)
        for x in range(fitted.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 8:
                continue
            pixels[x, y] = (int(red * gain), int(green * gain), int(blue * gain), alpha)
    return fitted


def ground_product(canvas, fitted, jx: int, jy: int):
    """A short soft shadow tucked under the glass. No floor disc and no dropped oval."""
    base = canvas.convert("RGBA")
    alpha = fitted.split()[-1]
    width, height = fitted.size
    foot_y = height - 1
    for y in range(height - 1, int(height * 0.7), -1):
        if any(alpha.getpixel((x, y)) > 20 for x in range(0, width, 3)):
            foot_y = y
            break
    foot = [x for x in range(width) if alpha.getpixel((x, foot_y)) > 20]
    if foot:
        foot_x0, foot_x1 = foot[0], foot[-1]
    else:
        foot_x0, foot_x1 = int(width * 0.35), int(width * 0.65)
    foot_w = max(12, foot_x1 - foot_x0)
    cx = jx + (foot_x0 + foot_x1) // 2
    by = jy + foot_y
    # Darken the counter directly under the glass. A separate oval reads as a floating disc.
    sw = max(20, int(foot_w * 0.92))
    sh = max(8, min(12, int(height * 0.02)))
    pixels = base.load()
    rx = sw / 2
    for dy in range(1, sh + 1):
        half = rx * (1 - (dy / (sh + 1)) ** 2) ** 0.5
        gain = 0.30 + 0.64 * (dy / sh)
        y = by + dy
        if y < 0 or y >= base.size[1]:
            continue
        x0 = max(0, int(cx - half))
        x1 = min(base.size[0], int(cx + half) + 1)
        for x in range(x0, x1):
            edge = abs(x - cx) / max(1.0, half)
            soft = gain + (1 - gain) * (edge ** 1.5)
            red, green, blue, alpha = pixels[x, y]
            pixels[x, y] = (int(red * soft), int(green * soft), int(blue * soft), alpha)
    return base


def counter_texture(image, jar_bbox) -> float:
    """Std-dev of the counter beside the jar. A flat gradient scores near zero."""
    from PIL import ImageStat

    width, height = image.size
    try:
        x0, _y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        x0, x1, y1 = width // 3, 2 * width // 3, int(height * 0.72)
    y_a = max(0, y1 - 130)
    y_b = max(y_a + 8, min(height, y1 - 6))

    def _std(box) -> float:
        crop = image.crop(box).convert("L")
        if crop.size[0] < 8 or crop.size[1] < 8:
            return 0.0
        return float(ImageStat.Stat(crop).stddev[0])

    patches = (
        (max(0, x0 - 160), y_a, max(8, x0 - 8), y_b),
        (max(0, x0 - 340), y_a, max(8, x0 - 36), y_b),
        (min(width - 8, x1 + 8), y_a, min(width, x1 + 160), y_b),
        (min(width - 8, x1 + 36), y_a, min(width, x1 + 340), y_b),
    )
    return max(_std(box) for box in patches)


def contact_depth(image, jar_bbox) -> float:
    """How much darker the contact line is than the counter beside it."""
    from PIL import ImageStat

    width, height = image.size
    try:
        x0, _y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return 0.0
    cx0 = x0 + int((x1 - x0) * 0.35)
    cx1 = x0 + int((x1 - x0) * 0.65)

    def _mean(box) -> float | None:
        if box[2] - box[0] < 8 or box[3] - box[1] < 3:
            return None
        if box[1] < 0 or box[3] > height or box[0] < 0 or box[2] > width:
            return None
        return float(ImageStat.Stat(image.crop(box).convert("L")).mean[0])

    # The contact line against the counter a few pixels past that shadow.
    near = _mean((cx0, y1 + 1, cx1, y1 + 4))
    past = _mean((cx0, y1 + 6, cx1, y1 + 11))
    if near is None or past is None:
        return 0.0
    return past - near


def realism_issues(image, jar_bbox, scene_id, *, contact_shadow: bool = True) -> list[str]:
    """Fail closed when the frame is a flat backdrop, an unknown plate, or an ungrounded jar."""
    issues = []
    if scene_id not in _IDS:
        issues.append("lifestyle_scene_missing")
    if not contact_shadow:
        issues.append("contact_shadow_missing")
    elif image is not None and contact_depth(image, jar_bbox) < 6.0:
        issues.append("contact_shadow_missing")
    if image is not None and counter_texture(image, jar_bbox) < _MIN_TEXTURE:
        issues.append("flat_background")
    return issues
