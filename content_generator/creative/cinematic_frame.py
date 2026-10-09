"""
Cinematic vertical frame for reel VIDEO — viral-style, real jar, no white box.

Fixes the "white box on black" look: knocks out the white background from the
real jar PNG (corner flood-fill so the label's own whites survive), then places
the cut-out jar large on a cinematic espresso->amber gradient with a radial
glow, vignette, and bold high-contrast caption.

Pillow only. Used by reel_video; the static-post composer is left untouched.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_GOLD  = (200, 150, 46)
_CREAM = (245, 238, 216)


def _knockout_white(img):
    """
    Return RGBA jar with the white background made transparent (corner flood-fill).

    Delegates to real_jar_composer.knockout_white — the carousel path needs the
    identical operation, and two copies of it would drift.
    """
    from content_generator.creative.real_jar_composer import knockout_white
    return knockout_white(img)


def _gradient_bg(width, height, exposure_boost=False):
    """Cinematic vertical gradient: deep espresso -> warm brown -> espresso."""
    from PIL import Image
    if exposure_boost:
        top    = (28, 18, 10)
        mid    = (78, 48, 22)
        bottom = (18, 12, 7)
    else:
        top    = (13, 9, 5)      # espresso
        mid    = (46, 28, 12)    # warm brown
        bottom = (10, 7, 4)
    bg = Image.new("RGB", (width, height))
    px = bg.load()
    for y in range(height):
        f = y / height
        if f < 0.5:
            t = f / 0.5
            c = tuple(int(top[i] + (mid[i] - top[i]) * t) for i in range(3))
        else:
            t = (f - 0.5) / 0.5
            c = tuple(int(mid[i] + (bottom[i] - mid[i]) * t) for i in range(3))
        for x in range(width):
            px[x, y] = c
    return bg


def _radial_glow(canvas, cx, cy, size, color=(60, 42, 16)):
    from PIL import Image, ImageDraw, ImageFilter
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    for r in range(size // 2, 0, -3):
        a = int(200 * (1 - r / (size // 2)) ** 2)
        d.ellipse([(size // 2 - r, size // 2 - r), (size // 2 + r, size // 2 + r)], fill=a)
    mask = mask.filter(ImageFilter.GaussianBlur(30))
    glow = Image.new("RGB", (size, size), color)
    canvas.paste(glow, (cx - size // 2, cy - size // 2), mask=mask)


def _font(size, bold=True):
    from PIL import ImageFont
    cands = (["arialbd.ttf", "segoeuib.ttf", "georgiab.ttf"] if bold
             else ["segoeui.ttf", "arial.ttf"])
    ext = []
    for c in cands:
        ext.append(c)
        if os.name == "nt":
            ext.append(os.path.join("C:\\Windows\\Fonts", c))
        else:
            ext += [os.path.join("/usr/share/fonts/truetype/dejavu",
                                 "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    for c in ext:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    from PIL import ImageFont as IF
    try:
        return IF.load_default(size=size)
    except Exception:
        return IF.load_default()


def _wrap(draw, text, font, max_w):
    try:
        from content_generator.creative.real_jar_composer import _sanitize_text
        text = _sanitize_text(text)
    except Exception:
        text = str(text or "").strip()
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines[:3]


def compose_cinematic_frame(headline, sub="", day=0, idx=0, product=None,
                            width=1080, height=1920, label="cine_frame"):
    """Real jar (white knocked out) on a cinematic backdrop + bold caption."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    from content_generator.creative.real_jar_composer import pick_jar_photo

    # Front-facing AND overlay-safe: _knockout_white needs a white sweep, a
    # finished creative would drag its own headline into the cut-out, and the
    # rear label (barcode, batch number) reads as a warehouse photo.
    # pick_jar_photo enforces all three — this used to be duplicated here.
    jar_path = pick_jar_photo(day, idx, product, overlay_safe=True, prefer_front=True)
    if not jar_path:
        return None

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        dirs = get_visual_adaptation_directives()
    except Exception:
        dirs = {}

    boost_exposure = dirs.get("boost_exposure", False)
    boost_upper = dirs.get("boost_upper_activity", False)

    canvas = _gradient_bg(width, height, exposure_boost=boost_exposure)
    # warm glow behind the jar (lower-centre)
    glow_color = (130, 90, 36) if boost_exposure else (60, 42, 16)
    _radial_glow(canvas, width // 2, int(height * 0.66), int(width * 0.95), color=glow_color)
    draw = ImageDraw.Draw(canvas)

    # Jar — knocked out, large, lower-centre
    try:
        jar = _knockout_white(Image.open(jar_path))
        # Fill the frame: tall 9:16 stories/reels need a much larger hero so the
        # middle isn't dead space (a small jar at the bottom reads as unfinished).
        is_tall = height > width * 1.4
        target_h = int(height * (0.58 if is_tall else 0.46))
        ratio = target_h / jar.height
        jar = jar.resize((int(jar.width * ratio), target_h))
        if jar.width > int(width * 0.82):
            r = int(width * 0.82) / jar.width
            jar = jar.resize((int(jar.width * r), int(jar.height * r)))
        jx = (width - jar.width) // 2
        # Sit the hero just below the copy block, ending above Instagram's
        # bottom UI (~10% is covered by the reply bar).
        jy = int(height * (0.36 if is_tall else 0.50))
        canvas.paste(jar, (jx, jy), jar)   # alpha mask = jar itself
    except Exception as e:
        logger.warning("[cine] jar paste failed: %s", e)
        return None

    # Caption — big, bold, high-contrast, upper third
    margin = int(width * 0.08)
    max_w = width - 2 * margin
    hf = _font(max(52, width // 11), bold=True)
    y = int(height * 0.08)
    lines = _wrap(draw, headline.upper(), hf, max_w)

    if boost_upper or boost_exposure:
        # Translucent backing pill for maximum contrast and upper frame pattern-interrupt
        try:
            pad_x = int(width * 0.04)
            pad_y = int(height * 0.015)
            pill_w = min(width - 20, max_w + pad_x * 2)
            pill_h = int(len(lines) * hf.size * 1.16) + pad_y * 2
            px0 = (width - pill_w) // 2
            py0 = max(10, y - pad_y)
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            odraw.rounded_rectangle([(px0, py0), (px0 + pill_w, py0 + pill_h)], radius=20,
                                    fill=(12, 8, 4, 180), outline=_GOLD, width=2)
            canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(canvas)
        except Exception as pe:
            logger.debug("[cine] backing pill skipped: %s", pe)

    for line in lines:
        # subtle shadow for pop
        draw.text((width // 2 + 3, y + 3), line, font=hf, fill=(0, 0, 0), anchor="ma")
        draw.text((width // 2, y), line, font=hf, fill=_CREAM, anchor="ma")
        y += int(hf.size * 1.12)

    if sub:
        sf = _font(max(30, width // 26), bold=False)
        y += int(height * 0.01)
        for line in _wrap(draw, sub, sf, max_w):
            draw.text((width // 2, y), line, font=sf, fill=_GOLD, anchor="ma")
            y += int(sf.size * 1.3)

    # Minimal brand mark — placed in the SAFE ZONE (upper-middle), NOT at the
    # bottom where Instagram's caption/buttons/audio UI covers it (v7: safe zone).
    ff = _font(max(24, width // 40), bold=True)
    draw.text((width // 2, int(height * (0.31 if height > width * 1.4 else 0.43))),
              "PURITY BEANS  |  p3online.in", font=ff, fill=_GOLD, anchor="mm")

    from content_generator.core.ist_dates import today_ist
    os.makedirs(_OUT_DIR, exist_ok=True)
    out = os.path.join(_OUT_DIR, f"{label}_{today_ist().isoformat()}.jpg")
    canvas.save(out, "JPEG", quality=90)

    try:
        from content_generator.creative.jar_provenance import record_jar_provenance
        record_jar_provenance(out, jar_asset_id=jar_path, render_source="cinematic_real_jar")
    except Exception as pe:
        logger.debug("[cinematic_frame] Provenance recording skipped: %s", pe)

    return out
