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


def _claim_pill(product, headline: str) -> str:
    """Badge copy that matches the jar. Unknown products stay on the slogan."""
    from content_generator.creative.cinematic_frame import _product_class
    hl = (headline or "").lower()
    kind = _product_class(product)
    # A headline can name Ultra Blend when the frame has no product yet.
    # It must not relabel a pure jar, including Gourmet Duo Mini, as 30% chicory.
    if kind == "unknown" and "ultra blend" in hl:
        kind = "ultra"
    if kind == "ultra":
        return "ULTRA BLEND  |  70% COFFEE  30% CHICORY"
    if kind == "pure":
        if "label" in hl or "ingredient" in hl:
            return "LABEL TRUTH  |  100% COFFEE"
        return "100% COFFEE  |  ZERO CHICORY"
    if "label" in hl or "ingredient" in hl:
        return "LABEL TRUTH  |  READ THE JAR"
    if "instant" in hl:
        return "INSTANT COFFEE AUDIT"
    return "INDIA'S CLEANEST INSTANT COFFEE"


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
    """Feed, story, or square hero. The jar is native-resolution and fully inside the safe zone."""
    from content_generator.creative.jar_frame import compose_conversion_frame
    fmt = "story" if height > int(width * 1.3) else "feed"
    return compose_conversion_frame(
        headline=headline,
        sub=body,
        product=product,
        day=day,
        idx=idx,
        width=width,
        height=height,
        label=label,
        format_name=fmt,
        out_dir=_OUT_DIR,
    )


def _wrap_lines(draw, text: str, font, max_w: int, max_lines: int = 8) -> list[str]:
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
    return lines[:max_lines]


def _get_studio_front_jar(day: int, idx: int) -> str | None:
    everything = _all_jar_photos()
    studio_fronts = [p for p in everything if _has_white_background(p) and "_front.png" in p.lower()]
    if not studio_fronts:
        studio_fronts = [p for p in everything if _has_white_background(p)]
    if not studio_fronts:
        return pick_jar_photo(day, idx, overlay_safe=True)
    return studio_fronts[(day * 3 + idx) % len(studio_fronts)]


def _draw_vector_arrow(draw, x: int, y: int, size: int = 12, fill=(212, 163, 64)):
    """Draw a vector right-arrow triangle so no font missing-glyph box ever occurs."""
    draw.polygon([(x, y - size // 2), (x + size, y), (x, y + size // 2)], fill=fill)


def compose_carousel_slide(
    heading: str,
    body: str,
    day: int,
    idx: int,
    total_slides: int,
    width: int = 1080,
    height: int = 1080,
    label: str = "carousel_slide",
    product: str | None = None,
) -> str | None:
    """
    Renders an editorial D2C Instagram carousel slide:
      - Slide 1: Hero Cover with category badge, punchy hook, real jar staging, and 'SWIPE' cue.
      - Middle Slides: Modern editorial cards formatted around the slide's actual body copy,
                       with slide index (e.g. '02 / 07') and progress tracking, without repetitive jar clutter.
      - Final Slide: High-converting CTA outro with Save & Share prompts, discount/order cues, and hero jar.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        logger.warning("[real_jar] Pillow not installed")
        return None

    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    theme = _THEMES[day % len(_THEMES)]
    total_slides = max(1, total_slides)

    is_cover = (idx == 0)
    is_outro = (idx == total_slides - 1 and total_slides > 1)
    is_middle = (not is_cover and not is_outro)
    try:
        from content_generator.publisher.surface_copy import clean_slide_copy
        heading, body = clean_slide_copy(heading, body, product)
    except Exception as exc:
        logger.debug("[real_jar] slide copy clean skipped: %s", exc)

    if is_cover or is_outro:
        from content_generator.creative.jar_frame import compose_conversion_frame
        return compose_conversion_frame(
            headline=heading,
            sub=body,
            product=product,
            day=day,
            idx=idx,
            width=width,
            height=height,
            label=label,
            format_name="carousel",
            out_dir=_OUT_DIR,
        )

    canvas = Image.new("RGB", (width, height), theme["bg"])

    # ── SLIDE 1: HERO COVER ───────────────────────────────────────────────────
    if is_cover:
        table_h = int(height * 0.34)
        table_y = height - table_h

        # Studio wall backdrop
        bg_top = theme.get("bg_top", theme["bg"])
        bg_mid = theme.get("bg_mid", theme["bg"])
        for y in range(table_y):
            f = y / max(1, table_y)
            c = tuple(int(bg_top[j] + (bg_mid[j] - bg_top[j]) * f) for j in range(3))
            ImageDraw.Draw(canvas).line([(0, y), (width, y)], fill=c)

        # Softbox radial spotlight
        try:
            glow_size = int(width * 0.95)
            glow_mask = Image.new("L", (glow_size, glow_size), 0)
            glow_draw = ImageDraw.Draw(glow_mask)
            for r in range(glow_size // 2, 0, -3):
                alpha = int(195 * (1.0 - (r / (glow_size // 2))) ** 1.8)
                glow_draw.ellipse(
                    [(glow_size // 2 - r, glow_size // 2 - r), (glow_size // 2 + r, glow_size // 2 + r)],
                    fill=alpha
                )
            glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(38))
            spotlight = Image.new("RGB", (glow_size, glow_size), theme["spotlight"])
            canvas.paste(spotlight, ((width - glow_size) // 2, int(height * 0.18)), mask=glow_mask)
        except Exception as e:
            logger.debug("[real_jar] Cover spotlight failed: %s", e)

        # Tabletop
        table_surf = Image.new("RGBA", (width, table_h), (0, 0, 0, 0))
        t_top = theme.get("table_top", (26, 18, 12))
        t_bot = theme.get("table_bot", (16, 11, 8))
        tpx = table_surf.load()
        for y in range(table_h):
            f = y / max(1, table_h)
            c = tuple(int(t_top[j] + (t_bot[j] - t_top[j]) * f) for j in range(3))
            for x in range(width):
                tpx[x, y] = (c[0], c[1], c[2], 255)
        tdraw = ImageDraw.Draw(table_surf)
        tdraw.line([(0, 0), (width, 0)], fill=theme.get("horizon", (140, 95, 45)), width=2)
        canvas.paste(table_surf.convert("RGB"), (0, table_y))

        # Real Jar Staging (guaranteed clean studio front photo)
        jar_path = _get_studio_front_jar(day, idx)
        if jar_path:
            try:
                jar = knockout_white(Image.open(jar_path))
                target_h = int(height * 0.44)
                ratio = target_h / jar.height
                jar = jar.resize((int(jar.width * ratio), target_h), resample_filter)
                jx = (width - jar.width) // 2
                jy = height - jar.height - int(height * 0.08)

                # Ground Shadows
                shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow_layer)
                s_w = int(jar.width * 1.35)
                s_h = int(jar.height * 0.10)
                s_x = jx + (jar.width - s_w) // 2
                s_y = jy + jar.height - int(s_h * 0.50)
                sdraw.ellipse([(s_x, s_y), (s_x + s_w, s_y + s_h)], fill=(6, 4, 2, 140))

                c_w = int(jar.width * 0.94)
                c_h = int(jar.height * 0.04)
                c_x = jx + (jar.width - c_w) // 2
                c_y = jy + jar.height - int(c_h * 0.70)
                sdraw.ellipse([(c_x, c_y), (c_x + c_w, c_y + c_h)], fill=(2, 1, 1, 230))

                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
                canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer).convert("RGB")
                canvas.paste(jar, (jx, jy), jar)
            except Exception as e:
                logger.debug("[real_jar] Cover jar staging failed: %s", e)

        draw = ImageDraw.Draw(canvas)

        # Top Bar: Slide Counter on Right
        counter_text = f"01 / {total_slides:02d}"
        cnt_font = _font("footer", 16)
        cw = int(draw.textlength(counter_text, font=cnt_font))
        cx = width - cw - 70
        cy = 52
        pill_box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pill_box)
        pdraw.rounded_rectangle([(cx - 14, cy - 8), (cx + cw + 14, cy + cnt_font.size + 8)],
                                radius=14, fill=theme.get("pill_bg", (20, 14, 9, 220)),
                                outline=theme.get("pill_border", theme["accent"]), width=1)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), pill_box).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        draw.text((cx + cw // 2, cy + cnt_font.size // 2), counter_text, font=cnt_font,
                  fill=theme.get("pill_text", theme["accent"]), anchor="mm")

        # Top Bar: Category Pill on Left
        pill_text = "THE CHICORY AUDIT  |  100% PURE"
        hl_lower = (heading or "").lower()
        if "instant" in hl_lower:
            pill_text = "INSTANT COFFEE AUDIT"
        elif "label" in hl_lower or "ingredient" in hl_lower:
            pill_text = "LABEL TRUTH  |  100% COFFEE"
        pw = int(draw.textlength(pill_text, font=cnt_font))
        px = 56
        pill_box2 = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pdraw2 = ImageDraw.Draw(pill_box2)
        pdraw2.rounded_rectangle([(px - 14, cy - 8), (px + pw + 14, cy + cnt_font.size + 8)],
                                 radius=14, fill=theme.get("pill_bg", (20, 14, 9, 220)),
                                 outline=theme.get("pill_border", theme["accent"]), width=1)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), pill_box2).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        draw.text((px + pw // 2, cy + cnt_font.size // 2), pill_text, font=cnt_font,
                  fill=theme.get("pill_text", theme["accent"]), anchor="mm")

        # Headline
        h_font = _font("title", 44)
        hy = 120
        max_w = width - 120
        for line in _wrap(draw, heading.upper(), h_font, max_w):
            draw.text((width // 2 + 2, hy + 2), line, font=h_font, fill=(0, 0, 0, 200), anchor="ma")
            draw.text((width // 2, hy), line, font=h_font, fill=theme["text_primary"], anchor="ma")
            hy += int(h_font.size * 1.18)

        # Sub-hook
        if body:
            b_font = _font("body", 22)
            hy += 12
            for line in _wrap(draw, body, b_font, max_w)[:2]:
                draw.text((width // 2 + 1, hy + 1), line, font=b_font, fill=(0, 0, 0, 180), anchor="ma")
                draw.text((width // 2, hy), line, font=b_font, fill=theme["text_body"], anchor="ma")
                hy += int(b_font.size * 1.25)

        # Swipe Cue Pill at Bottom Right with vector arrow
        swipe_text = "SWIPE"
        sw_font = _font("footer", 17)
        sw_w = int(draw.textlength(swipe_text, font=sw_font))
        sw_box_w = sw_w + 50
        sw_x = width - sw_box_w - 60
        sw_y = height - 100
        sw_box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw_box = ImageDraw.Draw(sw_box)
        sdraw_box.rounded_rectangle([(sw_x, sw_y - 8), (sw_x + sw_box_w, sw_y + sw_font.size + 10)],
                                    radius=18, fill=(28, 18, 11, 230),
                                    outline=theme["accent"], width=2)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), sw_box).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        draw.text((sw_x + 16, sw_y + sw_font.size // 2 + 1), swipe_text, font=sw_font,
                  fill=theme["accent"], anchor="lm")
        _draw_vector_arrow(draw, sw_x + sw_w + 26, sw_y + sw_font.size // 2 + 1, size=12, fill=theme["accent"])

        # Minimalist Brand Footer
        f_font = _font("footer", 15)
        fy = height - 36
        draw.line([(60, fy - 14), (width - 60, fy - 14)], fill=theme["accent"], width=1)
        draw.text((width // 2, fy), "PURITY BEANS  |  100% PURE COFFEE  |  p3online.in",
                  font=f_font, fill=theme["accent"], anchor="mm")

    # ── MIDDLE SLIDES: EDITORIAL VALUE CARDS ──────────────────────────────────
    elif is_middle:
        from content_generator.creative.surface_frames import compose_editorial_card
        return compose_editorial_card(
            heading=heading,
            body=body,
            day=day,
            idx=idx,
            total_slides=total_slides,
            width=width,
            height=height,
            label=label,
            product=product,
            out_dir=_OUT_DIR,
        )

    # Save
    from content_generator.core.ist_dates import today_ist
    os.makedirs(_OUT_DIR, exist_ok=True)
    date_str = today_ist().isoformat()
    path = os.path.join(_OUT_DIR, f"{label}_{date_str}.jpg")
    canvas.save(path, "JPEG", quality=90)
    logger.info("[real_jar] Composed carousel slide %d/%d -> %s", idx + 1, total_slides, path)
    from content_generator.creative.jar_frame import select_front_asset, write_text_card_geometry
    write_text_card_geometry(path)
    try:
        from content_generator.creative.jar_provenance import record_jar_provenance
        chosen = select_front_asset(product)
        if chosen:
            record_jar_provenance(path, jar_asset_id=chosen["path"], render_source="real_jar")
    except Exception as e:
        logger.debug("[real_jar] Provenance recording skipped: %s", e)
    return path


def compose_carousel_slides(slides: list[dict], day: int, product: str | None = None) -> list[str]:
    """
    Renders high-converting, professional 1080x1080 carousel slides:
      - Slide 1: Hero Cover with hook badge, headline, authentic jar, and 'SWIPE ->' cue.
      - Middle Slides: Editorial informational & comparison cards with slide numbers and progress tracking.
      - Final Slide: Outro CTA with Save & Share prompts and product staging.
    """
    paths = []
    total_slides = len(slides)
    for i, slide in enumerate(slides):
        if isinstance(slide, str):
            heading, body = slide, ""
        else:
            heading = str(slide.get("heading") or slide.get("title") or "")
            body = str(slide.get("body") or "")
        if not heading:
            continue
        p = compose_carousel_slide(
            heading=heading,
            body=body,
            day=day,
            idx=i,
            total_slides=total_slides,
            width=1080,
            height=1350,
            label=f"carousel_slide_{i+1}_day{day}",
            product=product,
        )
        if p:
            paths.append(p)
    return paths


def compose_reel_thumbnail(reel: dict, day: int, label: str = "reel_1") -> str | None:
    """9:16 thumbnail from the reel's hook text + a real jar photo."""
    headline = str(reel.get("hook_text") or reel.get("hook") or "READ THE LABEL")
    return compose_post_image(
        headline=headline, body="", day=day, idx=7, product=reel.get("product"),
        width=1080, height=1920, label=f"{label}_thumb_day{day}",
    )
