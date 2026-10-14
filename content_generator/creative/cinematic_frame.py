"""
Cinematic vertical frame for Instagram Stories and Reel Videos — grounded, safe-zone compliant, real jar.

Solves the unpolished floating-jar look:
1. Physical Tabletop Grounding: Upper espresso studio wall + grounded dark Italian wood/slate
   countertop at the bottom 36% with horizon edge sheen and realistic physics contact shadows.
2. Instagram Safe Zones: Keeps all on-screen copy strictly within safe zones (top >= 260px,
   bottom <= 1660px) so Instagram header and reply bar never collide with copy.
3. Distinct chrome: Shorts, Reels, and Stories each get their own badge and CTA.
   Claims follow the jar — Ultra Blend is 70/30, pure jars may say zero chicory,
   and an unknown jar stays on the slogan. No fake poll or sticker is drawn.
4. Provenance Preserved: Authentic jar provenance tracked for every rendered asset.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_GOLD  = (200, 150, 46)
_CREAM = (248, 242, 226)
_PURE_JARS = ("bold", "purista", "purica", "prima", "premium agglomerate")


def _product_class(product) -> str:
    """ultra, pure, or unknown. Unknown must stay claim-neutral.

    Gourmet Duo and Gourmet Duo Mini are pure coffee. A label that names
    one of those duos together with Ultra Blend stays neutral so neither
    jar inherits the other's chicory line.
    """
    key = " ".join(str(product or "").strip().lower().replace("_", " ").replace("-", " ").split())
    duo = "gourmet duo" in key
    ultra = "ultra" in key
    if duo and ultra:
        return "unknown"
    if duo:
        return "pure"
    if ultra:
        return "ultra"
    if any(name in key for name in _PURE_JARS):
        return "pure"
    return "unknown"


def onscreen_chrome(format_type: str, product=None) -> tuple[str, str]:
    """Badge and CTA that match the format and the jar in the frame.

    Shorts stay short enough that the PART counter on the right does not
    collide with a centered badge. Zero-chicory copy is reserved for jars
    that are actually pure coffee.
    """
    kind = _product_class(product)
    fmt = str(format_type or "reel").strip().lower()
    if fmt == "short":
        badge = "YOUTUBE SHORTS"
        if kind == "ultra":
            cta = "ULTRA BLEND  •  70% COFFEE  30% CHICORY"
        elif kind == "pure":
            cta = "PURE COFFEE  •  ZERO CHICORY"
        else:
            cta = "INDIA'S CLEANEST INSTANT COFFEE"
    elif fmt == "story":
        if kind == "ultra":
            badge, cta = "STORY  •  ULTRA BLEND", "70% COFFEE  •  30% CHICORY"
        elif kind == "pure":
            badge, cta = "STORY  •  ONE INGREDIENT", "PURE COFFEE  •  TAP THE LINK"
        else:
            badge, cta = "STORY  •  READ THE LABEL", "INDIA'S CLEANEST INSTANT COFFEE"
    else:
        if kind == "ultra":
            badge, cta = "REEL  •  ULTRA BLEND", "70% COFFEE  •  30% CHICORY"
        elif kind == "pure":
            badge, cta = "REEL  •  PURITY BEANS", "PURE COFFEE  •  SAVE THIS"
        else:
            badge, cta = "REEL  •  PURITY BEANS", "SAVE THIS  •  LINK IN BIO"
    return badge, cta


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


def compose_cinematic_frame(headline, sub="", day=0, idx=0, product=None,
                            width=1080, height=1920, label="cine_frame",
                            format_type="reel", scene_idx=0, total_scenes=0,
                            badge="", cta_text=None, on_date=None):
    """
    Real jar (white knocked out) on a grounded cinematic backdrop + safe-zone copy.
    Supports distinct visual styles for YouTube Shorts ('short'), Instagram Reels ('reel'),
    and Instagram Stories ('story').
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    from content_generator.creative.real_jar_composer import pick_jar_photo, _has_white_background, _all_jar_photos

    # For knockout compositing, we strictly prefer authentic high-resolution 100g studio
    # hero shots on solid white sweep (clean knockout without flash glare/tearing).
    everything = _all_jar_photos()
    studio_100g = [p for p in everything if _has_white_background(p) and "_100g_front.png" in p.lower()]
    studio_fronts = studio_100g or [p for p in everything if _has_white_background(p) and "_front.png" in p.lower()]
    if not studio_fronts:
        studio_fronts = [p for p in everything if _has_white_background(p)]

    if studio_fronts:
        if product:
            matched = [p for p in studio_fronts if f"_{product.lower().replace(' ', '_')}_" in p.lower()]
            jar_path = (matched or studio_fronts)[(day * 3 + idx) % len(matched or studio_fronts)]
        else:
            # Advance across distinct product variants across beats (idx) and days (day)
            # studio_100g has 4 distinct products: ultra_blend, bold, purista, purica
            # Cycling by (day + idx) guarantees no consecutive beat repeats the same variant!
            jar_path = studio_fronts[(day + idx) % len(studio_fronts)]
    else:
        jar_path = pick_jar_photo(day, idx, product, overlay_safe=True, prefer_front=True)

    if not jar_path:
        return None

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        lower_label = str(label or "").lower()
        target_platform = "youtube" if ("youtube" in lower_label or "yt_" in lower_label or "short" in lower_label or format_type == "short") else "instagram"
        dirs = get_visual_adaptation_directives(platform=target_platform)
    except Exception:
        dirs = {}

    boost_exposure = dirs.get("boost_exposure", False)
    is_tall = height > width * 1.4

    canvas = _gradient_bg(width, height, exposure_boost=boost_exposure, is_tall=is_tall)
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)
    max_w = width - 2 * margin

    resample_filter = getattr(Image, "Resampling", Image).LANCZOS

    if is_tall:
        # Pre-measure text layout FIRST to eliminate any possibility of copy colliding with jar
        # Distinct typography for YouTube Shorts vs Instagram Reels/Stories
        if format_type == "short":
            hf_size = max(44, min(60, width // 16))
            headline_color = (255, 230, 0)  # YouTube high-visibility Canary Yellow
            sub_color = (255, 255, 255)       # Crisp White
        elif format_type == "story":
            hf_size = max(44, min(58, width // 17))
            headline_color = _CREAM
            sub_color = _GOLD
        else:
            hf_size = max(42, min(56, width // 18))
            headline_color = _CREAM
            sub_color = _GOLD

        hf = _font(hf_size, bold=True)
        h_lines = _wrap(draw, headline.upper(), hf, max_w)[:2]

        sf_size = max(24, min(30, width // 36))
        sf = _font(sf_size, bold=False)
        s_lines = _wrap(draw, sub, sf, max_w)[:3] if sub else []

        text_cursor = 345
        text_cursor += len(h_lines) * int(hf.size * 1.15)
        if s_lines:
            text_cursor += 10 + len(s_lines) * int(sf.size * 1.25)
        text_bottom = text_cursor

        # Jar bounds: baseline sits right above bottom CTA pill (1568px), top stays safely below copy
        jar_bottom = int(height * 0.80)  # 1536px
        min_jar_top = text_bottom + 45   # Guaranteed breathing room between text and jar cap
        available_jar_h = max(300, jar_bottom - min_jar_top)
        target_h = min(int(height * 0.40), available_jar_h - 20)

        # Knock out studio jar with high-res LANCZOS resampling
        try:
            jar = _knockout_white(Image.open(jar_path))
            ratio = target_h / jar.height
            jar = jar.resize((int(jar.width * ratio), target_h), resample=resample_filter)
            if jar.width > int(width * 0.78):
                r = int(width * 0.78) / jar.width
                jar = jar.resize((int(jar.width * r), int(jar.height * r)), resample=resample_filter)

            jx = (width - jar.width) // 2
            jy = jar_bottom - jar.height
            if jy < min_jar_top:
                jy = min_jar_top

            # Warm radial glow centered behind the jar body
            glow_color = (130, 90, 36) if boost_exposure else (65, 42, 18)
            glow_y = int(jy + jar.height * 0.45)
            _radial_glow(canvas, width // 2, glow_y, int(width * 0.90), color=glow_color)

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

        # Re-initialize draw on composite canvas for crisp copy
        draw = ImageDraw.Draw(canvas)

        # 1. Distinct Platform Eyebrow Badge (y >= 260px)
        chrome_badge, chrome_cta = onscreen_chrome(format_type, product)
        category_text = badge or chrome_badge

        cf = _font(22, bold=True)
        cat_w = draw.textlength(category_text, font=cf)
        cat_pill_w = int(cat_w + 36)
        cat_pill_x = (width - cat_pill_w) // 2
        badge_border = (220, 50, 40) if format_type == "short" else _GOLD
        draw.rounded_rectangle(
            [(cat_pill_x, 275), (cat_pill_x + cat_pill_w, 312)],
            radius=12,
            fill=(20, 14, 8),
            outline=badge_border,
            width=1,
        )
        badge_text_color = (255, 220, 100) if format_type == "short" else _GOLD
        draw.text((width // 2, 293), category_text, font=cf, fill=badge_text_color, anchor="mm")

        # Optional Scene Counter for YouTube Shorts (e.g. SCENE 1/4)
        if format_type == "short" and total_scenes > 1:
            scene_label = f"PART {scene_idx + 1} OF {total_scenes}"
            scf = _font(18, bold=True)
            sc_w = draw.textlength(scene_label, font=scf)
            sc_pill_w = int(sc_w + 24)
            sc_pill_x = width - margin - sc_pill_w
            draw.rounded_rectangle(
                [(sc_pill_x, 277), (sc_pill_x + sc_pill_w, 310)],
                radius=8,
                fill=(45, 12, 10),
                outline=(220, 60, 40),
                width=1,
            )
            draw.text((sc_pill_x + sc_pill_w // 2, 293), scene_label, font=scf, fill=(255, 230, 200), anchor="mm")

        # 2. Headline in Safe Zone
        y = 345
        for line in h_lines:
            draw.text((width // 2 + 3, y + 3), line, font=hf, fill=(0, 0, 0), anchor="ma")
            draw.text((width // 2, y), line, font=hf, fill=headline_color, anchor="ma")
            y += int(hf.size * 1.15)

        # 3. Sub-headline
        if s_lines:
            y += 8
            for line in s_lines:
                draw.text((width // 2 + 1, y + 1), line, font=sf, fill=(0, 0, 0), anchor="ma")
                draw.text((width // 2, y), line, font=sf, fill=sub_color, anchor="ma")
                y += int(sf.size * 1.25)

        # 4. Platform-Distinct Call-to-Action / Conversion Pill
        # For Reels: Beat 0 (hook) has NO bottom pill clutter so the hook breathes!
        show_cta = True
        if format_type == "reel" and idx == 0 and total_scenes > 1:
            show_cta = False  # Let hook have maximum breathing room

        if show_cta:
            ff = _font(max(24, width // 38), bold=True)
            resolved_cta = cta_text or chrome_cta

            cta_w = draw.textlength(resolved_cta, font=ff)
            cta_pill_w = int(cta_w + 40)
            cta_pill_x = (width - cta_pill_w) // 2
            pill_outline = (220, 60, 40) if format_type == "short" else _GOLD
            draw.rounded_rectangle(
                [(cta_pill_x, 1568), (cta_pill_x + cta_pill_w, 1612)],
                radius=14,
                fill=(18, 12, 7, 230),
                outline=pill_outline,
                width=1,
            )
            draw.text((width // 2, 1590), resolved_cta, font=ff, fill=_CREAM, anchor="mm")

    else:
        # Standard 1:1 or non-tall format
        # Warm radial glow behind the jar
        glow_color = (130, 90, 36) if boost_exposure else (65, 42, 18)
        glow_y = int(height * 0.64)
        _radial_glow(canvas, width // 2, glow_y, int(width * 0.90), color=glow_color)

        try:
            jar = _knockout_white(Image.open(jar_path))
            target_h = int(height * 0.46)
            ratio = target_h / jar.height
            jar = jar.resize((int(jar.width * ratio), target_h), resample=resample_filter)
            if jar.width > int(width * 0.78):
                r = int(width * 0.78) / jar.width
                jar = jar.resize((int(jar.width * r), int(jar.height * r)), resample=resample_filter)

            jx = (width - jar.width) // 2
            jy = int(height * 0.50)
            canvas.paste(jar, (jx, jy), jar)
        except Exception as e:
            logger.warning("[cine] jar paste failed: %s", e)
            return None

        draw = ImageDraw.Draw(canvas)
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
    if on_date is None:
        date_str = today_ist().isoformat()
    elif hasattr(on_date, "isoformat"):
        date_str = on_date.isoformat()
    else:
        date_str = str(on_date)[:10]
    os.makedirs(_OUT_DIR, exist_ok=True)
    out = os.path.join(_OUT_DIR, f"{label}_{date_str}.jpg")
    canvas.save(out, "JPEG", quality=90)

    try:
        from content_generator.creative.jar_provenance import record_jar_provenance
        record_jar_provenance(out, jar_asset_id=jar_path, render_source="cinematic_real_jar")
    except Exception as pe:
        logger.debug("[cinematic_frame] Provenance recording skipped: %s", pe)

    return out
