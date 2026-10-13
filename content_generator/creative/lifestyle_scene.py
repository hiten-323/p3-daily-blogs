"""Photographic lifestyle plates. The product jar is never redrawn onto them."""
from __future__ import annotations

import os

# Prop boxes are pixels of the 720×1280 plate. "side" is where the jar sits.
SCENES = (
    {
        "id": "kitchen_morning",
        "file": "brand_assets/scenes/kitchen_morning.jpg",
        "size": (720, 1280),
        "props": (),
    },
    {
        "id": "cafe_table",
        "file": "brand_assets/scenes/cafe_table.jpg",
        "size": (720, 1280),
        "props": ({"id": "cup", "box": (394, 644, 610, 896), "side": "left"},),
    },
    {
        "id": "work_desk",
        "file": "brand_assets/scenes/work_desk.jpg",
        "size": (720, 1280),
        "props": ({"id": "laptop", "box": (148, 470, 498, 636), "side": "right"},),
    },
    {
        "id": "balcony_sunrise",
        "file": "brand_assets/scenes/balcony_sunrise.jpg",
        "size": (720, 1280),
        "props": (
            {"id": "plant_left", "box": (0, 630, 236, 880), "side": "right"},
            {"id": "plant_right", "box": (600, 980, 720, 1120), "side": "left"},
        ),
    },
)
_IDS = {scene["id"] for scene in SCENES}
_MIN_TEXTURE = 9.0
_FLOOR_DISC_DELTA = 18.0


def scene_for_day(day: int) -> dict:
    """Rotate the setting each day. The jar photo does not change with the scene."""
    return SCENES[int(day or 0) % len(SCENES)]


def scene_by_id(scene_id: str | None) -> dict | None:
    for scene in SCENES:
        if scene["id"] == scene_id:
            return scene
    return None


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


def frame_props(scene, width: int, height: int) -> list[dict]:
    """Prop boxes in the cover-cropped frame. The same crop load_plate uses."""
    if not scene:
        return []
    src_w, src_h = scene.get("size", (720, 1280))
    scale = max(width / src_w, height / src_h)
    left = (src_w * scale - width) / 2
    top = (src_h * scale - height) / 2
    mapped = []
    for prop in scene.get("props", ()):
        x0, y0, x1, y1 = prop["box"]
        box = (
            int(round(x0 * scale - left)),
            int(round(y0 * scale - top)),
            int(round(x1 * scale - left)),
            int(round(y1 * scale - top)),
        )
        if box[2] <= 0 or box[3] <= 0 or box[0] >= width or box[1] >= height:
            continue
        mapped.append({"id": prop["id"], "side": prop.get("side", "left"), "box": box})
    return mapped


def props_overlap(jar_bbox, props) -> list[str]:
    """Prop ids whose box intersects the jar. Touching edges do not count."""
    try:
        x0, y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return []
    hits = []
    for prop in props or []:
        a0, b0, a1, b1 = prop["box"]
        if x0 < a1 and x1 > a0 and y0 < b1 and y1 > b0:
            hits.append(prop["id"])
    return hits


def _free_spans(limit_l: int, limit_r: int, blocked: list[tuple[int, int]]) -> list[tuple[int, int]]:
    spans = [(limit_l, limit_r)]
    for b0, b1 in sorted(blocked):
        nxt = []
        for s0, s1 in spans:
            if b1 <= s0 or b0 >= s1:
                nxt.append((s0, s1))
                continue
            if s0 < b0:
                nxt.append((s0, b0))
            if b1 < s1:
                nxt.append((b1, s1))
        spans = [(a, b) for a, b in nxt if b - a >= 8]
    return spans


def place_product(scene, width, height, text_bottom, cta_top, zone, jar_size, attempt: int = 0) -> tuple[int, int, int, int]:
    """Sit the jar beside scene props. The base stays on the counter, in front of them."""
    slot = product_rect(width, height, text_bottom, cta_top, zone)
    base = slot[3]
    max_h = max(80, base - slot[1])
    max_w = max(80, slot[2] - slot[0])
    jar_w, jar_h = [max(1, int(v)) for v in jar_size]
    props = frame_props(scene, width, height)
    gap = max(24, int(width * 0.034))
    limit_l, limit_r = int(zone[0]), int(zone[2])
    full = min(1.0, max_w / jar_w, max_h / jar_h)
    min_h = int(height * 0.285)
    scales = [full]
    for prop in props:
        clear_h = base - prop["box"][3]
        if min_h <= clear_h < jar_h * full:
            scales.append(clear_h / jar_h)
    for scale in sorted(set(scales), reverse=True):
        jw = max(1, int(round(jar_w * scale)))
        jh = max(1, int(round(jar_h * scale)))
        if jh < min_h:
            continue
        top = base - jh
        blocked = []
        for prop in props:
            a0, b0, a1, b1 = prop["box"]
            if top >= b1 or base <= b0:
                continue
            blocked.append((a0 - gap, a1 + gap))
        placed = None
        for s0, s1 in _free_spans(limit_l, limit_r, blocked):
            if s1 - s0 < jw:
                continue
            on_right = any(b0 >= s1 - 2 for b0, _b1 in blocked)
            on_left = any(b1 <= s0 + 2 for _b0, b1 in blocked)
            if on_right and not on_left:
                jx = s1 - jw
            elif on_left and not on_right:
                jx = s0
            else:
                jx = s0 + (s1 - s0 - jw) // 2
            beside = 1 if on_left or on_right else 0
            if placed is None or (beside, s1 - s0) > placed[0]:
                placed = ((beside, s1 - s0), jx, s0, s1)
        if placed:
            jx, s0, s1 = placed[1], placed[2], placed[3]
            # The next try sits at the other end of the same clear span.
            if int(attempt) % 2 == 1 and s1 - s0 >= jw:
                alt = s0 if jx > s0 + 4 else s1 - jw
                if s0 <= alt <= s1 - jw:
                    jx = alt
            return (jx, top, jx + jw, base)
    return slot


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
    # The glass foot is narrower than the label. Sample under the foot, not the whole jar.
    cx0 = x0 + int((x1 - x0) * 0.46)
    cx1 = x0 + int((x1 - x0) * 0.54)

    def _mean(box) -> float | None:
        if box[2] - box[0] < 8 or box[3] - box[1] < 3:
            return None
        if box[1] < 0 or box[3] > height or box[0] < 0 or box[2] > width:
            return None
        return float(ImageStat.Stat(image.crop(box).convert("L")).mean[0])

    # Darkest at the glass, then the counter. Use the brightest step so a
    # floor that darkens further down does not cancel the contact shadow.
    near = _mean((cx0, y1 + 1, cx1, y1 + 4))
    later = [
        _mean((cx0, y1 + 4, cx1, y1 + 7)),
        _mean((cx0, y1 + 6, cx1, y1 + 9)),
        _mean((cx0, y1 + 8, cx1, y1 + 11)),
    ]
    later = [value for value in later if value is not None]
    if near is None or not later:
        return 0.0
    return max(later) - near


def floor_disc_delta(image, jar_bbox) -> float:
    """How much brighter a wide band under the jar is than the counter beside it.

    The band is 40px tall and 1.3x the jar width. A studio ellipse is brighter than
    the counter. A contact shadow is darker, so its delta is small or negative.
    """
    from PIL import ImageStat

    width, height = image.size
    try:
        x0, _y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return 0.0
    jar_w = max(1, x1 - x0)
    band_w = max(jar_w + 8, int(jar_w * 1.3))
    cx = (x0 + x1) // 2
    bx0 = max(0, cx - band_w // 2)
    bx1 = min(width, cx + band_w // 2)
    by0 = y1 + 1
    by1 = min(height, y1 + 41)
    if by1 - by0 < 16 or bx1 - bx0 < 16:
        return 0.0

    def _mean(box) -> float | None:
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            return None
        if box[1] < 0 or box[3] > height or box[0] < 0 or box[2] > width:
            return None
        return float(ImageStat.Stat(image.crop(box).convert("L")).mean[0])

    band = _mean((bx0, by0, bx1, by1))
    side_w = max(24, min(120, jar_w // 5))
    left = _mean((max(0, bx0 - side_w - 8), by0, max(0, bx0 - 8), by1))
    right = _mean((min(width, bx1 + 8), by0, min(width, bx1 + 8 + side_w), by1))
    sides = [value for value in (left, right) if value is not None]
    if band is None or not sides:
        return 0.0
    return band - (sum(sides) / len(sides))


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
    if image is not None and floor_disc_delta(image, jar_bbox) > _FLOOR_DISC_DELTA:
        issues.append("floor_disc")
    if image is not None and props_overlap(jar_bbox, frame_props(scene_by_id(scene_id), image.size[0], image.size[1])):
        issues.append("prop_overlap")
    return issues
