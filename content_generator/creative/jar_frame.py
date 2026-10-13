"""Sharp, fully visible product frames for Stories, feed posts, and carousels.

Pastes the highest-resolution complete front-of-jar photo at scale <= 1.
Contact shadow is filtered on its own layer. The product layer is never blurred.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

JAR_LAPLACIAN_MIN = 80.0
MIN_JAR_HEIGHT_RATIO = 0.28
FRAME_EDGE_PX = 2
SOURCE_EDGE_PX = 12

_SAFE = {
    "story": (0.130, 0.146, 0.060),
    "feed": (0.055, 0.085, 0.055),
    "carousel": (0.055, 0.085, 0.055),
}


def safe_zone(width: int, height: int, format_name: str = "feed") -> tuple[int, int, int, int]:
    """Inclusive content box that clears Stories UI and feed chrome."""
    fmt = format_name if format_name in _SAFE else ("story" if height > width * 1.3 else "feed")
    top_f, bot_f, side_f = _SAFE[fmt]
    side = max(24, int(width * side_f))
    top = max(36, int(height * top_f))
    bottom = max(48, int(height * bot_f))
    return (side, top, width - side, height - bottom)


def _laplacian_variance(image) -> float:
    from PIL import ImageFilter, ImageStat

    gray = image.convert("L")
    kernel = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)
    response = gray.filter(kernel)
    return float(ImageStat.Stat(response).var[0])


def _content_metrics(path: str) -> dict | None:
    from PIL import Image

    try:
        im = Image.open(path).convert("RGB")
    except Exception as exc:
        logger.debug("[jar_frame] unreadable %s: %s", path, exc)
        return None
    width, height = im.size
    pixels = im.load()
    min_x, min_y, max_x, max_y = width, height, 0, 0
    found = False
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            r, g, b = pixels[x, y]
            if min(r, g, b) < 230:
                found = True
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if not found:
        return None
    box = (min_x, min_y, min(width, max_x + 2), min(height, max_y + 2))
    jar_w = max(1, box[2] - box[0])
    jar_h = max(1, box[3] - box[1])
    label = im.crop((
        box[0] + int(jar_w * 0.2),
        box[1] + int(jar_h * 0.25),
        box[0] + int(jar_w * 0.8),
        box[1] + int(jar_h * 0.7),
    ))
    margin = min(box[0], box[1], width - 1 - (box[2] - 1), height - 1 - (box[3] - 1))
    return {
        "path": path,
        "margin": margin,
        "area": jar_w * jar_h,
        "lap": _laplacian_variance(label),
        "native": (jar_w, jar_h),
    }


def product_slug(product) -> str | None:
    key = " ".join(str(product or "").strip().lower().replace("_", " ").replace("-", " ").split())
    if not key or ("gourmet duo" in key and "ultra" in key):
        return None
    if "ultra" in key:
        return "ultra_blend"
    if "premium agglomerate" in key or key == "prima" or key.startswith("prima "):
        return "prima"
    for slug in ("purista", "purica", "bold"):
        if slug in key:
            return slug
    return None


def select_front_asset(product=None) -> dict | None:
    """Highest-resolution complete front photo for this jar.

    Complete means the product pixels are inset from every source edge.
    Score is native jar area times label sharpness, so a larger soft file
    does not beat a smaller sharp one, and an edge-cropped file is skipped
    while any complete front exists.
    """
    from content_generator.creative.real_jar_composer import _all_jar_photos

    slug = product_slug(product)
    rows = []
    for path in _all_jar_photos():
        if not path.lower().endswith("_front.png"):
            continue
        if slug and f"_{slug}_" not in path.lower():
            continue
        if slug is None and "ultra" in path.lower():
            continue
        metrics = _content_metrics(path)
        if metrics:
            rows.append(metrics)
    if slug and not rows:
        return None
    complete = [row for row in rows if row["margin"] >= SOURCE_EDGE_PX]
    pool = complete or rows
    if not pool:
        return None
    pool.sort(key=lambda row: (row["area"] * row["lap"], row["area"]), reverse=True)
    chosen = pool[0]
    if chosen["margin"] < SOURCE_EDGE_PX:
        logger.warning(
            "[jar_frame] every front photo for %s touches the source edge; using %s",
            slug or "pure", os.path.basename(chosen["path"]),
        )
    return chosen


def load_native_jar(product=None):
    """RGBA jar at native resolution, white sweep removed, plus the source path."""
    from PIL import Image
    from content_generator.creative.real_jar_composer import knockout_white

    chosen = select_front_asset(product)
    if not chosen:
        return None
    try:
        jar = knockout_white(Image.open(chosen["path"]))
    except Exception as exc:
        logger.warning("[jar_frame] mask rejected %s: %s", chosen["path"], exc)
        return None
    return jar, chosen["path"], chosen


def fit_jar_down(jar, max_w: int, max_h: int):
    """Scale the jar down to fit. Never enlarge past native pixels."""
    from PIL import Image

    max_w = max(1, int(max_w))
    max_h = max(1, int(max_h))
    scale = min(1.0, max_w / max(1, jar.width), max_h / max(1, jar.height))
    if scale >= 0.999:
        return jar, 1.0
    size = (max(1, int(round(jar.width * scale))), max(1, int(round(jar.height * scale))))
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    return jar.resize(size, resample), scale


def paste_product_jar(canvas, jar, rect: tuple[int, int, int, int]):
    """Ground the jar, then paste it unfiltered and bottom-aligned."""
    x0, y0, x1, y1 = rect
    fitted, scale = fit_jar_down(jar, x1 - x0, y1 - y0)
    jx = x0 + max(0, (x1 - x0 - fitted.width) // 2)
    jy = y1 - fitted.height
    if jy < y0:
        jy = y0
    from content_generator.creative.lifestyle_scene import ground_product, seat_base
    fitted = seat_base(fitted)
    base = ground_product(canvas, fitted, jx, jy)
    base.paste(fitted, (jx, jy), fitted)
    bbox = (jx, jy, jx + fitted.width, jy + fitted.height)
    return base.convert("RGB"), bbox, scale


def conversion_copy(product, headline: str = "", sub: str = "") -> dict:
    from content_generator.creative.frame_copy import conversion_copy as _conversion_copy
    return _conversion_copy(product, headline, sub)


def geometry_path(image_path: str) -> str:
    return image_path + ".jar.json"


def write_geometry(image_path: str, payload: dict) -> None:
    try:
        with open(geometry_path(image_path), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception as exc:
        logger.warning("[jar_frame] could not write geometry for %s: %s", image_path, exc)


def load_geometry(image_path: str) -> dict | None:
    path = geometry_path(image_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_text_card_geometry(image_path: str) -> None:
    """Editorial slides with no product jar. They are not hero frames."""
    write_geometry(image_path, {"jar_required": False, "role": "text_card"})


def _intersects(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def audit_jar_region(image, *, jar_bbox, text_boxes=None, safe_zone_box=None, scale: float = 1.0) -> dict:
    """Fail closed when the jar crop is soft, clipped, tiny, or under type."""
    issues: list[str] = []
    width, height = image.size
    try:
        x0, y0, x1, y1 = [int(v) for v in jar_bbox]
    except Exception:
        return {"ok": False, "issues": ["jar_bbox_invalid"], "sharpness": 0.0}
    if x1 <= x0 or y1 <= y0:
        return {"ok": False, "issues": ["jar_bbox_invalid"], "sharpness": 0.0}
    if scale > 1.001:
        issues.append("jar_upscaled")
    if x0 <= FRAME_EDGE_PX or y0 <= FRAME_EDGE_PX or x1 >= width - FRAME_EDGE_PX or y1 >= height - FRAME_EDGE_PX:
        issues.append("jar_cropped")
    if safe_zone_box is not None:
        sx0, sy0, sx1, sy1 = [int(v) for v in safe_zone_box]
        if x0 < sx0 or y0 < sy0 or x1 > sx1 or y1 > sy1:
            issues.append("jar_outside_safe_zone")
    if (y1 - y0) < MIN_JAR_HEIGHT_RATIO * height:
        issues.append("jar_too_small")
    crop = image.crop((max(0, x0), max(0, y0), min(width, x1), min(height, y1)))
    sharpness = _laplacian_variance(crop) if crop.size[0] and crop.size[1] else 0.0
    if sharpness < JAR_LAPLACIAN_MIN:
        issues.append("jar_blurred")
    for box in text_boxes or []:
        if _intersects((x0, y0, x1, y1), tuple(int(v) for v in box)):
            issues.append("jar_covered_by_text")
            break
    return {"ok": not issues, "issues": issues, "sharpness": round(sharpness, 2), "jar_bbox": [x0, y0, x1, y1]}


def audit_product_image(path: str) -> dict:
    """Fail closed. A hero frame without geometry is not publishable."""
    if not path or not os.path.exists(path):
        return {"ok": False, "issues": ["jar_image_missing"], "sharpness": 0.0}
    geometry = load_geometry(path)
    if not geometry:
        return {"ok": False, "issues": [f"{os.path.basename(path)}: jar_geometry_missing"], "sharpness": 0.0}
    if geometry.get("jar_required") is False:
        issues = []
        if geometry.get("lifestyle_required", True) and not geometry.get("scene_id"):
            issues.append("lifestyle_scene_missing")
        from content_generator.creative.visual_gate import copy_and_mask_issues
        issues.extend(copy_and_mask_issues(geometry))
        name = os.path.basename(path)
        if issues:
            return {
                "ok": False,
                "issues": [f"{name}: {issue}" for issue in issues],
                "sharpness": None,
                "jar_required": False,
            }
        return {"ok": True, "issues": [], "sharpness": None, "jar_required": False, "scene_id": geometry.get("scene_id")}
    try:
        from PIL import Image
        with Image.open(path) as source:
            image = source.convert("RGB")
    except Exception as exc:
        return {"ok": False, "issues": [f"unreadable_image:{type(exc).__name__}"], "sharpness": 0.0}
    result = audit_jar_region(
        image,
        jar_bbox=geometry.get("jar_bbox"),
        text_boxes=geometry.get("text_boxes") or [],
        safe_zone_box=geometry.get("safe_zone"),
        scale=float(geometry.get("scale") or 1.0),
    )
    if geometry.get("lifestyle_required", True):
        from content_generator.creative.lifestyle_scene import realism_issues
        from content_generator.creative.visual_gate import copy_and_mask_issues
        extra = realism_issues(image, geometry.get("jar_bbox"), geometry.get("scene_id"), contact_shadow=bool(geometry.get("contact_shadow", False)))
        extra.extend(copy_and_mask_issues(geometry))
        result["issues"].extend(extra)
        result["ok"] = not result["issues"]
    result["issues"] = [f"{os.path.basename(path)}: {issue}" for issue in result["issues"]]
    return result


def audit_product_images(paths: list[str]) -> dict:
    issues: list[str] = []
    checked = 0
    for path in paths:
        result = audit_product_image(path)
        checked += 1
        if not result.get("ok"):
            issues.extend(result.get("issues") or ["jar_qa_failed"])
    return {"ok": not issues, "issues": issues, "images_checked": checked}


def _draw_cta(canvas, text: str, font, y: int, width: int):
    """Gold CTA on a dark plate so it stays readable over the counter."""
    from PIL import Image, ImageDraw

    text = (text or "").strip()
    if not text:
        return canvas, None
    overlay = canvas.convert("RGBA")
    draw = ImageDraw.Draw(overlay)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = max(16, (width - tw) // 2)
    plate = [x - 28, y - 12, x + tw + 28, y + th + 14]
    bar = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    ImageDraw.Draw(bar).rounded_rectangle(plate, radius=16, fill=(16, 10, 7, 196))
    overlay = Image.alpha_composite(overlay, bar)
    ImageDraw.Draw(overlay).text((x, y), text, font=font, fill=(245, 228, 176))
    return overlay.convert("RGB"), tuple(plate)


def _draw_centered(draw, text: str, font, y: int, fill, width: int) -> tuple[int, tuple[int, int, int, int] | None]:
    text = (text or "").strip()
    if not text:
        return y, None
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)
    return y + int(font.size * 1.18), (x, y, x + tw, y + th)


def compose_conversion_frame(
    headline: str = "",
    sub: str = "",
    product=None,
    day: int = 0,
    idx: int = 0,
    width: int = 1080,
    height: int = 1350,
    label: str = "feed",
    format_name: str = "feed",
    on_date=None,
    out_dir: str | None = None,
    attempt: int = 0,
) -> str | None:
    """Story, 4:5 feed, or square carousel hero. Real jar on a rotating lifestyle plate."""
    del idx
    try:
        from PIL import ImageDraw
    except ImportError:
        return None
    loaded = load_native_jar(product)
    if not loaded:
        logger.warning("[jar_frame] no front-of-jar photo for %s", product)
        return None
    jar, jar_path, _chosen = loaded
    slug = product_slug(product) or _slug_from_path(jar_path)
    copy = conversion_copy(slug or product, headline, sub)

    from content_generator.creative.lifestyle_scene import load_plate, match_light
    canvas, scene_id = load_plate(width, height, day)
    if canvas is None:
        logger.warning("[jar_frame] lifestyle plate missing")
        return None
    jar = match_light(jar, canvas)
    zone = safe_zone(width, height, "story" if format_name == "story" or height > width * 1.3 else format_name)
    from content_generator.creative.real_jar_composer import _font, _wrap

    draw = ImageDraw.Draw(canvas)
    title_size = max(40, min(58, width // 18))
    body_size = max(22, min(28, width // 40))
    title_font = _font("title", title_size)
    body_font = _font("body", body_size)
    footer_font = _font("footer", max(20, width // 42))
    max_w = zone[2] - zone[0]
    hook_lines = _wrap(draw, copy["hook"], title_font, max_w)[:2]
    benefit_lines = _wrap(draw, copy["benefit"], body_font, max_w)[:2]

    y = zone[1]
    text_boxes: list[tuple[int, int, int, int]] = []
    for line in hook_lines:
        y, box = _draw_centered(draw, line, title_font, y, (255, 248, 236), width)
        if box:
            text_boxes.append(box)
    y += int(height * 0.012)
    for line in benefit_lines:
        y, box = _draw_centered(draw, line, body_font, y, (232, 196, 122), width)
        if box:
            text_boxes.append(box)
    if copy["offer"]:
        y += int(height * 0.008)
        y, box = _draw_centered(draw, copy["offer"], footer_font, y, (245, 236, 220), width)
        if box:
            text_boxes.append(box)

    cta_h = int(footer_font.size * 2.4)
    cta_top = zone[3] - cta_h
    from content_generator.creative.lifestyle_scene import frame_props, place_product, scene_for_day
    jar_rect = place_product(
        scene_for_day(day), width, height, y, cta_top, zone, jar.size, attempt=attempt,
    )
    prop_boxes = [dict(prop, box=list(prop["box"])) for prop in frame_props(scene_for_day(day), width, height)]
    canvas, jar_bbox, scale = paste_product_jar(canvas, jar, jar_rect)
    canvas, cta_box = _draw_cta(canvas, copy["cta"], footer_font, cta_top + 6, width)
    if cta_box:
        text_boxes.append(cta_box)

    from content_generator.core.ist_dates import today_ist
    if on_date is None:
        date_str = today_ist().isoformat()
    elif hasattr(on_date, "isoformat"):
        date_str = on_date.isoformat()
    else:
        date_str = str(on_date)[:10]
    folder = out_dir or _OUT_DIR
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{label}_{date_str}.jpg")
    canvas.save(path, "JPEG", quality=92)
    write_geometry(path, {
        "jar_required": True,
        "jar_bbox": list(jar_bbox),
        "text_boxes": [list(box) for box in text_boxes],
        "safe_zone": list(zone),
        "scale": round(scale, 4),
        "source_asset": jar_path.replace("\\", "/"),
        "format": format_name,
        "scene_id": scene_id,
        "contact_shadow": True,
        "lifestyle_required": True,
        "props": prop_boxes,
        "product": slug or str(product or ""),
        "mask_ok": True,
        "mask_issues": [],
        "on_image": {
            "hook": copy["hook"],
            "benefit": copy["benefit"],
            "offer": copy["offer"],
            "cta": copy["cta"],
        },
    })
    try:
        from content_generator.creative.jar_provenance import record_jar_provenance
        record_jar_provenance(path, jar_asset_id=jar_path, render_source="real_jar")
    except Exception as exc:
        logger.debug("[jar_frame] provenance skipped: %s", exc)
    logger.info(
        "[jar_frame] %s scale=%.3f jar=%s bbox=%s",
        os.path.basename(path), scale, os.path.basename(jar_path), jar_bbox,
    )
    return path


def _slug_from_path(path: str) -> str | None:
    name = os.path.basename(path).lower()
    for slug in ("ultra_blend", "purista", "purica", "bold", "prima"):
        if f"_{slug}_" in name:
            return slug
    return None
