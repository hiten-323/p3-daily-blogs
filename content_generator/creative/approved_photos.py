"""
Approved Photos — official Purity Beans photography, used AS-IS.

Replaces AI/Pillow jar compositing (founder found composites unrealistic,
2026-10-14). Rules enforced here:
  * lifestyle / infographic photos: crop + resize to platform aspect ONLY.
    The crop window always contains the manifest jar_bbox (+margin) so the
    jar is never cut. Text overlays go only in the manifest text_zone and
    never on photos with baked copy (infographics get no overlay at all).
  * cutouts (white studio shots): only on a clean studio / solid brand
    canvas — never composited into a photographic scene.
  * blocked items (manifest "blocked": true) are never returned.
  * QA (fail-closed): jar fully in frame and sharp (Laplacian variance).
"""
from __future__ import annotations
import json
import logging
import os

logger = logging.getLogger(__name__)

_DIR = os.path.join("brand_assets", "approved_photos")
_MANIFEST = os.path.join(_DIR, "manifest.json")
_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
HANDLE = "@purepantryprovisions"
CTA = f"Follow {HANDLE}  •  Shop p3online.in"
_ESPRESSO, _GOLD, _CREAM = (13, 9, 5), (200, 150, 46), (245, 238, 216)
_MIN_SHARPNESS = float(os.getenv("APPROVED_PHOTO_MIN_SHARPNESS", "20"))
_cache: dict | None = None


def enabled() -> bool:
    return os.getenv("APPROVED_PHOTOS_ONLY", "1") != "0" and os.path.exists(_MANIFEST)


def load_manifest() -> dict:
    global _cache
    if _cache is None:
        with open(_MANIFEST, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


_REAL_SURFACES = ["ig_post", "ig_story", "carousel_cover", "carousel_middle", "carousel_cta",
                  "fb", "threads", "linkedin", "reel_thumb", "yt_thumb", "blog"]


def real_photos(sku: str | None = None) -> list[dict]:
    """Real (non-AI) photos dropped into <sku>/real/. Auto-priority over cutouts."""
    out = []
    for s in ("bold", "purica", "purista", "ultra_blend"):
        if sku and s != sku:
            continue
        d = os.path.join(_DIR, s, "real")
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            it = {"file": f"{s}/real/{fn}", "sku": s, "type": "real_photo",
                  "jar_bbox": [0, 0, 1, 1], "text_bboxes": [], "baked_copy": False,
                  "text_zone": "top", "allowed_surfaces": _REAL_SURFACES, "blocked": False}
            side = os.path.join(d, os.path.splitext(fn)[0] + ".json")
            if os.path.exists(side):
                try:
                    with open(side, encoding="utf-8") as f:
                        it.update(json.load(f))
                except Exception as e:
                    logger.warning("[approved_photos] bad sidecar %s: %s", side, e)
            if not it.get("blocked"):
                out.append(it)
    return out


def items(surface: str | None = None, sku: str | None = None,
          types: tuple[str, ...] | None = None) -> list[dict]:
    out = []
    for it in load_manifest().get("items", []) + real_photos():
        if it.get("blocked"):
            continue
        if surface and surface not in it.get("allowed_surfaces", []):
            continue
        if sku and it.get("sku") != sku:
            continue
        if types and it.get("type") not in types:
            continue
        if os.path.exists(os.path.join(_DIR, it["file"])):
            out.append(it)
    return out


def _norm_sku(product) -> str | None:
    if not product:
        return None
    p = str(product).lower().replace("-", "_").replace(" ", "_")
    for s in ("ultra_blend", "bold", "purista", "purica"):
        if s in p or (s == "ultra_blend" and "ultra" in p):
            return s
    return None


def pick(surface: str, day: int, idx: int = 0, product=None,
         types: tuple[str, ...] | None = None, want_overlay: bool = False) -> dict | None:
    sku = _norm_sku(product)
    # Never show another SKU's jar under copy about a specific SKU.
    pool = items(surface, sku, types) if sku else items(surface, None, types)
    if want_overlay:
        clean = [i for i in pool if i.get("text_zone")]
        pool = clean or pool
    if not pool:
        return None
    return pool[(day * 3 + idx) % len(pool)]


# ── geometry ──────────────────────────────────────────────────────────────
def protected_boxes(it: dict) -> list:
    """Jar + all baked-in text boxes (normalized). Crops must keep all of them."""
    return [list(it["jar_bbox"])] + [list(b) for b in it.get("text_bboxes", [])]


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def crop_window(w: int, h: int, bbox, tw: int, th: int, margin: float = 0.04):
    """Largest crop of aspect tw:th that fully contains bbox (+margin).
    Returns (box, ok). ok=False when the jar cannot fit — caller must pad
    (letterbox) instead of cutting the jar."""
    x0, y0, x1, y1 = bbox
    jx0, jy0 = max(0, (x0 - margin) * w), max(0, (y0 - margin) * h)
    jx1, jy1 = min(w, (x1 + margin) * w), min(h, (y1 + margin) * h)
    ar = tw / th
    cw, ch = (w, w / ar) if w / h < ar else (h * ar, h)
    if cw < jx1 - jx0 - 0.5 or ch < jy1 - jy0 - 0.5:
        return None, False
    cx, cy = (jx0 + jx1) / 2, (jy0 + jy1) / 2
    left = min(max(cx - cw / 2, 0), w - cw)
    top = min(max(cy - ch / 2, 0), h - ch)
    left = min(left, jx0); left = max(left, jx1 - cw)
    top = min(top, jy0); top = max(top, jy1 - ch)
    return (round(left), round(top), round(left + cw), round(top + ch)), True


def sharpness(img) -> float:
    from PIL import ImageFilter, ImageStat
    g = img.convert("L").filter(ImageFilter.FIND_EDGES)
    if g.size[0] > 8 and g.size[1] > 8:  # drop filter border artefacts
        g = g.crop((2, 2, g.size[0] - 2, g.size[1] - 2))
    return ImageStat.Stat(g).var[0]


def qa_jar(final, jar_px_box) -> list[str]:
    """Fail-closed QA on the rendered image. jar_px_box in final pixels."""
    errs = []
    W, H = final.size
    x0, y0, x1, y1 = jar_px_box
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
        errs.append("jar_cut_off")
    if (x1 - x0) * (y1 - y0) < 0.02 * W * H:
        errs.append("jar_too_small")
    crop = final.crop((max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))))
    if crop.size[0] < 8 or crop.size[1] < 8 or sharpness(crop) < _MIN_SHARPNESS:
        errs.append("jar_not_sharp")
    return errs


# ── text helpers ──────────────────────────────────────────────────────────
def _font(role, size):
    try:
        from content_generator.creative.real_jar_composer import _font as f
        return f(role, size)
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines=4):
    words, lines, cur = str(text or "").split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def _clean(text):
    try:
        from content_generator.creative.real_jar_composer import _sanitize_text
        return _sanitize_text(text)
    except Exception:
        return str(text or "").strip()


def _text_block(img, zone_box, headline, body, scrim=True, dark_text=False):
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = [int(v) for v in zone_box]
    if scrim:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle((x0, y0, x1, y1), radius=28, fill=(13, 9, 5, 165))
        img.alpha_composite(ov)
    d = ImageDraw.Draw(img)
    pad = int(min(x1 - x0, y1 - y0) * 0.08) + 12
    hw = img.size[0]
    hf, bf = _font("headline", max(30, hw // 22)), _font("body", max(22, hw // 38))
    col = _ESPRESSO if dark_text else _CREAM
    y = y0 + pad
    for ln in _wrap(d, _clean(headline).upper(), hf, x1 - x0 - 2 * pad, 3):
        d.text((x0 + pad, y), ln, font=hf, fill=col); y += int(hf.size * 1.15) if hasattr(hf, "size") else 40
    y += 8
    for ln in _wrap(d, _clean(body), bf, x1 - x0 - 2 * pad, 3):
        if y > y1 - pad:
            break
        d.text((x0 + pad, y), ln, font=bf, fill=_GOLD if not dark_text else (90, 60, 30)); y += int(bf.size * 1.3) if hasattr(bf, "size") else 30


def _footer(img, dark=False):
    from PIL import Image, ImageDraw
    W, H = img.size
    fh = max(54, H // 22)
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle((0, H - fh, W, H), fill=(13, 9, 5, 200))
    img.alpha_composite(ov)
    d = ImageDraw.Draw(img)
    f = _font("body", max(22, fh // 2 - 2))
    tw = d.textlength(CTA, font=f)
    d.text(((W - tw) / 2, H - fh + (fh - (f.size if hasattr(f, "size") else 20)) / 2 - 2), CTA, font=f, fill=_CREAM)
    return fh


# ── renderers ─────────────────────────────────────────────────────────────
def render_photo(it: dict, width: int, height: int, headline: str = "", body: str = "",
                 label: str = "approved") -> str | None:
    """Lifestyle / infographic: crop+resize only. The crop keeps the whole jar
    AND all baked-in text; otherwise the full photo is fitted over a blurred
    extension of itself (never cut)."""
    from PIL import Image, ImageFilter
    src = Image.open(os.path.join(_DIR, it["file"])).convert("RGB")
    w, h = src.size
    prot = protected_boxes(it)
    box, ok = crop_window(w, h, union(prot), width, height)
    if ok:
        scale = width / (box[2] - box[0])
        img = src.crop(box).resize((width, height), Image.LANCZOS).convert("RGBA")
        mp = lambda b: ((b[0] * w - box[0]) * scale, (b[1] * h - box[1]) * scale,
                        (b[2] * w - box[0]) * scale, (b[3] * h - box[1]) * scale)
    else:
        cs = max(width / w, height / h)
        bg = src.resize((int(w * cs) + 1, int(h * cs) + 1), Image.LANCZOS)
        bg = bg.crop(((bg.size[0] - width) // 2, (bg.size[1] - height) // 2,
                      (bg.size[0] - width) // 2 + width, (bg.size[1] - height) // 2 + height))
        bg = bg.filter(ImageFilter.GaussianBlur(40))
        bg = Image.blend(bg, Image.new("RGB", bg.size, _ESPRESSO), 0.35)
        scale = min(width / w, height / h)
        nw, nh = int(w * scale), int(h * scale)
        img = bg.convert("RGBA")
        ox, oy = (width - nw) // 2, (height - nh) // 2
        img.paste(src.resize((nw, nh), Image.LANCZOS), (ox, oy))
        mp = lambda b: (ox + b[0] * nw, oy + b[1] * nh, ox + b[2] * nw, oy + b[3] * nh)
    jar = mp(it["jar_bbox"])
    texts = [mp(b) for b in it.get("text_bboxes", [])]
    fh = _footer(img)
    band = None
    if headline and it.get("type") in ("lifestyle", "real_photo"):
        band = _band_box(width, height, [jar] + texts, fh)
        if band:
            _slim_band(img, band, headline, body)
    return _save(img, jar, label, os.path.join(_DIR, it["file"]), texts=texts, band=band)


MAX_BAND_FRAC = 0.15


def _overlaps(a, b, pad=0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _band_box(W, H, protected, footer_h):
    """Slim full-width band (<=15% H) at top or just above the footer that
    touches neither the jar nor any baked-in text. None if no room."""
    bh = int(H * 0.11)
    m = int(H * 0.025)
    for y0 in (m, H - footer_h - m - bh):
        band = (int(W * 0.05), y0, int(W * 0.95), y0 + bh)
        if not any(_overlaps(band, p, pad=12) for p in protected):
            return band
    return None


def _slim_band(img, band, headline, body):
    from PIL import Image, ImageDraw, ImageFilter
    x0, y0, x1, y1 = band
    bh = y1 - y0
    strip = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(strip).rounded_rectangle(band, radius=bh // 2, fill=(13, 9, 5, 95))
    img.alpha_composite(strip.filter(ImageFilter.GaussianBlur(2)))
    hf = _font("headline", max(28, int(bh * 0.36)))
    bf = _font("body", max(20, int(bh * 0.22)))
    d = ImageDraw.Draw(img)
    head = _clean(headline).upper()
    hsz = getattr(hf, "size", 28)
    while d.textlength(head, font=hf) > (x1 - x0) * 0.9 and hsz > 22:
        hsz -= 2
        hf = _font("headline", hsz)
    sub = _clean(body)
    lines = [(head, hf, _CREAM)] + ([(sub, bf, _GOLD)] if sub and d.textlength(sub, font=bf) <= (x1 - x0) * 0.9 else [])
    hs = [getattr(f, "size", 24) for _, f, _ in lines]
    y = y0 + (bh - sum(hs) - 6 * (len(lines) - 1)) / 2 - 2
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    pos = []
    for (t, f, c), hh in zip(lines, hs):
        tx = x0 + ((x1 - x0) - d.textlength(t, font=f)) / 2
        sd.text((tx + 2, y + 3), t, font=f, fill=(0, 0, 0, 170)); pos.append((tx, y, t, f, c)); y += hh + 6
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(img)
    for tx, ty, t, f, c in pos:
        d.text((tx, ty), t, font=f, fill=c)


_CARDS = {  # premium plain cards: soft paper + per-SKU muted brand tint
    "paper": (244, 239, 230),
    "bold": (236, 232, 240), "purica": (231, 238, 233),
    "purista": (242, 233, 231), "ultra_blend": (243, 236, 222),
}


def _apply_tone(img, tone: dict | None):
    """Global-only tone correction (whole image, uniform) — no local grading."""
    if not tone:
        return img
    from PIL import ImageEnhance
    img = ImageEnhance.Color(img).enhance(float(tone.get("saturation", 1)))
    img = ImageEnhance.Contrast(img).enhance(float(tone.get("contrast", 1)))
    return ImageEnhance.Brightness(img).enhance(float(tone.get("brightness", 1)))


_FONT_DIR = os.path.join("brand_assets", "fonts")
JAR_HEIGHT_FRAC = 0.67          # jar fills ~65-70% of card height
MAX_UPSCALE = 2.0
MIN_LABEL_SHARPNESS_RATIO = float(os.getenv("APPROVED_LABEL_SHARPNESS_RATIO", "0.55"))

# Verified-fact copy (shopify_catalog / product truth). No anti-chicory wording.
SKU_COPY = {
    "bold": ("Strong, full-bodied, honest.",
             "Pure coffee instant, in a lead-free glass jar"),
    "purica": ("Smooth Arabica, ready in seconds.",
               "Freeze-dried pure Arabica instant coffee"),
    "purista": ("Deep Robusta, gently freeze-dried.",
                "Freeze-dried pure Robusta instant coffee"),
    "ultra_blend": ("The filter-coffee comfort you grew up with.",
                    "70% coffee, 30% chicory instant blend"),
}


def _vfont(name: str, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
    except Exception:
        return _font("headline" if "Serif" in name else "body", size)


def _strip_shop(text: str) -> str:
    """Footer already says 'Shop p3online.in' — never repeat it in the subline."""
    import re
    t = re.sub(r"(?i)\s*(shop|order|buy)?\s*(now\s*)?(on|at)?\s*p3online\.in\s*", " ", str(text or ""))
    t = re.sub(r"(?i)follow\s*@?purepantryprovisions", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip(" .,-•|")


def render_card_as_is(it: dict, width: int, height: int, label: str = "card") -> str | None:
    """Founder-approved finished card: resize only (pad with its own bg if the
    aspect differs) — no overlay, no crop."""
    from PIL import Image
    src = Image.open(os.path.join(_DIR, it["file"])).convert("RGB")
    w, h = src.size
    s = min(width / w, height / h)
    nw, nh = round(w * s), round(h * s)
    img = Image.new("RGB", (width, height), src.getpixel((3, 3)))
    ox, oy = (width - nw) // 2, (height - nh) // 2
    img.paste(src.resize((nw, nh), Image.LANCZOS), (ox, oy))
    b = it["jar_bbox"]
    jar = (ox + b[0] * nw, oy + b[1] * nh, ox + b[2] * nw, oy + b[3] * nh)
    return _save(img.convert("RGBA"), jar, label, os.path.join(_DIR, it["file"]))


def render_studio_card(it: dict, width: int, height: int, headline: str = "", body: str = "",
                       label: str = "studio", day: int = 0) -> str | None:
    """Studio cutout on a clean plain paper / brand-tint card with a subtle
    natural floor shadow. Jar fills ~67% of card height so the label reads at
    phone size. No scenes, no props. White sweep removed by multiply blend."""
    from PIL import Image, ImageDraw, ImageFilter, ImageChops
    src = _apply_tone(Image.open(os.path.join(_DIR, it["file"])).convert("RGB"), it.get("tone"))
    card = _CARDS["paper"] if day % 2 == 0 else _CARDS.get(it.get("sku"), _CARDS["paper"])
    img = Image.new("RGB", (width, height), card)
    sku = it.get("sku")
    d_head, d_sub = SKU_COPY.get(sku, ("", ""))
    headline = _clean(headline) or d_head
    sub = _strip_shop(_clean(body)) or (d_sub if headline != d_head or True else "")
    if sub.lower() == headline.lower():
        sub = d_sub
    w, h = src.size
    x0, y0, x1, y1 = it["jar_bbox"]
    pp = int(max(x1 - x0, y1 - y0) * max(w, h) * 0.06)   # white margin for feathering
    c = (int(x0 * w) - pp, int(y0 * h) - pp, int(x1 * w) + pp, int(y1 * h) + pp)
    jarimg = Image.new("RGB", (c[2] - c[0], c[3] - c[1]), (255, 255, 255))
    sc = (max(0, c[0]), max(0, c[1]), min(w, c[2]), min(h, c[3]))
    jarimg.paste(src.crop(sc), (sc[0] - c[0], sc[1] - c[1]))
    foot_h = int(height * 0.055)
    jh, jw0 = (y1 - y0) * h, (x1 - x0) * w
    s = min(height * JAR_HEIGHT_FRAC / jh, width * 0.80 / jw0, MAX_UPSCALE)
    jarimg = jarimg.resize((round(jarimg.size[0] * s), round(jarimg.size[1] * s)), Image.LANCZOS)
    if s > 1.05:  # mild unsharp after upscale to keep label edges crisp
        jarimg = jarimg.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    # feather the crop edge to pure white so no rectangle of studio sweep shows
    fw = max(8, int(min(jarimg.size) * 0.06))
    fm = Image.new("L", jarimg.size, 0)
    ImageDraw.Draw(fm).rectangle((fw, fw, jarimg.size[0] - fw, jarimg.size[1] - 1), fill=255)
    fm = fm.filter(ImageFilter.GaussianBlur(fw / 2))
    jarimg = Image.composite(jarimg, Image.new("RGB", jarimg.size, (255, 255, 255)), fm)
    ox = (width - jarimg.size[0]) // 2
    oy = height - foot_h - int(height * 0.035) - int((y1 * h - c[1]) * s)
    jar = (ox + (x0 * w - c[0]) * s, oy + (y0 * h - c[1]) * s,
           ox + (x1 * w - c[0]) * s, oy + (y1 * h - c[1]) * s)
    jw = jar[2] - jar[0]
    sh = Image.new("L", (width, height), 0)
    ImageDraw.Draw(sh).ellipse((jar[0] + jw * 0.06, jar[3] - jw * 0.05,
                                jar[2] - jw * 0.06, jar[3] + jw * 0.06), fill=80)
    sh = sh.filter(ImageFilter.GaussianBlur(max(6, int(jw * 0.06))))
    img = Image.composite(Image.new("RGB", img.size, tuple(int(v * 0.74) for v in card)), img, sh)
    region = img.crop((ox, oy, ox + jarimg.size[0], oy + jarimg.size[1]))
    img.paste(ImageChops.multiply(region, jarimg), (ox, oy))
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)
    m = int(width * 0.08)
    text_bottom = jar[1] - height * 0.02
    hsz = max(34, int(width / 12.5))
    hf = _vfont("IBMPlexSerif-Bold.ttf", hsz)
    lines = _wrap(d, headline, hf, width - 2 * m, 2)
    bsz = max(20, width // 36)
    bf = _vfont("IBMPlexSerif-Italic.ttf", bsz)
    # shrink headline until the text block fits above the jar
    while hsz > 28:
        block = len(lines) * hsz * 1.12 + (bsz * 1.9 if sub else 0)
        if height * 0.045 + block <= text_bottom:
            break
        hsz -= 2
        hf = _vfont("IBMPlexSerif-Bold.ttf", hsz)
        lines = _wrap(d, headline, hf, width - 2 * m, 2)
    block = len(lines) * hsz * 1.12 + (bsz * 1.9 if sub else 0)
    y = max(height * 0.045, (text_bottom - block) * 0.55)
    for ln in lines:
        d.text(((width - d.textlength(ln, font=hf)) / 2, y), ln, font=hf, fill=_ESPRESSO)
        y += hsz * 1.12
    if sub:
        sl = _wrap(d, sub, bf, width - 2 * m, 1)
        if sl:
            d.text(((width - d.textlength(sl[0], font=bf)) / 2, y + bsz * 0.45), sl[0], font=bf, fill=(139, 94, 60))
    ff = _vfont("IBMPlexSans-Regular.ttf", max(17, width // 52))
    d.text(((width - d.textlength(CTA, font=ff)) / 2, height - foot_h / 2 - getattr(ff, "size", 18) * 0.6),
           CTA, font=ff, fill=(140, 120, 95))
    # label sharpness QA: output label vs source label (same region)
    lab = lambda b: (b[0] + (b[2] - b[0]) * 0.15, b[1] + (b[3] - b[1]) * 0.45,
                     b[2] - (b[2] - b[0]) * 0.15, b[1] + (b[3] - b[1]) * 0.80)
    src_lab = src.crop(tuple(int(v) for v in lab((x0 * w, y0 * h, x1 * w, y1 * h))))
    out_lab = img.convert("RGB").crop(tuple(int(v) for v in lab(jar)))
    tsz = min(src_lab.size, out_lab.size, key=lambda z: z[0] * z[1])  # compare at the lower res
    ratio = (sharpness(out_lab.resize(tsz, Image.LANCZOS))
             / max(1e-6, sharpness(src_lab.resize(tsz, Image.LANCZOS))))
    if ratio < MIN_LABEL_SHARPNESS_RATIO:
        logger.warning("[approved_photos] label sharpness dropped (%.2f) %s", ratio, label)
        return None
    if (jar[3] - jar[1]) < 0.60 * height and s < MAX_UPSCALE and (jar[2] - jar[0]) < 0.79 * width:
        logger.warning("[approved_photos] jar too small on card %s", label)
        return None
    return _save(img, jar, label, os.path.join(_DIR, it["file"]))


def qa_layout(size, texts, band) -> list[str]:
    """Baked-in text fully in frame; overlay band slim and never touching it."""
    W, H = size
    errs = []
    for t in texts or []:
        if t[0] < -1 or t[1] < -1 or t[2] > W + 1 or t[3] > H + 1:
            errs.append("baked_text_cut_off")
    if band:
        if band[3] - band[1] > MAX_BAND_FRAC * H:
            errs.append("overlay_band_too_tall")
        if any(_overlaps(band, t) for t in texts or []):
            errs.append("overlay_touches_baked_text")
    return errs


def _save(img, jar, label, src=None, texts=None, band=None):
    rgb = img.convert("RGB")
    errs = qa_jar(rgb, jar) + qa_layout(rgb.size, texts, band)
    if errs:
        logger.warning("[approved_photos] QA fail-closed %s: %s", label, errs)
        return None
    os.makedirs(_OUT_DIR, exist_ok=True)
    path = os.path.join(_OUT_DIR, f"{label}.jpg")
    rgb.save(path, "JPEG", quality=92)
    if src:
        try:
            from content_generator.creative.jar_provenance import record_jar_provenance
            record_jar_provenance(path, jar_asset_id=src, render_source="approved_photo")
        except Exception as e:
            logger.debug("[approved_photos] provenance record failed: %s", e)
    return path


def render(surface: str, width: int, height: int, headline: str = "", body: str = "",
           day: int = 0, idx: int = 0, product=None, label: str = "approved",
           prefer: str = "photo") -> str | None:
    """Main entry. Real photos in <sku>/real/ win; otherwise studio cutout
    card. AI lifestyle/infographic renders are blocked in the manifest."""
    if not enabled():
        return None
    try:
        if not product:
            product = _norm_sku(f"{headline} {body}")
        sku = _norm_sku(product)
        if sku and height > width * 1.6 and surface in ("ig_story", "reel_thumb"):
            cards = [c for c in items(surface, sku, ("approved_card",)) if c.get("use_as_is")]
            if cards:
                p = render_card_as_is(cards[(day + idx) % len(cards)], width, height, label)
                if p:
                    return p
        if prefer != "studio":
            reals = [r for r in real_photos(sku) if surface in r.get("allowed_surfaces", [])]
            if reals:
                p = render_photo(reals[(day * 3 + idx) % len(reals)], width, height, headline, body, label)
                if p:
                    return p
        cut = [i for i in items(surface, sku, ("cutout",))] or items("studio_card", sku, ("cutout",))
        if any(i.get("primary") for i in cut):
            cut = [i for i in cut if i.get("primary")]
        if not cut:
            return None
        return render_studio_card(cut[(day * 3 + idx) % len(cut)], width, height, headline, body, label, day)
    except Exception as e:  # never break the pipeline; caller falls back
        logger.warning("[approved_photos] render failed (%s): %s", label, e)
        return None
