"""
Cinematic vertical frame for Instagram Stories and Reel Videos — grounded, safe-zone compliant, real jar.

Solves the unpolished floating-jar look:
1. Physical Tabletop Grounding: Upper espresso studio wall + grounded dark Italian wood/slate
   countertop at the bottom 36% with horizon edge sheen and realistic physics contact shadows.
2. Instagram Safe Zones: Keeps all on-screen copy strictly within safe zones (top >= 260px,
   bottom <= 1660px) so Instagram header and reply bar never collide with copy.
3. Interactive Story Element: Sleek simulated Instagram Story poll/inspection card
   for high viewer engagement.
4. Provenance Preserved: Authentic jar provenance tracked for every rendered asset.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_GOLD  = (200, 150, 46)
_CREAM = (248, 242, 226)


def _knockout_white(img):
    """
    Return RGBA jar with the white background made transparent (corner flood-fill).
    """
    from content_generator.creative.real_jar_composer import knockout_white
    return knockout_white(img)


def _gradient_bg(width, height, exposure_boost=False, is_tall=False):
    """
    Cinematic grounded studio backdrop:
    - If is_tall (9:16): Deep espresso studio wall (top 64%) + grounded dark oak/slate counter
      (bottom 36%) with subtle horizon sheen.
    - Otherwise: Deep espresso studio wall gradient.
    """
    from PIL import Image, ImageDraw
    bg = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(bg)

    if exposure_boost:
        wall_top = (30, 20, 12)
        wall_mid = (82, 52, 26)
        table_edge = (46, 30, 18)
        table_bot = (22, 14, 8)
    else:
        wall_top = (14, 9, 5)
        wall_mid = (46, 28, 14)
        table_edge = (35, 22, 12)
        table_bot = (16, 10, 5)

    if is_tall:
        table_y = int(height * 0.64)
        # Studio wall gradient
        for y in range(table_y):
            f = y / max(1, table_y)
            c = tuple(int(wall_top[i] + (wall_mid[i] - wall_top[i]) * f) for i in range(3))
            draw.line([(0, y), (width, y)], fill=c)
        # Tabletop surface gradient
        for y in range(table_y, height):
            f = (y - table_y) / max(1, height - table_y)
            c = tuple(int(table_edge[i] + (table_bot[i] - table_edge[i]) * f) for i in range(3))
            draw.line([(0, y), (width, y)], fill=c)
        # Subtle horizon edge highlight sheen
        draw.line([(0, table_y), (width, table_y)], fill=(75, 52, 28))
        draw.line([(0, table_y + 1), (width, table_y + 1)], fill=(52, 36, 18))
    else:
        for y in range(height):
            f = y / height
            if f < 0.5:
                t = f / 0.5
                c = tuple(int(wall_top[i] + (wall_mid[i] - wall_top[i]) * t) for i in range(3))
            else:
                t = (f - 0.5) / 0.5
                c = tuple(int(wall_mid[i] + (table_bot[i] - wall_mid[i]) * t) for i in range(3))
            draw.line([(0, y), (width, y)], fill=c)

    return bg


def _radial_glow(canvas, cx, cy, size, color=(60, 42, 16)):
    from PIL import Image, ImageDraw, ImageFilter
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    for r in range(size // 2, 0, -3):
        a = int(220 * (1 - r / (size // 2)) ** 2)
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
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:3]


def _draw_interactive_story_card(canvas, headline: str, y_top: int, width: int):
    """
    Draw an authentic interactive Instagram Story sticker (Poll / Quiz / Guarantee)
    positioned comfortably in the safe zone between the headline and the hero jar.
    Uses pure ASCII characters to prevent tofu boxes.
    """
    from PIL import Image, ImageDraw
    h_lower = headline.lower()

    if any(k in h_lower for k in ("chicory", "label", "ingredient", "adulter", "blend", "cheap")):
        title = "POLL: Do you check your coffee label?"
        opt1 = "100% Arabica only"
        opt2 = "Checking right now"
    elif any(k in h_lower for k in ("bitter", "sugar", "taste", "milk", "smooth", "flavour", "flavor")):
        title = "TASTE TEST: Need sugar to mask bitterness?"
        opt1 = "Never (real coffee)"
        opt2 = "Always (chicory blend)"
    else:
        title = "QUICK POLL: Instant coffee drinker?"
        opt1 = "Demanding 100% pure"
        opt2 = "Settling for chicory"

    card_w = int(width * 0.86)
    card_h = 126
    cx0 = (width - card_w) // 2
    cy0 = y_top

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # Sticker background card with subtle rounded corners and gold border
    odraw.rounded_rectangle(
        [(cx0, cy0), (cx0 + card_w, cy0 + card_h)],
        radius=18,
        fill=(22, 15, 9, 215),
        outline=_GOLD,
        width=2,
    )

    # Card Title
    tf = _font(23, bold=True)
    odraw.text((width // 2, cy0 + 16), title, font=tf, fill=_CREAM, anchor="mt")

    # Two interactive voting pills
    pill_w = (card_w - 48) // 2
    pill_h = 44
    p_y = cy0 + 62

    # Pill 1
    p1_x = cx0 + 16
    odraw.rounded_rectangle(
        [(p1_x, p_y), (p1_x + pill_w, p_y + pill_h)],
        radius=12,
        fill=(38, 25, 14, 230),
        outline=(160, 120, 40),
        width=1,
    )
    pf = _font(20, bold=True)
    odraw.text((p1_x + pill_w // 2, p_y + pill_h // 2), f"O  {opt1}", font=pf, fill=_CREAM, anchor="mm")

    # Pill 2
    p2_x = p1_x + pill_w + 16
    odraw.rounded_rectangle(
        [(p2_x, p_y), (p2_x + pill_w, p_y + pill_h)],
        radius=12,
        fill=(38, 25, 14, 230),
        outline=(160, 120, 40),
        width=1,
    )
    odraw.text((p2_x + pill_w // 2, p_y + pill_h // 2), f"O  {opt2}", font=pf, fill=_CREAM, anchor="mm")

    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def compose_cinematic_frame(headline, sub="", day=0, idx=0, product=None,
                            width=1080, height=1920, label="cine_frame"):
    """
    Real jar (white knocked out) on a grounded cinematic backdrop + safe-zone copy.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    from content_generator.creative.real_jar_composer import pick_jar_photo

    jar_path = pick_jar_photo(day, idx, product, overlay_safe=True, prefer_front=True)
    if not jar_path:
        return None

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        lower_label = str(label or "").lower()
        target_platform = "youtube" if ("youtube" in lower_label or "yt_" in lower_label or "short" in lower_label) else "instagram"
        dirs = get_visual_adaptation_directives(platform=target_platform)
    except Exception:
        dirs = {}

    boost_exposure = dirs.get("boost_exposure", False)
    is_tall = height > width * 1.4

    canvas = _gradient_bg(width, height, exposure_boost=boost_exposure, is_tall=is_tall)

    # Warm radial glow behind the jar
    glow_color = (130, 90, 36) if boost_exposure else (65, 42, 18)
    glow_y = int(height * (0.60 if is_tall else 0.64))
    _radial_glow(canvas, width // 2, glow_y, int(width * 0.90), color=glow_color)

    # Jar — knocked out, resting firmly on the grounded tabletop
    try:
        jar = _knockout_white(Image.open(jar_path))
        target_h = int(height * (0.44 if is_tall else 0.46))
        ratio = target_h / jar.height
        jar = jar.resize((int(jar.width * ratio), target_h))
        if jar.width > int(width * 0.78):
            r = int(width * 0.78) / jar.width
            jar = jar.resize((int(jar.width * r), int(jar.height * r)))

        jx = (width - jar.width) // 2
        if is_tall:
            jar_bottom = int(height * 0.79)
            jy = jar_bottom - jar.height
        else:
            jy = int(height * 0.50)

        # Ground Contact Shadow + Ambient Occlusion (physics grounding)
        try:
            from PIL import ImageFilter
            shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(shadow_layer)

            # Diffuse cast shadow
            s_w = int(jar.width * 1.35)
            s_h = int(jar.height * 0.10)
            s_x = jx + (jar.width - s_w) // 2
            s_y = jy + jar.height - int(s_h * 0.50)
            sdraw.ellipse([(s_x, s_y), (s_x + s_w, s_y + s_h)], fill=(6, 4, 2, 140))

            # Deep contact occlusion shadow directly under jar base
            c_w = int(jar.width * 0.94)
            c_h = int(jar.height * 0.04)
            c_x = jx + (jar.width - c_w) // 2
            c_y = jy + jar.height - int(c_h * 0.70)
            sdraw.ellipse([(c_x, c_y), (c_x + c_w, c_y + c_h)], fill=(2, 1, 1, 240))

            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer).convert("RGB")
        except Exception as se:
            logger.debug("[cine] Shadow compositing skipped: %s", se)

        canvas.paste(jar, (jx, jy), jar)
    except Exception as e:
        logger.warning("[cine] jar paste failed: %s", e)
        return None

    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)
    max_w = width - 2 * margin

    if is_tall:
        # 1. Instagram Safe Zone Eyebrow Pill (y >= 260px)
        category_text = "PURITY STORY • ZERO CHICORY"
        cf = _font(22, bold=True)
        cat_w = draw.textlength(category_text, font=cf)
        cat_pill_w = int(cat_w + 36)
        cat_pill_x = (width - cat_pill_w) // 2
        draw.rounded_rectangle(
            [(cat_pill_x, 275), (cat_pill_x + cat_pill_w, 312)],
            radius=12,
            fill=(20, 14, 8),
            outline=_GOLD,
            width=1,
        )
        draw.text((width // 2, 293), category_text, font=cf, fill=_GOLD, anchor="mm")

        # 2. Headline in Safe Zone
        hf = _font(max(48, width // 12), bold=True)
        y = 345
        lines = _wrap(draw, headline.upper(), hf, max_w)
        for line in lines:
            draw.text((width // 2 + 3, y + 3), line, font=hf, fill=(0, 0, 0), anchor="ma")
            draw.text((width // 2, y), line, font=hf, fill=_CREAM, anchor="ma")
            y += int(hf.size * 1.14)

        # 3. Sub-headline
        if sub:
            sf = _font(max(26, width // 30), bold=False)
            y += 8
            for line in _wrap(draw, sub, sf, max_w):
                draw.text((width // 2, y), line, font=sf, fill=_GOLD, anchor="ma")
                y += int(sf.size * 1.25)

        # 4. Interactive Story Card
        card_top = min(y + 16, jy - 138)
        if card_top > 450:
            canvas = _draw_interactive_story_card(canvas, headline, card_top, width)
            draw = ImageDraw.Draw(canvas)

        # 5. Bottom Safe Zone CTA Pill (above bottom 1680px UI cutoff)
        ff = _font(max(24, width // 38), bold=True)
        cta_text = "PURITY BEANS  |  TAP LINK IN BIO >"
        cta_w = draw.textlength(cta_text, font=ff)
        cta_pill_w = int(cta_w + 40)
        cta_pill_x = (width - cta_pill_w) // 2
        draw.rounded_rectangle(
            [(cta_pill_x, 1568), (cta_pill_x + cta_pill_w, 1612)],
            radius=14,
            fill=(18, 12, 7, 230),
            outline=_GOLD,
            width=1,
        )
        draw.text((width // 2, 1590), cta_text, font=ff, fill=_CREAM, anchor="mm")

    else:
        # Standard 1:1 or non-tall format
        hf = _font(max(52, width // 11), bold=True)
        y = int(height * 0.08)
        lines = _wrap(draw, headline.upper(), hf, max_w)
        for line in lines:
            draw.text((width // 2 + 3, y + 3), line, font=hf, fill=(0, 0, 0), anchor="ma")
            draw.text((width // 2, y), line, font=hf, fill=_CREAM, anchor="ma")
            y += int(hf.size * 1.12)

        if sub:
            sf = _font(max(30, width // 26), bold=False)
            y += int(height * 0.01)
            for line in _wrap(draw, sub, sf, max_w):
                draw.text((width // 2, y), line, font=sf, fill=_GOLD, anchor="ma")
                y += int(sf.size * 1.3)

        ff = _font(max(24, width // 40), bold=True)
        draw.text((width // 2, int(height * 0.43)),
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
