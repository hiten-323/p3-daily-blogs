"""
Real Jar Composer — brand images built FROM actual jar photos, not AI guesses.

Why this exists:
  FLUX / Pollinations are text-to-image APIs. They cannot see reference
  images — listing file paths in the prompt does nothing. Result: invented
  jars with gibberish labels posted to Instagram.

This module guarantees the real product:
  - Base: an actual photo from brand_assets/puritybeans_*.png
    (product-aware, rotates through products/sizes/angles by day+slide
    so no two posts look the same)
  - Canvas: brand palette (#0D0905 espresso, #C8962E gold, #F5EED8 cream)
  - Overlay: slide headline + body + Purity Beans / p3online.in footer
  - Pillow only — works on any runner, zero API calls, zero hallucination.
"""
from __future__ import annotations
import logging
import os
import re
import unicodedata

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_ASSETS  = "brand_assets"

_BG     = (13, 9, 5)        # #0D0905 espresso black
_GOLD   = (200, 150, 46)    # #C8962E
_CREAM  = (245, 238, 216)   # #F5EED8
_MUTED  = (170, 150, 120)

_THEMES = [
    # 0: Espresso Obsidian (Deep roast espresso dark canvas, warm amber softbox glow, gold accents)
    {
        "bg": (13, 9, 6),
        "bg_top": (13, 9, 6),
        "bg_mid": (22, 15, 10),
        "table_top": (28, 19, 13),
        "table_bot": (16, 11, 8),
        "horizon": (140, 95, 45),
        "spotlight": (105, 68, 28),
        "pill_bg": (22, 15, 10, 220),
        "pill_border": (212, 163, 64, 230),
        "pill_text": (245, 225, 175),
        "accent": (212, 163, 64),
        "text_primary": (255, 248, 238),
        "text_body": (225, 208, 182),
        "footer_bg": (14, 10, 7),
    },
    # 1: Roasted Mocha & Velvet Walnut (Rich dark cocoa tone, warm honey studio light)
    {
        "bg": (18, 11, 8),
        "bg_top": (18, 11, 8),
        "bg_mid": (32, 20, 14),
        "table_top": (38, 24, 16),
        "table_bot": (22, 14, 10),
        "horizon": (160, 110, 55),
        "spotlight": (120, 75, 32),
        "pill_bg": (26, 17, 12, 220),
        "pill_border": (225, 175, 75, 230),
        "pill_text": (250, 232, 185),
        "accent": (225, 175, 75),
        "text_primary": (255, 250, 242),
        "text_body": (230, 215, 190),
        "footer_bg": (18, 12, 8),
    },
    # 2: Artisan Cafe Copper (Warm roasted hazelnut with copper-amber directional studio lighting)
    {
        "bg": (20, 13, 10),
        "bg_top": (20, 13, 10),
        "bg_mid": (36, 22, 16),
        "table_top": (32, 21, 15),
        "table_bot": (18, 12, 8),
        "horizon": (150, 100, 50),
        "spotlight": (115, 70, 30),
        "pill_bg": (28, 18, 12, 220),
        "pill_border": (205, 155, 60, 230),
        "pill_text": (245, 225, 180),
        "accent": (205, 155, 60),
        "text_primary": (252, 246, 236),
        "text_body": (220, 205, 180),
        "footer_bg": (16, 11, 7),
    },
    # 3: Alabaster Latte Luxury (Warm ivory/latte studio wall with dark espresso table contrast)
    {
        "bg": (244, 238, 228),
        "bg_top": (244, 238, 228),
        "bg_mid": (235, 225, 210),
        "table_top": (42, 28, 18),
        "table_bot": (26, 17, 11),
        "horizon": (180, 130, 70),
        "spotlight": (255, 248, 235),
        "pill_bg": (32, 22, 15, 230),
        "pill_border": (195, 145, 45, 230),
        "pill_text": (245, 230, 195),
        "accent": (195, 145, 45),
        "text_primary": (24, 16, 11),
        "text_body": (65, 48, 35),
        "footer_bg": (22, 15, 10),
    },
]

_PRODUCTS = ["ultra_blend", "bold", "purista", "purica"]
_SIZES    = ["100g", "50g"]
_ANGLES   = ["front", "lifestyle", "side", "variant"]


def _all_jar_photos() -> list[str]:
    paths = []
    for p in _PRODUCTS:
        for s in _SIZES:
            for a in _ANGLES:
                fp = os.path.join(_ASSETS, f"puritybeans_{p}_{s}_{a}.png")
                if os.path.exists(fp):
                    paths.append(fp)
    return paths


# ── Overlay safety ────────────────────────────────────────────────────────────
# brand_assets/ holds two different kinds of file under the same naming scheme:
#
#   1. studio shots  — jar on a white sweep. The composer owns the whole canvas,
#                      so a headline can go anywhere. Detectable with certainty.
#   2. finished creatives — full-bleed images that ALREADY carry their own
#                      headline, feature bullets and footer (the agency deliverables).
#                      Drawing our headline on top collides with theirs.
#
# The filename says nothing about which is which — puritybeans_bold_50g_lifestyle
# is a finished creative, puritybeans_bold_100g_lifestyle is a clean photo. So the
# rule is safe-by-default: only provably-clean assets receive text. A full-bleed
# photo the founder KNOWS is text-free can be opted in via brand_assets/overlay_safe.txt.
_OVERLAY_SAFE_LIST = os.path.join(_ASSETS, "overlay_safe.txt")
_overlay_safe_cache: dict[str, bool] = {}


def _explicit_overlay_safe() -> set[str]:
    """Filenames the founder has opted in (one per line, '#' comments allowed)."""
    names: set[str] = set()
    if not os.path.exists(_OVERLAY_SAFE_LIST):
        return names
    try:
        with open(_OVERLAY_SAFE_LIST, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    names.add(line)
    except Exception as e:
        logger.warning("[real_jar] could not read %s: %s", _OVERLAY_SAFE_LIST, e)
    return names


def _has_white_background(path: str) -> bool:
    """True when all four corners are white — i.e. a studio sweep, not full-bleed."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        w, h = im.size
        for (x, y) in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            bx = max(0, min(x - 12, w - 24))
            by = max(0, min(y - 12, h - 24))
            patch = im.crop((bx, by, bx + 24, by + 24)).resize((1, 1)).getpixel((0, 0))
            if min(patch) <= 235:
                return False
        return True
    except Exception as e:
        logger.debug("[real_jar] background probe failed for %s: %s", path, e)
        return False


def is_overlay_safe(path: str) -> bool:
    """Can we draw a headline over this asset without colliding with baked-in copy?"""
    key = os.path.basename(path)
    if key not in _overlay_safe_cache:
        _overlay_safe_cache[key] = key in _explicit_overlay_safe() or _has_white_background(path)
    return _overlay_safe_cache[key]


def pick_jar_photo(day: int, idx: int = 0, product: str | None = None,
                   overlay_safe: bool = False, prefer_front: bool = True) -> str | None:
    """
    Deterministically rotate through real jar photos so posts differ daily.

    overlay_safe=True restricts the pool to assets that carry no copy of their own.
    prefer_front=False opts back into the rear label — the only slide that wants
    it is one arguing the ingredient panel ("read the label, no chicory").
    """
    everything = _all_jar_photos()
    pool = everything
    if product:
        pool = [p for p in pool if f"_{product}_" in p] or everything

    if overlay_safe:
        safe = [p for p in pool if is_overlay_safe(p)]
        if not safe:
            # Widen before giving up: a different product still beats overlaying
            # a headline onto a finished creative.
            safe = [p for p in everything if is_overlay_safe(p)]
        # Prefer front-facing hero presentations (front shots or clean lifestyle hero photos).
        # Exclude rear label side shots (barcode, batch number, directions for use).
        if prefer_front:
            heroes = [p for p in safe if "_side" not in os.path.basename(p).lower()]
            safe = heroes or safe
        if safe:
            pool = safe
        else:
            logger.warning(
                "[real_jar] No overlay-safe asset available — falling back to %s. "
                "Headline may collide with copy baked into the image.",
                os.path.basename(pool[0]) if pool else "nothing")

    if not pool:
        logger.warning("[real_jar] No jar photos found in %s", _ASSETS)
        return None
    return pool[(day * 3 + idx) % len(pool)]


# Windows names are what the founder previews with; the Linux names are what
# actually exists on the ubuntu-latest runner that renders the live posts.
# Listing only the Windows names silently downgraded every CI-rendered slide to
# Pillow's bitmap default (missing glyphs -> tofu boxes). Keep both, per role.
_FONT_ROLES = {
    # elegant serif for headlines
    "title":  (["georgiab.ttf", "georgia.ttf", "timesbd.ttf", "times.ttf", "arialbd.ttf"],
               ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf",
                "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]),
    # clean sans for body copy
    "body":   (["segoeui.ttf", "calibri.ttf", "arial.ttf"],
               ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"]),
    # bold sans for the footer strip
    "footer": (["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"],
               ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf"]),
}
_LINUX_FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/msttcorefonts",
    "/usr/share/fonts/truetype/freefont",
)
_font_fallback_warned = False


def _scan_for_any_ttf() -> str | None:
    """Last resort before the bitmap default: any real TrueType file on the box."""
    for root in ("/usr/share/fonts", "/usr/local/share/fonts"):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in sorted(files):
                if fn.lower().endswith((".ttf", ".otf")):
                    return os.path.join(dirpath, fn)
    return None


def knockout_white(img):
    """
    Return an RGBA jar with the white studio sweep cleanly made transparent,
    cropped to the jar itself. Flood-fills inward from boundary seeds (thresh=95)
    and removes residual studio sweep floor shadow while preserving whites
    inside the authentic label and cap.
    """
    from PIL import Image, ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    seeds = (
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
    )
    for seed in seeds:
        try:
            ImageDraw.floodfill(img, seed, (0, 0, 0, 0), thresh=95)
        except Exception as e:
            logger.debug("[real_jar] floodfill at %s failed: %s", seed, e)
    # Clean residual studio floor sweep shadow under the glass base (zero memory overhead)
    try:
        y_start = int(h * 0.85)
        pix = img.load()
        for y in range(y_start, h):
            for x in range(w):
                r, g, b, a = pix[x, y]
                if a > 0 and r > 120 and g > 120 and b > 120:
                    if abs(r - g) < 25 and abs(r - b) < 25 and abs(g - b) < 25:
                        pix[x, y] = (r, g, b, 0)
    except Exception as e:
        logger.debug("[real_jar] floor shadow cleaning skipped: %s", e)
    try:
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)      # drop the transparent margin
    except Exception as e:
        logger.debug("[real_jar] bbox crop failed: %s", e)
    return img


def _font(role: str, size: int):
    global _font_fallback_warned
    from PIL import ImageFont

    win_names, nix_names = _FONT_ROLES.get(role, _FONT_ROLES["body"])

    candidates: list[str] = []
    if os.name == "nt":
        for c in win_names:
            candidates += [c, os.path.join("C:\\Windows\\Fonts", c)]
    else:
        for c in nix_names:
            candidates += [os.path.join(d, c) for d in _LINUX_FONT_DIRS]
            candidates.append(c)
        # msttcorefonts, when present, gives the founder's intended look
        for c in win_names:
            candidates.append(os.path.join("/usr/share/fonts/truetype/msttcorefonts", c))

    for c in candidates:
        try:
            return ImageFont.truetype(c, size=size)
        except Exception:
            continue

    found = _scan_for_any_ttf()
    if found:
        try:
            return ImageFont.truetype(found, size=size)
        except Exception as e:
            logger.debug("[real_jar] scanned font %s unusable: %s", found, e)

    # Never silent: the bitmap default is what produced the tofu boxes.
    if not _font_fallback_warned:
        _font_fallback_warned = True
        logger.warning(
            "[real_jar] NO TrueType font resolved for role=%s — falling back to "
            "Pillow's bitmap default. Rendered text will look degraded.", role)
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


# ── Scaffolding labels ────────────────────────────────────────────────────────
# The LLM echoes the prompt's own structure into the copy ("Slide 1:", "**Frame
# 2**", "[Slide 3]", "Hook:"). Rendered into an image it reads as a leaked
# template. Two patterns because the risk is asymmetric:
#
#   LOOSE — pure template words. A trailing number alone is enough to strip,
#           because "Slide 1 It tastes bitter" is never real copy.
#   STRICT — words that also appear in genuine headlines ("Step into real
#           coffee"). These need an actual delimiter, so prose survives.
_NUM = r"\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten"
_NOISE = r"[\s*_#>\[\(\-]*"          # markdown bold, bullets, brackets, quotes
_DELIM = r"[:\-–—.)]"

_SCAFFOLD_LOOSE = re.compile(
    rf"^{_NOISE}"
    r"(slide|frame|scene|card|panel|hook|headline|caption|title|(?:text\s+)?overlay)"
    rf"\s*(?:no\.?|number|#)?\s*"
    rf"(?:(?:{_NUM})\s*[\]\)]?\s*{_DELIM}*|[\]\)]?\s*{_DELIM}+)"
    r"\s*[*_]*\s*", re.I)

_SCAFFOLD_STRICT = re.compile(
    rf"^{_NOISE}"
    r"(step|part|page|image|visual|body|copy|text)"
    rf"\s*(?:no\.?|number|#)?\s*(?:{_NUM})?\s*[\]\)]?\s*{_DELIM}+"
    r"\s*[*_]*\s*", re.I)

# ── Glyph safety ──────────────────────────────────────────────────────────────
# Fixing tofu by listing the characters that broke is whack-a-mole — the next
# unlisted glyph ships to Instagram. Instead: map the symbols worth keeping to
# ASCII equivalents, then drop anything still non-ASCII. On-screen brand copy is
# English, so this is total coverage regardless of which font the runner resolves.
_GLYPH_MAP = {
    "•": "-", "·": "-", "‧": "-", "▪": "-", "●": "-", "‣": "-",
    "–": "-", "—": "-", "―": "-", "‑": "-", "−": "-",
    "'": "'", "'": "'", "‚": ",", """: '"', """: '"', "„": '"',
    "…": "...", "→": "->", "←": "<-", "⇒": "=>", "↑": "^", "↓": "v",
    "×": "x", "÷": "/", "±": "+/-", "≈": "~", "≠": "!=", "≤": "<=", "≥": ">=",
    "™": "(TM)", "®": "(R)", "©": "(C)", "°": " deg",
    "★": "*", "☆": "*", "✓": "+", "✔": "+", "✗": "x", "✘": "x",
    "₹": "Rs ", "€": "EUR ", "£": "GBP ", "¢": "c",
    " ": " ", "​": "", " ": " ", " ": " ",
}


def _sanitize_text(text: str) -> str:
    """
    Last line of defence before pixels: no 'Slide 1:' labels, no unrenderable
    glyphs. Render path only — Instagram captions keep their emoji.
    """
    t = str(text or "").strip()

    for _ in range(3):                       # handles "Slide 1: Hook: ..."
        new = _SCAFFOLD_STRICT.sub("", _SCAFFOLD_LOOSE.sub("", t)).strip()
        if new == t:
            break
        t = new

    for bad, good in _GLYPH_MAP.items():
        t = t.replace(bad, good)
    # Decompose accents (é -> e + mark) so the base letter survives the drop.
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if ord(ch) < 128)
    return re.sub(r"\s{2,}", " ", t).strip()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    text = _sanitize_text(text)
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:4]


def compose_post_image(
    headline: str,
    body: str = "",
    day: int = 0,
    idx: int = 0,
    width: int = 1080,
    height: int = 1080,
    product: str | None = None,
    label: str = "brand_post",
) -> str | None:
    """
    Build one branded image: real jar photo + headline + body + footer.
    Returns saved file path, or None if Pillow/photos unavailable.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        logger.warning("[real_jar] Pillow not installed")
        return None

    # Any on-screen copy means we need a substrate with no copy of its own.
    needs_clean_substrate = bool(str(headline or "").strip() or str(body or "").strip())
    jar_path = pick_jar_photo(day, idx, product, overlay_safe=needs_clean_substrate)
    if not jar_path:
        return None

    # Cover mode only applies to full-bleed photos. A white studio sweep is
    # composited jar-on-canvas instead.
    is_lifestyle = ("lifestyle" in os.path.basename(jar_path).lower()
                    and not _has_white_background(jar_path))

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        lower_label = str(label or "").lower()
        if "facebook" in lower_label:
            target_platform = "facebook"
        elif "youtube" in lower_label or "yt_" in lower_label or "short" in lower_label:
            target_platform = "youtube"
        else:
            target_platform = "instagram"
        dirs = get_visual_adaptation_directives(platform=target_platform)
    except Exception:
        dirs = {}

    # Rotate through brand themes for visual diversity and contrast
    # When exposure boost is requested, prefer light warm cream or golden sunrise over pure dark espresso
    if dirs.get("boost_exposure"):
        theme_idx = (day + idx) % 3
    else:
        theme_idx = (day * 2 + idx) % len(_THEMES)
    theme = _THEMES[theme_idx]

    canvas = Image.new("RGB", (width, height), theme["bg"])

    # 1. Process and draw/paste the main background or jar photo
    try:
        jar = Image.open(jar_path).convert("RGB")
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.LANCZOS

        if is_lifestyle:
            # Lifestyle photo: scale to COVER the entire canvas, crop center
            img_ratio = jar.width / jar.height
            canvas_ratio = width / height
            if img_ratio > canvas_ratio:
                new_h = height
                new_w = int(height * img_ratio)
            else:
                new_w = width
                new_h = int(width / img_ratio)
            
            jar = jar.resize((new_w, new_h), resample_filter)
            x_offset = (new_w - width) // 2
            y_offset = (new_h - height) // 2
            jar = jar.crop((x_offset, y_offset, x_offset + width, y_offset + height))
            canvas.paste(jar, (0, 0))
            
            # Subtle luxury gradient scrim:
            # - Top gradient: ensures category pill, headline, and body copy pop with high legibility
            # - Bottom gradient: ensures brand signature is crisp
            # - Middle: transparent so the real jar and lifestyle scene stay vivid
            scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            spx = scrim.load()
            top_bound = int(height * 0.42)
            bot_bound = int(height * 0.86)
            for y in range(height):
                if y < top_bound:
                    alpha = int(185 * (1.0 - (y / top_bound) ** 1.4))
                    for x in range(width):
                        spx[x, y] = (12, 8, 5, alpha)
                elif y > bot_bound:
                    alpha = int(200 * ((y - bot_bound) / (height - bot_bound)))
                    for x in range(width):
                        spx[x, y] = (10, 7, 4, alpha)
            canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim).convert("RGB")
        else:
            # Studio setting: Studio Wall (upper ~68%) + Ground Tabletop Surface (bottom ~32%)
            table_h = int(height * 0.32)
            table_y = height - table_h

            # Studio wall backdrop gradient
            bg_top = theme.get("bg_top", theme["bg"])
            bg_mid = theme.get("bg_mid", theme["bg"])
            for y in range(table_y):
                f = y / max(1, table_y)
                c = tuple(int(bg_top[i] + (bg_mid[i] - bg_top[i]) * f) for i in range(3))
                ImageDraw.Draw(canvas).line([(0, y), (width, y)], fill=c)

            # Softbox radial glow centered on the product scene
            try:
                glow_size = int(width * 0.95)
                glow_mask = Image.new("L", (glow_size, glow_size), 0)
                glow_draw = ImageDraw.Draw(glow_mask)
                for r in range(glow_size // 2, 0, -3):
                    alpha = int(195 * (1.0 - (r / (glow_size // 2))) ** 1.8)
                    glow_draw.ellipse(
                        [(glow_size // 2 - r, glow_size // 2 - r), 
                         (glow_size // 2 + r, glow_size // 2 + r)], 
                        fill=alpha
                    )
                glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(38))
                spotlight = Image.new("RGB", (glow_size, glow_size), theme["spotlight"]) 
                gx = (width - glow_size) // 2
                gy = int(height * 0.20)
                canvas.paste(spotlight, (gx, gy), mask=glow_mask)
            except Exception as e:
                logger.debug("[real_jar] Radial spotlight failed: %s", e)

            # Ground Tabletop Surface
            table_surf = Image.new("RGBA", (width, table_h), (0, 0, 0, 0))
            t_top = theme.get("table_top", (26, 18, 12))
            t_bot = theme.get("table_bot", (16, 11, 8))
            tpx = table_surf.load()
            for y in range(table_h):
                f = y / max(1, table_h)
                c = tuple(int(t_top[i] + (t_bot[i] - t_top[i]) * f) for i in range(3))
                for x in range(width):
                    tpx[x, y] = (c[0], c[1], c[2], 255)
            
            # Subtle warm horizon line
            tdraw = ImageDraw.Draw(table_surf)
            horizon_color = theme.get("horizon", (140, 95, 45))
            tdraw.line([(0, 0), (width, 0)], fill=horizon_color, width=2)
            canvas.paste(table_surf.convert("RGB"), (0, table_y))

            # Clean knockout of the authentic jar (preserves internal whites, drops white sweep)
            jar = knockout_white(Image.open(jar_path))

            # Sizing and placement (adapts according to audit directives)
            break_centered = bool(dirs.get("break_centered_catalog"))
            target_h = int(height * (0.45 if break_centered else 0.52))
            ratio = target_h / jar.height
            jar = jar.resize((int(jar.width * ratio), target_h), resample_filter)
            if jar.width > width - 80:
                r = (width - 80) / jar.width
                jar = jar.resize((width - 80, int(jar.height * r)), resample_filter)

            if break_centered:
                side = -1 if (day + idx) % 2 else 1
                jx = max(20, min(width - jar.width - 20, int((width - jar.width) / 2 + side * width * 0.10)))
                jy = height - jar.height - int(height * 0.07)
            else:
                jx = (width - jar.width) // 2
                jy = height - jar.height - int(height * 0.07)

            # Ground Contact Shadow + Ambient Occlusion (grounds jar physically on tabletop)
            try:
                shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow_layer)
                
                # Diffuse cast shadow
                s_w = int(jar.width * 1.35)
                s_h = int(jar.height * 0.10)
                s_x = jx + (jar.width - s_w) // 2
                s_y = jy + jar.height - int(s_h * 0.50)
                sdraw.ellipse([(s_x, s_y), (s_x + s_w, s_y + s_h)], fill=(6, 4, 2, 140))
                
                # Tight ambient occlusion contact shadow under the glass base
                c_w = int(jar.width * 0.94)
                c_h = int(jar.height * 0.04)
                c_x = jx + (jar.width - c_w) // 2
                c_y = jy + jar.height - int(c_h * 0.70)
                sdraw.ellipse([(c_x, c_y), (c_x + c_w, c_y + c_h)], fill=(2, 1, 1, 230))
                
                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
                canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer).convert("RGB")
            except Exception as se:
                logger.debug("[real_jar] Shadow compositing skipped: %s", se)

            canvas.paste(jar, (jx, jy), jar)       # alpha mask = the authentic jar itself
            
    except Exception as e:
        logger.warning("[real_jar] Could not process jar photo %s: %s", jar_path, e)
        return None

    draw = ImageDraw.Draw(canvas)

    # 1. Category Badge Pill in upper area
    pill_text = "100% COFFEE  |  ZERO CHICORY"
    hl_lower = (headline or "").lower()
    if "chicory" in hl_lower:
        pill_text = "THE CHICORY TEST  |  100% PURE"
    elif "label" in hl_lower or "ingredient" in hl_lower:
        pill_text = "LABEL TRUTH  |  100% COFFEE"
    elif "instant" in hl_lower:
        pill_text = "INSTANT COFFEE AUDIT"
    elif "taste" in hl_lower or "bitter" in hl_lower:
        pill_text = "PURE TASTE STANDARD"

    pill_text = _sanitize_text(pill_text)
    p_font = _font("footer", max(17, width // 44))
    pw = int(draw.textlength(pill_text, font=p_font))
    px = (width - pw) // 2
    py = int(height * 0.048)
    pad_x, pad_y = int(width * 0.022), int(height * 0.008)

    try:
        pill_box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pill_box)
        pdraw.rounded_rectangle(
            [(px - pad_x, py - pad_y), (px + pw + pad_x, py + p_font.size + pad_y)],
            radius=16,
            fill=theme.get("pill_bg", (20, 14, 9, 220)),
            outline=theme.get("pill_border", theme["accent"]),
            width=2,
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), pill_box).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        draw.text((width // 2, py + p_font.size // 2), pill_text, font=p_font,
                  fill=theme.get("pill_text", theme["accent"]), anchor="mm")
    except Exception as pe:
        logger.debug("[real_jar] Pill box skipped: %s", pe)

    # 2. Headline (top area)
    margin = int(width * 0.08)
    max_w  = width - 2 * margin
    h_font = _font("title", max(34, width // 15))
    y = py + p_font.size + pad_y + int(height * 0.025)
    for line in _wrap(draw, headline.upper(), h_font, max_w):
        draw.text((width // 2 + 2, y + 2), line, font=h_font, fill=(0, 0, 0, 200), anchor="ma")
        draw.text((width // 2, y), line, font=h_font, fill=theme["text_primary"], anchor="ma")
        y += int(h_font.size * 1.18)

    # 3. Body
    if body:
        b_font = _font("body", max(19, width // 35))
        y += int(height * 0.015)
        for line in _wrap(draw, body, b_font, max_w):
            draw.text((width // 2 + 1, y + 1), line, font=b_font, fill=(0, 0, 0, 170), anchor="ma")
            draw.text((width // 2, y), line, font=b_font, fill=theme["text_body"], anchor="ma")
            y += int(b_font.size * 1.28)

    # 4. Refined Minimalist Brand Footer (replaces rigid full-width yellow block)
    f_font = _font("footer", max(16, width // 44))
    fy = height - int(height * 0.040)
    draw.line([(int(width * 0.08), fy - 16), (int(width * 0.92), fy - 16)], fill=theme["accent"], width=1)
    footer_text = _sanitize_text("PURITY BEANS  |  100% PURE COFFEE  |  p3online.in")
    draw.text((width // 2, fy), footer_text, font=f_font, fill=theme["accent"], anchor="mm")

    # Save
    import io
    from content_generator.core.ist_dates import today_ist
    os.makedirs(_OUT_DIR, exist_ok=True)
    date_str = today_ist().isoformat()
    path = os.path.join(_OUT_DIR, f"{label}_{date_str}.jpg")
    canvas.save(path, "JPEG", quality=88)
    logger.info("[real_jar] Composed %s from real photo %s", path, os.path.basename(jar_path))

    # Record verified real-jar provenance
    try:
        from content_generator.creative.jar_provenance import record_jar_provenance
        record_jar_provenance(path, jar_asset_id=jar_path, render_source="real_jar")
    except Exception as e:
        logger.debug("[real_jar] Provenance recording skipped: %s", e)

    return path


def compose_carousel_slides(slides: list[dict], day: int) -> list[str]:
    """One branded 1080x1080 image per slide — each with a DIFFERENT real jar photo."""
    paths = []
    for i, slide in enumerate(slides):
        if isinstance(slide, str):
            heading, body = slide, ""
        else:
            heading = str(slide.get("heading") or slide.get("title") or "")
            body    = str(slide.get("body") or "")[:160]
        if not heading:
            continue
        p = compose_post_image(
            headline=heading, body=body, day=day, idx=i,
            width=1080, height=1080, label=f"carousel_slide_{i+1}_day{day}",
        )
        if p:
            paths.append(p)
    return paths


def compose_reel_thumbnail(reel: dict, day: int, label: str = "reel_1") -> str | None:
    """9:16 thumbnail from the reel's hook text + a real jar photo."""
    headline = str(reel.get("hook_text") or reel.get("hook") or "REAL COFFEE. ZERO CHICORY.")
    return compose_post_image(
        headline=headline, body="", day=day, idx=7,
        width=1080, height=1920, label=f"{label}_thumb_day{day}",
    )
