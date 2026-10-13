"""Editorial carousel cards and per-surface stills. No network, no publish."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def compose_editorial_card(
    heading: str,
    body: str,
    day: int = 0,
    idx: int = 0,
    total_slides: int = 1,
    width: int = 1080,
    height: int = 1350,
    label: str = "carousel_slide",
    product: str | None = None,
    out_dir: str | None = None,
) -> str | None:
    """Middle carousel slide: the slide's own words, no invented claims, no sticker stack."""
    from PIL import ImageDraw

    from content_generator.creative.jar_frame import (
        _draw_centered,
        conversion_copy,
        safe_zone,
        write_geometry,
    )
    from content_generator.creative.lifestyle_scene import load_plate
    from content_generator.creative.real_jar_composer import _font, _wrap
    from content_generator.publisher.surface_copy import clean_slide_copy

    heading, body = clean_slide_copy(heading, body, product)
    canvas, scene_id = load_plate(width, height, day, blur=3.5)
    if canvas is None:
        return None
    zone = safe_zone(width, height, "carousel")
    draw = ImageDraw.Draw(canvas)
    copy = conversion_copy(product or "Bold")
    index_font = _font("footer", max(18, width // 48))
    title_font = _font("title", max(36, min(52, width // 18)))
    body_font = _font("body", max(24, min(32, width // 34)))
    y = zone[1]
    y, _box = _draw_centered(
        draw, f"{idx + 1:02d}  /  {max(1, total_slides):02d}", index_font, y, (232, 196, 122), width,
    )
    y += int(height * 0.03)
    max_w = zone[2] - zone[0]
    for line in _wrap(draw, heading.upper(), title_font, max_w)[:3]:
        y, _box = _draw_centered(draw, line, title_font, y, (255, 248, 236), width)
    y += int(height * 0.04)
    for line in _wrap(draw, body, body_font, max_w)[:8]:
        y, _box = _draw_centered(draw, line, body_font, y, (236, 228, 214), width)
    footer_font = _font("footer", max(18, width // 46))
    _draw_centered(draw, copy["cta"], footer_font, zone[3] - int(footer_font.size * 1.4), (232, 196, 122), width)

    folder = out_dir or os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    os.makedirs(folder, exist_ok=True)
    from content_generator.core.ist_dates import today_ist
    path = os.path.join(folder, f"{label}_{today_ist().isoformat()}.jpg")
    canvas.save(path, "JPEG", quality=92)
    write_geometry(path, {
        "jar_required": False,
        "role": "text_card",
        "scene_id": scene_id,
        "lifestyle_required": True,
    })
    try:
        from content_generator.creative.jar_frame import select_front_asset
        from content_generator.creative.jar_provenance import record_jar_provenance
        chosen = select_front_asset(product)
        if chosen:
            record_jar_provenance(path, jar_asset_id=chosen["path"], render_source="real_jar")
    except Exception as exc:
        logger.debug("[surface] text-card provenance skipped: %s", exc)
    return path
