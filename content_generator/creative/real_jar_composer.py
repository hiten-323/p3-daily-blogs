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
        # Prefer the FRONT of the jar. The _side shots are the back label —
        # barcode, batch number, directions for use — which reads as a warehouse
        # photo rather than a hero shot. Fall back to any safe asset if needed.
        if prefer_front:
            fronts = [p for p in safe if "_front" in os.path.basename(p).lower()]
            safe = fronts or safe
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
    Return an RGBA jar with the white studio sweep made transparent, cropped to
    the jar itself. Flood-fills inward from the corners so whites *inside* the
    label and cap survive. Without this the sweep pastes as a hard white
    rectangle on the espresso canvas.
    """
    from PIL import Image, ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        try:
            ImageDraw.floodfill(img, seed, (0, 0, 0, 0), thresh=40)
        except Exception as e:
            logger.debug("[real_jar] floodfill at %s failed: %s", seed, e)
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

    canvas = Image.new("RGB", (width, height), _BG)

    # 1. Process and draw/paste the main background or jar photo
    try:
        jar = Image.open(jar_path).convert("RGB")
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.LANCZOS

        if is_lifestyle:
            # Lifestyle photo: scale to COVER the entire canvas, crop center, and apply dark overlay
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
            
            # Apply dark espresso overlay to ensure high copy contrast
            overlay = Image.new("RGBA", (width, height), (13, 9, 5, 130)) # ~50% opacity
            canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        else:
            # Regular jar photo: draw radial spotlight and paste jar centered at bottom
            try:
                glow_size = int(width * 0.6)
                glow_mask = Image.new("L", (glow_size, glow_size), 0)
                glow_draw = ImageDraw.Draw(glow_mask)
                for r in range(glow_size // 2, 0, -2):
                    alpha = int(210 * (1.0 - (r / (glow_size // 2))) ** 2)
                    glow_draw.ellipse(
                        [(glow_size // 2 - r, glow_size // 2 - r), 
                         (glow_size // 2 + r, glow_size // 2 + r)], 
                        fill=alpha
                    )
                glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(20))
                gold_glow = Image.new("RGB", (glow_size, glow_size), (40, 28, 12)) 
                gx = (width - glow_size) // 2
                gy = height - max(8, height // 90) - int(height * 0.55)
                canvas.paste(gold_glow, (gx, gy), mask=glow_mask)
            except Exception as e:
                logger.debug("[real_jar] Radial spotlight failed: %s", e)

            # Cut the white sweep away before pasting, or the studio background
            # lands as a hard white rectangle over the espresso canvas and the
            # radial spotlight drawn above is completely hidden behind it.
            jar = knockout_white(Image.open(jar_path))

            # Paste jar at bottom 55%
            target_h = int(height * 0.52)
            ratio    = target_h / jar.height
            jar      = jar.resize((int(jar.width * ratio), target_h), resample_filter)
            if jar.width > width - 80:
                r   = (width - 80) / jar.width
                jar = jar.resize((width - 80, int(jar.height * r)), resample_filter)
            jx = (width - jar.width) // 2
            jy = height - max(8, height // 90) - jar.height - int(height * 0.02)
            canvas.paste(jar, (jx, jy), jar)       # alpha mask = the jar itself
            
    except Exception as e:
        logger.warning("[real_jar] Could not process jar photo %s: %s", jar_path, e)
        return None

    draw = ImageDraw.Draw(canvas)
    bar = max(8, height // 90)
    draw.rectangle([(0, 0), (width, bar)], fill=_GOLD)
    draw.rectangle([(0, height - bar), (width, height)], fill=_GOLD)

    # Headline (top area)
    margin = int(width * 0.07)
    max_w  = width - 2 * margin
    h_font = _font("title", max(34, width // 14))
    y      = int(height * 0.06)
    for line in _wrap(draw, headline.upper(), h_font, max_w):
        draw.text((width // 2, y), line, font=h_font, fill=_CREAM, anchor="ma")
        y += int(h_font.size * 1.18)

    # Body
    if body:
        b_font = _font("body", max(20, width // 32))
        y += int(height * 0.015)
        for line in _wrap(draw, body, b_font, max_w):
            draw.text((width // 2, y), line, font=b_font, fill=_MUTED, anchor="ma")
            y += int(b_font.size * 1.3)

    # Footer brand strip (above bottom gold bar, over dark strip)
    f_font = _font("footer", max(18, width // 36))
    strip_h = int(height * 0.045)
    
    # Gold separator line above the footer strip
    draw.line([(0, height - bar - strip_h), (width, height - bar - strip_h)], fill=_GOLD, width=2)
    
    draw.rectangle([(0, height - bar - strip_h), (width, height - bar)], fill=(20, 14, 8))
    draw.text((width // 2, height - bar - strip_h // 2),
              "PURITY BEANS  |  100% COFFEE, ZERO CHICORY  |  p3online.in",
              font=f_font, fill=_GOLD, anchor="mm")

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
