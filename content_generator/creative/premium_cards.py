"""Premium D2C card system: per-SKU palettes, layered depth, rotating layouts.

Hard rules kept: official studio cutouts only (true colours, sharp, fully in
frame, nothing overlapping the jar), no AI composites, no "100%", prices only
from Shopify (price_truth), every drawn string goes through render_claims.
"""
from __future__ import annotations

import logging
import math
import os
import re
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from content_generator.creative import render_claims as rc

logger = logging.getLogger(__name__)

HANDLE = "@purepantryprovisions"
SHOP = "p3online.in"
_DIR = os.path.join("brand_assets", "approved_photos")
_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

CUTOUTS = {
    "bold": "bold/bold_100g_cutout_wide_hires.png",
    "purica": "purica/purica_100g_cutout_front.png",
    "purista": "purista/purista_100g_cutout_front.png",
    "ultra_blend": "ultra_blend/ultra_blend_100g_cutout_front.png",
}

# Drawn from each jar's label: deep, mid, glow, accent, ink.
PALETTES = {
    "bold": [
        {"deep": (24, 10, 40), "mid": (74, 30, 110), "glow": (150, 92, 210), "accent": (232, 196, 120), "ink": (250, 244, 255)},
        {"deep": (12, 8, 24), "mid": (52, 26, 84), "glow": (220, 150, 245), "accent": (255, 214, 140), "ink": (255, 255, 255)},
    ],
    "purica": [
        {"deep": (8, 30, 22), "mid": (24, 84, 58), "glow": (120, 190, 140), "accent": (236, 210, 140), "ink": (244, 252, 246)},
        {"deep": (14, 24, 16), "mid": (48, 92, 52), "glow": (180, 214, 150), "accent": (250, 226, 160), "ink": (255, 255, 250)},
    ],
    "purista": [
        {"deep": (42, 16, 10), "mid": (120, 52, 28), "glow": (230, 150, 96), "accent": (255, 220, 160), "ink": (255, 248, 240)},
        {"deep": (30, 14, 12), "mid": (96, 36, 30), "glow": (214, 110, 80), "accent": (250, 206, 150), "ink": (255, 246, 238)},
    ],
    "ultra_blend": [
        {"deep": (48, 26, 4), "mid": (170, 100, 14), "glow": (255, 200, 70), "accent": (255, 236, 170), "ink": (255, 252, 240)},
        {"deep": (36, 18, 6), "mid": (140, 72, 10), "glow": (250, 170, 40), "accent": (255, 228, 150), "ink": (255, 250, 236)},
    ],
    # Gift-pack stills use the same card grades. They are not in CUTOUTS, so the
    # daily jar cards keep using the four studio cutouts.
    "gourmet_duo_mini": [
        {"deep": (28, 16, 12), "mid": (96, 42, 32), "glow": (214, 140, 96), "accent": (236, 206, 150), "ink": (255, 248, 240)},
        {"deep": (12, 28, 22), "mid": (36, 88, 58), "glow": (140, 190, 140), "accent": (236, 214, 160), "ink": (244, 252, 246)},
    ],
}

LAYOUTS = ("hero_center", "split_left", "editorial_top", "diagonal_band")
DISPLAY_NAME = {"bold": "Bold", "purica": "Purica", "purista": "Purista", "ultra_blend": "Ultra Blend"}


def _font(kind: str, size: int):
    cands = {
        "display": ["brand_assets/fonts/IBMPlexSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
        "italic": ["brand_assets/fonts/IBMPlexSerif-Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
        "sans": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    }[kind]
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


# ── background layers ─────────────────────────────────────────────────────
def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background(w, h, pal, seed=0, light=(0.5, 0.35)):
    """Tonal radial gradient + grain + vignette + a surface plane."""
    import numpy as np
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    lx, ly = light[0] * w, light[1] * h
    d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / math.hypot(w, h)
    t = np.clip(d * 1.7, 0, 1)[..., None]
    deep, mid, glow = (np.array(pal[k], np.float32) for k in ("deep", "mid", "glow"))
    inner = glow * (1 - np.clip(t * 2.2, 0, 1)) + mid * np.clip(t * 2.2, 0, 1)
    img = np.where(t < 0.45, inner, mid * (1 - (t - 0.45) / 0.55) + deep * ((t - 0.45) / 0.55))
    # diagonal tonal sweep
    sweep = ((xx / w) * 0.6 + (yy / h) * 0.4)[..., None]
    img = img * (1.08 - 0.25 * sweep)
    # surface plane (table) in lower 30%
    horizon = int(h * 0.70)
    plane = np.clip((yy - horizon) / max(1, h - horizon), 0, 1)[..., None]
    img = img * (1 - 0.45 * plane) + deep * 0.45 * plane
    edge = np.exp(-((yy - horizon) ** 2) / (2 * (h * 0.004) ** 2))[..., None]
    img = img + np.array(pal["accent"], np.float32) * 0.22 * edge
    # grain
    rng = np.random.default_rng(seed)
    img = img + rng.normal(0, 7.0, (h, w, 1)).astype(np.float32)
    # vignette
    v = 1 - 0.55 * np.clip(np.sqrt(((xx - w / 2) / (w / 1.3)) ** 2 + ((yy - h / 2) / (h / 1.3)) ** 2), 0, 1) ** 2.2
    img = np.clip(img * v[..., None], 0, 255).astype("uint8")
    return Image.fromarray(img).convert("RGBA"), horizon


def official_jar_asset(sku: str) -> str:
    """Real studio cutout for this SKU.

    Prefers a verified ``jar_asset_id`` in jar_provenance.json when that file
    sits in the trusted brand-assets tree and is a cutout for this SKU.
    Stock footage and AI jars are never returned.
    """
    canonical = os.path.join(_DIR, CUTOUTS[sku])
    try:
        from content_generator.creative import jar_provenance as jp
        registry = jp._load_registry()
    except Exception:
        return canonical
    want = os.path.basename(CUTOUTS[sku]).lower()
    sku_token = sku.lower().replace("-", "_")
    fallback = None
    seen = set()
    for entry in registry.values():
        if not isinstance(entry, dict) or not entry.get("asset_real_jar_verified"):
            continue
        marker = id(entry)
        if marker in seen:
            continue
        seen.add(marker)
        jar = str(entry.get("jar_asset_id") or "")
        if not jar:
            continue
        try:
            trusted = jp._trusted_jar_asset(jar)
        except Exception:
            trusted = False
        if not trusted or not os.path.isfile(jar):
            continue
        base = os.path.basename(jar).lower()
        if "cutout" not in base:
            continue
        if base == want:
            return jar
        if sku_token in base and fallback is None:
            fallback = jar
    return fallback or canonical


def load_jar(sku: str, target_h: int, source: str | None = None):
    from content_generator.creative.real_jar_composer import knockout_white
    src = Image.open(source or os.path.join(_DIR, CUTOUTS[sku]))
    jar = knockout_white(src)
    s = target_h / jar.height
    s = min(s, 2.0)  # never upscale past 2x (sharpness)
    return jar.resize((int(jar.width * s), int(jar.height * s)), Image.LANCZOS)


def place_jar(canvas, jar, cx, base_y, pal, floor_y=None):
    """Soft contact shadow + faded reflection on the surface plane.

    ``floor_y`` is a line the reflection must not cross (the CTA pill).
    """
    W, H = canvas.size
    x0, y0 = int(cx - jar.width / 2), int(base_y - jar.height)
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((x0 - jar.width * 0.08, base_y - jar.height * 0.035,
                                x0 + jar.width * 1.08, base_y + jar.height * 0.05), fill=(0, 0, 0, 170))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(6, jar.width // 14))))
    refl = jar.transpose(Image.FLIP_TOP_BOTTOM)
    rh = int(jar.height * 0.32)
    if floor_y is not None:
        rh = min(rh, max(0, int(floor_y) - int(base_y) - 2))
    if rh < 8:
        canvas.alpha_composite(jar, (x0, y0))
        return (x0, y0, x0 + jar.width, base_y)
    refl = refl.crop((0, 0, jar.width, rh))
    grad = Image.linear_gradient("L").resize((jar.width, rh)).point(lambda p: int((255 - p) * 0.28))
    a = Image.fromarray(__import__("numpy").minimum(__import__("numpy").array(refl.getchannel("A")),
                                                   __import__("numpy").array(grad)))
    refl.putalpha(a)
    canvas.alpha_composite(refl.filter(ImageFilter.GaussianBlur(1.5)), (x0, base_y + 2))
    canvas.alpha_composite(jar, (x0, y0))
    return (x0, y0, x0 + jar.width, base_y)


# ── typography ────────────────────────────────────────────────────────────
def _wrap(d, text, font, max_w, max_lines):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def fit_headline(d, text, max_w, max_h, kind="display", start=150, min_size=54, max_lines=3):
    size = start
    while size >= min_size:
        f = _font(kind, size)
        lines = _wrap(d, text, f, max_w, 99)
        if (len(lines) <= max_lines and len(lines) * size * 1.05 <= max_h
                and all(d.textlength(ln, font=f) <= max_w for ln in lines)):
            return f, lines
        size -= 6
    f = _font(kind, min_size)
    return f, _wrap(d, text, f, max_w, max_lines)


def _text(canvas, xy, s, font, fill, shadow=True, anchor="la"):
    if shadow:
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((xy[0] + 3, xy[1] + 5), s, font=font, fill=(0, 0, 0, 190), anchor=anchor)
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    ImageDraw.Draw(canvas).text(xy, s, font=font, fill=fill, anchor=anchor)


def cta_pill_box(W: int, H: int, cta: str | None):
    """Bottom-margin CTA pill. A 12% lift on 9:16 frames ran the pill through the jar."""
    if not cta:
        return None
    cf = _font("sans", max(30, int(W) // 26))
    tw = ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(cta, font=cf)
    m = int(W * 0.055)
    bw, bh = tw + W * 0.09, cf.size * 2.1
    y0 = H - m - bh - H * 0.02
    x0 = (W - bw) / 2
    return (x0, y0, x0 + bw, y0 + bh)


def brand_frame(canvas, pal, cta: str | None = None):
    """Logo wordmark + handle on every frame; strong CTA pill on final frames."""
    W, H = canvas.size
    d = ImageDraw.Draw(canvas)
    m = int(W * 0.055)
    f = _font("sans", max(22, W // 40))
    d.rounded_rectangle((m, m, m + W * 0.06, m + W * 0.06), radius=int(W * 0.015), outline=pal["accent"], width=3)
    d.text((m + W * 0.03, m + W * 0.03), "PB", font=_font("display", int(W * 0.03)), fill=pal["accent"], anchor="mm")
    d.text((m + W * 0.08, m + W * 0.012), "PURITY BEANS", font=f, fill=pal["ink"])
    d.text((m + W * 0.08, m + W * 0.012 + f.size * 1.2), HANDLE, font=_font("sans", max(18, W // 54)), fill=pal["accent"])
    if cta:
        x0, y0, x1, y1 = cta_pill_box(W, H, cta)
        bw, bh = x1 - x0, y1 - y0
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((x0 - 8, y0 - 8, x1 + 8, y1 + 8), radius=int(bh / 2) + 8,
                                               fill=pal["accent"] + (120,))
        canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((x0, y0, x1, y1), radius=int(bh / 2), fill=pal["accent"])
        d.text((W / 2, y0 + bh / 2), cta, font=_font("sans", max(30, W // 26)), fill=pal["deep"], anchor="mm")


def strip_chip(canvas, xy, pal, sku, anchor="la"):
    d = ImageDraw.Draw(canvas)
    t = rc.guard(rc.strip_for(sku).upper(), rc.sku_class(sku))
    f = _font("sans", max(20, canvas.size[0] // 46))
    tw = d.textlength(t, font=f)
    x, y = xy
    if anchor == "ma":
        x -= (tw + 40) / 2
    d.rounded_rectangle((x, y, x + tw + 40, y + f.size * 2), radius=f.size, outline=pal["accent"], width=2,
                        fill=pal["deep"] + (180,))
    d.text((x + 20, y + f.size), t, font=f, fill=pal["accent"], anchor="lm")
    return (x, y, x + tw + 40, y + f.size * 2)


def _price_line(sku):
    try:
        from content_generator.core import price_truth as pt
        if sku == "ultra_blend":
            return f"Rs {int(pt.variant_price(sku, 100))} \u2022 {pt.ultra('cups')}+ cups a jar"
        p = pt.variant_price(sku, 100)
        return f"100g \u2022 Rs {int(p)}" if p else ""
    except Exception:
        return ""


# ── layouts ───────────────────────────────────────────────────────────────
def render(sku: str, headline: str, sub: str = "", *, width=1080, height=1350, layout=None,
           palette_idx=0, cta: str | None = None, seed=0, out_path=None, show_price=True) -> dict:
    """Render one card. Returns {path, layout, palette, jar_box, text_boxes, headline_px, body_px}."""
    tok = rc.set_sku(sku)
    try:
        pal = PALETTES[sku][palette_idx % len(PALETTES[sku])]
        layout = layout or LAYOUTS[seed % len(LAYOUTS)]
        W, H = width, height
        light = {"hero_center": (0.5, 0.42), "split_left": (0.42, 0.38),
                 "editorial_top": (0.5, 0.6), "diagonal_band": (0.3, 0.55)}[layout]
        canvas, horizon = background(W, H, pal, seed=seed, light=light)
        headline = rc.guard(str(headline or ""))
        sub = rc.guard(str(sub or ""))
        d = ImageDraw.Draw(canvas)
        m = int(W * 0.07)
        top = int(H * 0.15)
        cta_h = int(H * 0.11) if cta else int(H * 0.05)
        pill = cta_pill_box(W, H, cta) if cta else None
        # Keep the jar and its reflection above the pill, including the glow.
        refl_floor = (pill[1] - 12) if pill else None
        texts = []
        if layout == "split_left":
            jar = load_jar(sku, int(H * 0.56))
            base_y = int(H * 0.80)
            if refl_floor is not None:
                base_y = min(base_y, int(refl_floor))
            jb = place_jar(canvas, jar, int(W * 0.70), base_y, pal, floor_y=refl_floor)
            col_w = jb[0] - m - int(W * 0.03)
            f, lines = fit_headline(d, headline.upper(), col_w, H * 0.40, start=120)
            y = top + H * 0.04
            x_text = m
        elif layout == "editorial_top":
            f, lines = fit_headline(d, headline.upper(), W - 2 * m, H * 0.26, start=130)
            y = top
            x_text = m
            jar = load_jar(sku, int(H * 0.42))
            jb = None
        elif layout == "diagonal_band":
            band = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(band).polygon([(0, H * 0.10), (W, H * 0.02), (W, H * 0.40), (0, H * 0.50)],
                                         fill=pal["deep"] + (200,))
            canvas.alpha_composite(band)
            f, lines = fit_headline(d, headline.upper(), W - 2 * m, H * 0.24, start=120)
            y = H * 0.16
            x_text = m
            jar = load_jar(sku, int(H * 0.44))
            jb = None
        else:  # hero_center
            f, lines = fit_headline(d, headline.upper(), W - 2 * m, H * 0.24, start=128)
            y = top
            x_text = None
            jar = load_jar(sku, int(H * 0.46))
            jb = None
        lh = int(f.size * 1.02)
        for ln in lines:
            if x_text is None:
                _text(canvas, (W / 2, y), ln, f, pal["ink"], anchor="ma")
                tw = ImageDraw.Draw(canvas).textlength(ln, font=f)
                texts.append((W / 2 - tw / 2, y, W / 2 + tw / 2, y + lh))
            else:
                _text(canvas, (x_text, y), ln, f, pal["ink"])
                tw = ImageDraw.Draw(canvas).textlength(ln, font=f)
                texts.append((x_text, y, x_text + tw, y + lh))
            y += lh
        # accent rule + sub
        y += int(H * 0.035)
        bf = _font("italic", max(30, W // 26))
        ax = W / 2 if x_text is None else x_text
        ImageDraw.Draw(canvas).line((ax - (60 if x_text is None else 0), y, ax + (60 if x_text is None else 120), y),
                                    fill=pal["accent"], width=5)
        y += int(H * 0.02)
        # The strip chip already states the SKU line (e.g. "Coffee + chicory blend"); a sub that just
        # repeats it reads as redundant copy and fails the vision gate every time.
        _norm = lambda t: re.sub(r"[^a-z0-9]+", " ", str(t).lower()).strip()
        if sub and _norm(rc.strip_for(sku)) and _norm(rc.strip_for(sku)) in _norm(sub) \
                and len(_norm(sub)) <= len(_norm(rc.strip_for(sku))) + 12:
            sub = ""
        if sub:
            maxw = (W - 2 * m) if layout != "split_left" else col_w
            for ln in _wrap(ImageDraw.Draw(canvas), sub, bf, maxw, 2):
                _text(canvas, (ax, y), ln, bf, pal["accent"], anchor="ma" if x_text is None else "la")
                y += int(bf.size * 1.25)
        y += int(H * 0.01)
        chip = strip_chip(canvas, (ax, y), pal, sku, anchor="ma" if x_text is None else "la")
        texts.append(chip)
        y = chip[3]
        if jb is None:
            base = H - cta_h - int(H * 0.06)
            if refl_floor is not None:
                base = min(base, refl_floor)
            avail = base - (y + H * 0.03)
            if jar.height > avail > 40:
                s = avail / jar.height
                jar = jar.resize((int(jar.width * s), int(jar.height * s)), Image.LANCZOS)
            cx = W * (0.5 if layout != "diagonal_band" else 0.62)
            jb = place_jar(canvas, jar, int(cx), int(base), pal, floor_y=refl_floor)
        price = _price_line(sku) if show_price else ""
        if price:
            pf = _font("sans", max(22, W // 44))
            px = m if layout != "split_left" else m
            py = jb[3] - pf.size * 1.5
            if layout in ("split_left",) or jb[0] > m + 340:
                _text(canvas, (px, py), rc.guard(price), pf, pal["ink"], shadow=True)
        brand_frame(canvas, pal, cta=cta)
        if pill:
            texts.append(tuple(pill))
        out_path = out_path or os.path.join(_OUT, f"premium_{sku}_{layout}_{seed}.jpg")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        canvas.convert("RGB").save(out_path, quality=93)
        return {"path": out_path, "layout": layout, "palette": palette_idx, "jar_box": jb,
                "text_boxes": texts, "headline_px": f.size, "body_px": bf.size, "sku": sku}
    finally:
        rc.reset_sku(tok)


def render_until_pass(sku, headline, sub="", *, width=1080, height=1350, cta=None, seed=0,
                      recent_layouts=(), max_tries=8, gate=None, out_path=None) -> dict:
    """Render, run the visual gate, re-render with a different template/palette on failure."""
    from content_generator.creative import visual_gate
    gate = gate or visual_gate.evaluate
    order = [l for l in LAYOUTS if l not in list(recent_layouts)[-2:]] + [l for l in LAYOUTS if l in list(recent_layouts)[-2:]]
    last = None
    for i in range(max_tries):
        layout = order[(seed + i) % len(order)]
        meta = render(sku, headline, sub, width=width, height=height, layout=layout, palette_idx=seed + i + i // len(order),  # decorrelate palette from layout so retries cover every combo
                     
                      cta=cta, seed=seed + i, out_path=out_path)
        verdict = gate(meta, recent_layouts=recent_layouts)
        meta["visual_gate"] = verdict
        if verdict.get("passed"):
            return meta
        logger.warning("[visual-gate] %s try %d failed: %s — re-rendering", sku, i + 1, verdict.get("reasons"))
        last = meta
        if visual_gate.is_vision_hold(verdict):
            logger.error("[visual-gate] %s: no vision scorer available — holding now instead of re-rendering", sku)
            break
    last = last or {}
    last["held"] = True
    return last


def render_story_video(sku: str, headline: str, sub: str, out_path: str, *, seconds: float = 10.0,
                       seed: int = 0, audio: str | None = None, layout: str = "hero_center") -> dict:
    """9:16 story: slow push-in on the hero frame, then the follow CTA frame, with music."""
    import glob
    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    base = out_path.rsplit(".", 1)[0]
    a = render(sku, headline, sub, width=1080, height=1920, layout=layout, seed=seed,
               out_path=base + "_a.jpg")
    b = render(sku, headline, sub, width=1080, height=1920, layout=layout, seed=seed,
               cta=f"FOLLOW {HANDLE.upper()}", out_path=base + "_b.jpg")
    if audio is None:
        tracks = sorted(glob.glob("music_library/**/*.mp3", recursive=True) + glob.glob("music_library/**/*.wav", recursive=True))
        audio = tracks[seed % len(tracks)] if tracks else None
    fps, t1 = 30, seconds * 0.6
    zoom = "zoompan=z='min(zoom+0.0009,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s=1080x1920:fps=30"
    cmd = [ff, "-nostdin", "-y", "-loop", "1", "-t", str(t1 + 0.6), "-i", a["path"], "-loop", "1", "-t", str(seconds - t1 + 0.6),
           "-i", b["path"]]
    if audio:
        cmd += ["-i", audio]
    filt = (f"[0:v]scale=2160:-1,{zoom.format(d=int((t1 + 0.6) * fps))},format=yuv420p[v0];"
            f"[1:v]scale=2160:-1,{zoom.format(d=int((seconds - t1 + 0.6) * fps))},format=yuv420p[v1];"
            f"[v0][v1]xfade=transition=fade:duration=0.6:offset={t1}[v]")
    cmd += ["-filter_complex", filt, "-map", "[v]"]
    if audio:
        cmd += ["-map", "2:a", "-af", f"afade=t=in:d=0.5,afade=t=out:st={seconds - 1}:d=1", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=90, stdin=subprocess.DEVNULL)
    return {"path": out_path, "frames": [a, b], "audio": audio, "jar_box": b["jar_box"], "layout": layout,
            "text_boxes": b["text_boxes"], "headline_px": b["headline_px"], "body_px": b["body_px"]}
