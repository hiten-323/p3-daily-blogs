"""Photographic lifestyle plates. The product jar is never redrawn onto them."""
from __future__ import annotations

import os

# Prop boxes are pixels of the 720×1280 plate. "side" is where the jar sits.
# height_cm is the real object. depth < 1 means the jar is slightly further away.
SCENES = (
    {
        "id": "kitchen_morning",
        "file": "brand_assets/scenes/kitchen_morning.jpg",
        "size": (720, 1280),
        "light": "left",
        "rim": 0.32,
        "props": (),
        "scale_ref": {"box": (280, 800, 470, 1020), "height_cm": 9.5, "depth": 1.0, "lift": 0.0},
    },
    {
        "id": "cafe_table",
        "file": "brand_assets/scenes/cafe_table.jpg",
        "size": (720, 1280),
        "light": "left",
        "rim": 0.22,
        "props": ({
            "id": "cup", "box": (394, 644, 610, 896), "side": "left",
            "height_cm": 9.5, "depth": 0.96, "lift": 0.08,
        },),
    },
    {
        "id": "work_desk",
        "file": "brand_assets/scenes/work_desk.jpg",
        "size": (720, 1280),
        "light": "left",
        "rim": 0.30,
        "props": ({
            "id": "laptop", "box": (148, 470, 498, 636), "side": "right",
            "height_cm": 16.5, "depth": 1.65, "lift": -1.0, "behind": True,
        },),
    },
    {
        "id": "balcony_sunrise",
        "file": "brand_assets/scenes/balcony_sunrise.jpg",
        "size": (720, 1280),
        "light": "right",
        "rim": 0.30,
        "props": (
            {"id": "plant_left", "box": (0, 630, 236, 880), "side": "right"},
            {"id": "plant_right", "box": (600, 980, 720, 1120), "side": "left"},
        ),
        "scale_ref": {"box": (320, 860, 500, 1060), "height_cm": 9.5, "depth": 1.0, "lift": 0.0},
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
    from content_generator.creative.scene_natural import frame_crop
    scale, crop_left, crop_top = frame_crop(scene, width, height)
    resized = (
        plate.resize((max(1, int(round(plate.width * scale))), max(1, int(round(plate.height * scale)))), Image.Resampling.LANCZOS)
        if scale < 0.999 or scale > 1.001
        else plate
    )
    left = max(0, int(round(crop_left)))
    top = max(0, int(round(crop_top)))
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
    from content_generator.creative.scene_natural import map_box
    mapped = []
    for prop in scene.get("props", ()):
        x0, y0, x1, y1 = map_box(scene, prop["box"], width, height)
        box = (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
        if box[2] <= 0 or box[3] <= 0 or box[0] >= width or box[1] >= height:
            continue
        mapped.append({
            "id": prop["id"],
            "side": prop.get("side", "left"),
            "behind": bool(prop.get("behind")),
            "box": box,
        })
    return mapped


def props_overlap(jar_bbox, props) -> list[str]:
    """Prop ids whose box intersects the jar. A backdrop the jar stands in front of does not count."""
    try:
        x0, y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return []
    jar_h = max(1, y1 - y0)
    hits = []
    for prop in props or []:
        a0, b0, a1, b1 = prop["box"]
        if not (x0 < a1 and x1 > a0 and y0 < b1 and y1 > b0):
            continue
        if prop.get("behind") and y1 > b1 and (y1 - b1) >= 0.28 * jar_h:
            continue
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


def _place_side(scene) -> str:
    for prop in scene.get("props", ()) if scene else ():
        if prop.get("height_cm") or prop.get("side"):
            return prop.get("side") or "left"
    return "center"


def place_product(scene, width, height, text_bottom, cta_top, zone, jar_size, attempt: int = 0) -> tuple[int, int, int, int]:
    """Put the jar in the foreground, larger than the props, on a third."""
    from content_generator.creative.scene_natural import hero_bounds, hero_height, map_box, scale_ref

    slot = product_rect(width, height, text_bottom, cta_top, zone)
    ref = scale_ref(scene)
    if not ref:
        return slot
    box = map_box(scene, ref["box"], width, height)
    ref_h = max(1.0, box[3] - box[1])
    native_w, native_h = [max(1, int(v)) for v in jar_size]
    lo, _hi = hero_bounds(width, height)
    jar_h = hero_height(width, height, ref_h, native_h)
    jar_w = max(1, int(round(jar_h * native_w / native_h)))
    margin_x = int(width * 0.08) + 3
    margin_y = int(height * 0.035)
    max_base = min(int(cta_top) - 22, height - margin_y)
    min_top = int(text_bottom) + 6
    # Foreground, but above the counter's front edge and the bottom scrim.
    base = int(round(box[3] + ref_h * 0.04))
    base = max(base, int(height * 0.68))
    base = min(base, max_base, int(height * 0.78))
    top = base - jar_h
    if top < min_top:
        top = min_top
        room = max(1, max_base - top)
        if room < jar_h:
            jar_h = room
            jar_w = max(1, int(round(jar_h * native_w / native_h)))
        base = top + jar_h
    props = frame_props(scene, width, height)
    gap = max(18, int(width * 0.028))
    limit_l = max(margin_x, int(zone[0]))
    limit_r = min(width - margin_x, int(zone[2]))
    blocked = []
    for prop in props:
        if not _prop_blocks(prop, top, base):
            continue
        a0, _b0, a1, _b1 = prop["box"]
        blocked.append((a0 - gap, a1 + gap))
    spans = _free_spans(limit_l, limit_r, blocked)
    widest = max((b - a for a, b in spans), default=0)
    floor_h = max(int(height * lo), int(ref_h) + 1)
    if widest > 48 and jar_w > widest:
        fit_h = int(jar_h * (widest - 4) / jar_w)
        if fit_h >= floor_h:
            jar_h = fit_h
            jar_w = max(1, int(round(jar_h * native_w / native_h)))
            top = base - jar_h
    side = _place_side(scene)
    thirds = (width / 3, width / 2, 2 * width / 3)
    order = {"left": (0, 1, 2), "right": (2, 1, 0)}.get(side, (1, 0, 2))
    if int(attempt) % 2 == 1:
        order = tuple(reversed(order))
    limit_l = max(margin_x, int(zone[0]))
    limit_r = min(width - margin_x, int(zone[2]))
    for index in order:
        jx = int(thirds[index] - jar_w / 2)
        jx = max(limit_l, min(jx, limit_r - jar_w))
        if _clear_of_props(jx, jar_w, top, base, props, gap):
            return (jx, top, jx + jar_w, base)
    blocked = []
    for prop in props:
        if not _prop_blocks(prop, top, base):
            continue
        a0, _b0, a1, _b1 = prop["box"]
        blocked.append((a0 - gap, a1 + gap))
    for s0, s1 in _free_spans(limit_l, limit_r, blocked):
        if s1 - s0 < jar_w:
            continue
        jx = s0 if side == "left" else s1 - jar_w if side == "right" else s0 + (s1 - s0 - jar_w) // 2
        jx = max(s0, min(jx, s1 - jar_w))
        return (jx, top, jx + jar_w, base)
    return slot


def _prop_blocks(prop, top, base) -> bool:
    """A jar standing in front of a backdrop prop is not blocked by it."""
    _a0, b0, _a1, b1 = prop["box"]
    if top >= b1 or base <= b0:
        return False
    jar_h = max(1, base - top)
    return not (base > b1 and (base - b1) >= 0.45 * jar_h)


def _clear_of_props(jx, jar_w, top, base, props, gap) -> bool:
    for prop in props:
        if not _prop_blocks(prop, top, base):
            continue
        a0, _b0, a1, _b1 = prop["box"]
        if jx < a1 + gap and jx + jar_w > a0 - gap:
            return False
    return True


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


def ground_product(canvas, fitted, jx: int, jy: int, light: str = "left"):
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
    cx = jx + (foot_x0 + foot_x1) // 2
    by = jy + foot_y
    # A narrow foot on an even counter. A wider shade only where the centre is sunlit.
    from content_generator.creative.scene_natural import shade_plan
    hold, band = shade_plan(base, cx, by, width)
    shift = int(width * 0.26) * (-1 if light == "right" else 1)
    pixels = base.load()
    for dy in range(1, 42):
        gain = 0.34 + (hold - 0.34) * min(1.0, (dy - 1) / 6.0)
        y = by + dy
        if y < 0 or y >= base.size[1]:
            continue
        x0 = max(0, int(cx - band / 2))
        x1 = min(base.size[0], int(cx + band / 2) + 1)
        foot = width * 0.14
        for x in range(x0, x1):
            applied = gain * (0.55 if dy <= 4 and abs(x - cx) < foot else 1.0)
            red, green, blue, alpha = pixels[x, y]
            pixels[x, y] = (int(red * applied), int(green * applied), int(blue * applied), alpha)
    lobe = max(18, int(width * 0.50))
    lx = cx + shift
    reach = 20
    for dy in range(1, reach + 1):
        half = (lobe / 2) * (1 - (dy / (reach + 1)) ** 2) ** 0.5
        gain = 0.22 + 0.55 * (dy / reach)
        y = by + dy
        if y < 0 or y >= base.size[1]:
            continue
        x0 = max(0, int(lx - half))
        x1 = min(base.size[0], int(lx + half) + 1)
        for x in range(x0, x1):
            edge = abs(x - lx) / max(1.0, half)
            soft = gain + (1 - gain) * (edge ** 1.35)
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
    if image is not None:
        from content_generator.creative.scene_natural import naturalism_issues
        issues.extend(naturalism_issues(image, jar_bbox, scene_by_id(scene_id)))
    return issues
