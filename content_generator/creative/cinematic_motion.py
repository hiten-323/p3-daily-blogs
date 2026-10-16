"""Cinematic procedural motion backgrounds for vertical video (Reels, Stories, Shorts).

Everything is drawn in code (numpy + PIL), frame by frame. No AI composites,
no stock footage. Layers, back to front:

  1. per-SKU tonal gradient with a slowly drifting key light (light sweep)
  2. crema-swirl texture loop on the surface plane (perspective-squashed spiral)
  3. far bokeh (warm, soft) - slow parallax
  4. drifting steam wisps (advected smooth noise) rising behind the jar
  5. swirling/falling coffee granules + amber particles - fast parallax
  6. slow camera push-in on layers 1-5 (different rates = parallax depth)
  7. grain + vignette
  8. official studio jar cutout (true colours, never scaled per frame, so it
     stays sharp) with contact shadow + reflection; a faint specular glint
     sweeps across the glass twice. Nothing is ever drawn on top of the jar
     except that glint; text and particles never overlap it.
  9. kinetic word-by-word headline, sub line, claim-safe strip chip,
     brand frame, and the follow CTA for @purepantryprovisions at the end.

Palette per SKU comes from premium_cards.PALETTES (sampled from jar labels).
Every drawn string goes through render_claims.guard. The output meta is the
same shape premium_cards returns, so visual_gate.evaluate_video gates it.
"""
from __future__ import annotations

import glob
import logging
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from content_generator.creative import premium_cards as pc
from content_generator.creative import render_claims as rc

logger = logging.getLogger(__name__)

W, H = 1080, 1920
BW, BH = 540, 960  # background render resolution (upscaled; bg is soft by design)
FPS = 30
LAYOUTS = ("cinematic_hero", "cinematic_low", "cinematic_offset")


def _smooth_noise(h, w, scale, rng):
    """Tileable smooth noise via low-res random + bicubic upscale."""
    small = rng.random((max(2, h // scale), max(2, w // scale))).astype(np.float32)
    img = Image.fromarray((small * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    return np.asarray(img, np.float32) / 255.0


class _Backdrop:
    def __init__(self, pal, seed, light_path, horizon_frac):
        self.pal = {k: np.array(v, np.float32) for k, v in pal.items()}
        self.rng = np.random.default_rng(seed)
        self.light_path = light_path
        self.horizon = horizon_frac
        yy, xx = np.mgrid[0:BH, 0:BW].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.steam = [_smooth_noise(BH * 2, BW, s, self.rng) for s in (60, 28)]
        self.grain = [self.rng.normal(0, 6.0, (BH, BW, 1)).astype(np.float32) for _ in range(4)]
        n = 26
        self.bokeh = [dict(x=self.rng.uniform(0, BW), y=self.rng.uniform(0, BH * 0.72),
                           r=self.rng.uniform(10, 42), a=self.rng.uniform(0.10, 0.32),
                           vx=self.rng.uniform(-4, 4), vy=self.rng.uniform(-7, -1),
                           depth=self.rng.uniform(0.3, 1.0), ph=self.rng.uniform(0, 6.28))
                      for _ in range(n)]
        m = 170
        self.parts = dict(x=self.rng.uniform(0, BW, m), y=self.rng.uniform(-BH, BH, m),
                          s=self.rng.uniform(0.6, 2.4, m), v=self.rng.uniform(18, 60, m),
                          sw=self.rng.uniform(4, 22, m), ph=self.rng.uniform(0, 6.28, m),
                          amber=self.rng.random(m) < 0.35, depth=self.rng.uniform(0.4, 1.4, m))
        v = 1 - 0.6 * np.clip(np.sqrt(((xx - BW / 2) / (BW / 1.25)) ** 2 + ((yy - BH / 2) / (BH / 1.25)) ** 2), 0, 1) ** 2.0
        self.vig = v[..., None]

    def _zoom(self, xx, yy, z):
        cx, cy = BW / 2, BH * 0.55
        return cx + (xx - cx) / z, cy + (yy - cy) / z

    def frame(self, t, dur):
        p = self.pal
        u = t / dur
        # 6. push-in: far layer slow, mid medium, near fast
        zf, zm, zn = 1 + 0.05 * u, 1 + 0.09 * u, 1 + 0.16 * u
        xx, yy = self._zoom(self.xx, self.yy, zf)
        # 1. gradient with drifting key light
        lx0, ly0, lx1, ly1 = self.light_path
        lx = (lx0 + (lx1 - lx0) * (0.5 - 0.5 * math.cos(math.pi * u))) * BW
        ly = (ly0 + (ly1 - ly0) * u) * BH
        d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / math.hypot(BW, BH)
        tt = np.clip(d * 1.8, 0, 1)[..., None]
        k = np.clip(tt * 2.2, 0, 1)
        inner = p["glow"] * (1 - k) + p["mid"] * k
        img = np.where(tt < 0.45, inner, p["mid"] * (1 - (tt - 0.45) / 0.55) + p["deep"] * ((tt - 0.45) / 0.55))
        # slow diagonal light sweep through the room
        band = np.exp(-(((xx / BW) * 0.8 + (yy / BH) * 0.5 - (-0.3 + 1.6 * u)) ** 2) / 0.012)[..., None]
        img = img + p["accent"] * 0.10 * band
        # 2. surface plane + crema swirl loop
        hz = self.horizon * BH
        plane = np.clip((yy - hz) / max(1, BH - hz), 0, 1)[..., None]
        img = img * (1 - 0.5 * plane) + p["deep"] * 0.5 * plane
        sx, sy = (xx - BW / 2) / BW, (yy - (hz + (BH - hz) * 0.55)) / BH * 3.2
        r = np.sqrt(sx ** 2 + sy ** 2)
        th = np.arctan2(sy, sx)
        swirl = 0.5 + 0.5 * np.sin(28 * r + 3 * th - 2 * math.pi * u * 1.5)
        swirl = swirl * np.exp(-r * 2.2) * (plane[..., 0] > 0)
        crema = p["accent"] * 0.55 + p["mid"] * 0.45
        img = img + (crema - img) * (0.30 * swirl)[..., None]
        edge = np.exp(-((yy - hz) ** 2) / (2 * (BH * 0.004) ** 2))[..., None]
        img = img + p["accent"] * 0.25 * edge
        canvas = Image.fromarray(np.clip(img, 0, 255).astype("uint8")).convert("RGBA")
        # 3. far bokeh
        bok = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bok)
        for b in self.bokeh:
            z = 1 + (zm - 1) * b["depth"]
            x = BW / 2 + (b["x"] + b["vx"] * t - BW / 2) * z
            y = BH * 0.55 + (((b["y"] + b["vy"] * t) % (BH * 0.75)) - BH * 0.55) * z
            rr = b["r"] * z
            a = int(255 * b["a"] * (0.75 + 0.25 * math.sin(b["ph"] + t * 1.3)))
            col = tuple(int(c) for c in (p["accent"] * 0.7 + p["glow"] * 0.3)) + (a,)
            bd.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col)
        canvas.alpha_composite(bok.filter(ImageFilter.GaussianBlur(6)))
        # 4. steam wisps (advected noise, rising)
        off = int((t * 26) % BH)
        n1 = np.roll(self.steam[0], -off, axis=0)[:BH]
        n2 = np.roll(self.steam[1], -int(off * 1.6), axis=0)[:BH]
        wx = np.clip(1 - np.abs((self.xx - BW * 0.5 - 30 * np.sin(self.yy / 90 + t * 0.8)) / (BW * 0.42)), 0, 1)
        wy = np.clip((hz - self.yy) / (BH * 0.5), 0, 1) * np.clip(self.yy / (BH * 0.25), 0, 1)
        steam = np.clip((n1 * 0.6 + n2 * 0.4 - 0.45) * 3.0, 0, 1) * wx * wy
        sa = Image.fromarray((steam * 200).astype("uint8"))
        sl = Image.new("RGBA", (BW, BH), tuple(int(c) for c in (p["ink"] * 0.85 + p["glow"] * 0.15)) + (0,))
        sl.putalpha(sa.filter(ImageFilter.GaussianBlur(5)))
        canvas.alpha_composite(sl)
        # 5. granules + particles (near layer)
        q = self.parts
        pl = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pl)
        ys = ((q["y"] + q["v"] * t) % (BH * 2)) - BH * 0.5
        xs = q["x"] + q["sw"] * np.sin(q["ph"] + t * 1.1 + ys / 120)
        for i in range(len(xs)):
            z = 1 + (zn - 1) * q["depth"][i]
            x = BW / 2 + (xs[i] - BW / 2) * z
            y = BH * 0.55 + (ys[i] - BH * 0.55) * z
            s = q["s"][i] * z
            if q["amber"][i]:
                col = tuple(int(c) for c in p["accent"]) + (190,)
            else:
                col = (58, 34, 18, 220)
            pd.ellipse((x - s, y - s * 0.8, x + s, y + s * 0.8), fill=col)
        canvas.alpha_composite(pl)
        # 7. grain + vignette
        arr = np.asarray(canvas.convert("RGB"), np.float32)
        arr = (arr + self.grain[int(t * FPS) % 4]) * self.vig
        return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).resize((W, H), Image.BILINEAR).convert("RGBA")


def _word_layout(d, lines, font, y0, cx):
    out, y = [], y0
    lh = int(font.size * 1.04)
    for ln in lines:
        words = ln.split()
        tw = d.textlength(ln, font=font)
        x = cx - tw / 2
        for wd in words:
            out.append((wd, x, y))
            x += d.textlength(wd + " ", font=font)
        y += lh
    return out, y


def _music(seed, audio):
    if audio:
        return audio
    tracks = sorted(glob.glob("music_library/**/*.wav", recursive=True) + glob.glob("music_library/**/*.mp3", recursive=True))
    pref = [t for t in tracks if "cinematic" in t or "premium" in t] or tracks
    return pref[seed % len(pref)] if pref else None


def render_cinematic_video(sku: str, beats: list[dict] | str, out_path: str, *, sub: str = "",
                           seconds: float = 10.0, seed: int = 0, layout: str | None = None,
                           palette_idx: int | None = None, audio: str | None = None,
                           poster_path: str | None = None) -> dict:
    """Render a 1080x1920 cinematic motion video. beats: list of {on, sub} or a single headline."""
    import imageio_ffmpeg
    if isinstance(beats, str):
        beats = [{"on": beats, "sub": sub}]
    beats = [b for b in beats if (b.get("on") or "").strip()] or [{"on": "PURITY BEANS", "sub": sub}]
    tok = rc.set_sku(sku)
    try:
        pal = pc.PALETTES[sku][(seed if palette_idx is None else palette_idx) % len(pc.PALETTES[sku])]
        layout = layout or LAYOUTS[seed % len(LAYOUTS)]
        horizon = {"cinematic_hero": 0.74, "cinematic_low": 0.78, "cinematic_offset": 0.75}[layout]
        light = {"cinematic_hero": (0.25, 0.30, 0.75, 0.40), "cinematic_low": (0.75, 0.25, 0.30, 0.42),
                 "cinematic_offset": (0.40, 0.20, 0.65, 0.45)}[layout]
        bd = _Backdrop(pal, seed, light, horizon)
        m = int(W * 0.07)
        cta = f"FOLLOW {pc.HANDLE.upper()}"
        bf = pc._font("italic", max(30, W // 26))
        base_y = int(H * horizon) + 10
        # text plans per beat (headline zone first, jar sized to the space left)
        scratch = ImageDraw.Draw(Image.new("RGBA", (W, H)))
        text_top = int(H * 0.15)
        plans, text_end = [], text_top
        for b in beats:
            head = rc.guard(str(b.get("on") or "")).upper()
            f, lines = pc.fit_headline(scratch, head, W - 2 * m, H * 0.13, start=104, min_size=60, max_lines=2)
            words, y = _word_layout(scratch, lines, f, text_top, W / 2)
            sub_t = rc.guard(str(b.get("sub") or ""))
            sub_lines = pc._wrap(scratch, sub_t, bf, W - 2 * m, 2) if sub_t else []
            end = y + int(H * 0.038) + len(sub_lines) * int(bf.size * 1.25) + int(H * 0.012) + bf.size * 2
            plans.append(dict(font=f, words=words, y_end=y, sub_lines=sub_lines))
            text_end = max(text_end, end)
        jar_h = min(int(H * 0.44), base_y - text_end - int(H * 0.03))
        jar = pc.load_jar(sku, jar_h)
        cx = int(W * (0.5 if layout != "cinematic_offset" else 0.56))
        jl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        jb = pc.place_jar(jl, jar, cx, base_y, pal)
        jar_alpha = np.zeros((H, W), np.float32)
        jar_alpha[jb[1]:jb[3], jb[0]:jb[2]] = np.asarray(jar.getchannel("A"), np.float32)[:jb[3] - jb[1], :jb[2] - jb[0]] / 255.0
        jyy, jxx = np.mgrid[0:H, 0:W].astype(np.float32)
        # soft dark scrim behind the text block so the sub-line stays legible over bright bokeh
        sy0, sy1 = text_top - int(H * 0.03), min(jb[1] - int(H * 0.01), text_end + int(H * 0.02))
        prof = np.zeros(H, np.float32)
        ramp = int(H * 0.04)
        prof[sy0:sy1] = 1.0
        prof[max(0, sy0 - ramp):sy0] = np.linspace(0, 1, sy0 - max(0, sy0 - ramp))
        prof[sy1:sy1 + ramp] = np.linspace(1, 0, len(prof[sy1:sy1 + ramp]))
        xs_ = np.abs(np.arange(W, dtype=np.float32) - W / 2) / (W / 2)
        scrim_a = (prof[:, None] * (1 - 0.45 * xs_ ** 2)[None, :] * 150).astype("uint8")
        scrim = Image.new("RGBA", (W, H), tuple(int(c) for c in pal["deep"]) + (0,))
        scrim.putalpha(Image.fromarray(scrim_a))
        n = int(seconds * FPS)
        cta_at = seconds * 0.70
        beat_len = cta_at / len(plans)
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        audio = _music(seed, audio)
        tmpv = out_path + ".noaudio.mp4"
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        proc = subprocess.Popen([ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                                 "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                                 tmpv], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        last_meta = None
        poster_frame = None
        for fi in range(n):
            t = fi / FPS
            fr = bd.frame(t, seconds)
            fr.alpha_composite(jl)
            # 8. specular glint across the glass (subtle, additive, inside jar alpha only)
            for c0 in (1.2, 6.0):
                g = (t - c0) / 1.6
                if 0 <= g <= 1:
                    pos = jb[0] - 120 + (jb[2] - jb[0] + 240) * g
                    band = np.exp(-(((jxx - pos) + (jyy - jb[1]) * 0.35) ** 2) / (2 * 38 ** 2)) * jar_alpha
                    arr = np.asarray(fr, np.float32)
                    arr[..., :3] += (band * 0.16 * 255)[..., None] * (1 - arr[..., :3] / 255)
                    fr = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
            fr.alpha_composite(scrim)
            # 9. kinetic text
            bi = min(len(plans) - 1, int(min(t, cta_at - 1e-3) / beat_len))
            pl = plans[bi]
            lt = t - bi * beat_len
            boxes = []
            tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for wi, (wd, x, y) in enumerate(pl["words"]):
                a = np.clip((lt - 0.15 - wi * 0.12) / 0.25, 0, 1)
                if a <= 0:
                    continue
                dy = int((1 - a) * 28)
                sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(sh).text((x + 3, y + 5 + dy), wd, font=pl["font"], fill=(0, 0, 0, int(190 * a)))
                tl.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
                ImageDraw.Draw(tl).text((x, y + dy), wd, font=pl["font"], fill=tuple(pal["ink"]) + (int(255 * a),))
            for ln_words in [pl["words"]]:
                if ln_words:
                    xs = [w[1] for w in ln_words]
                    boxes.append((min(xs), text_top, W - min(xs), pl["y_end"]))
            fr.alpha_composite(tl)
            y = pl["y_end"] + int(H * 0.02)
            sub_end = y + int(H * 0.018) + len(pl["sub_lines"]) * int(bf.size * 1.25)
            sa = np.clip((lt - 0.15 - len(pl["words"]) * 0.12) / 0.4, 0, 1)
            if pl["sub_lines"] and sa > 0:
                sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(sl).line((W / 2 - 60, y, W / 2 + 60, y), fill=tuple(pal["accent"]) + (int(255 * sa),), width=5)
                y += int(H * 0.018)
                for ln in pl["sub_lines"]:
                    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(hl).text((W / 2, y + 2), ln, font=bf, fill=(0, 0, 0, int(230 * sa)), anchor="ma",
                                            stroke_width=4, stroke_fill=(0, 0, 0, int(200 * sa)))
                    sl.alpha_composite(hl.filter(ImageFilter.GaussianBlur(4)))
                    pc._text(sl, (W / 2, y), ln, bf, tuple(pal["accent"]) + (int(255 * sa),), anchor="ma")
                    y += int(bf.size * 1.25)
                fr.alpha_composite(sl)
            chip_y = sub_end + int(H * 0.012)
            chip = pc.strip_chip(fr, (W / 2, chip_y), pal, sku, anchor="ma")
            boxes.append(chip)
            show_cta = t >= cta_at
            if show_cta:
                ca = min(1.0, (t - cta_at) / 0.35)
                cl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                pc.brand_frame(cl, pal, cta=cta)
                if ca < 1:
                    cl.putalpha(cl.getchannel("A").point(lambda v: int(v * ca)))
                fr.alpha_composite(cl)
            else:
                pc.brand_frame(fr, pal, cta=None)
            rgb = fr.convert("RGB")
            proc.stdin.write(rgb.tobytes())
            if fi == int(n * 0.92):
                poster_frame = rgb
                last_meta = dict(boxes=boxes, font=pl["font"])
        proc.stdin.close()
        proc.wait()
        if proc.returncode:
            raise RuntimeError(f"ffmpeg encode failed rc={proc.returncode}")
        cmd = [ff, "-y", "-i", tmpv]
        if audio:
            cmd += ["-i", audio, "-map", "0:v", "-map", "1:a", "-af",
                    f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, seconds - 1.2)}:d=1.2", "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-c:v", "copy", "-t", str(seconds), "-movflags", "+faststart", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        os.remove(tmpv)
        poster_path = poster_path or out_path.rsplit(".", 1)[0] + "_poster.jpg"
        (poster_frame or rgb).save(poster_path, quality=93)
        return {"path": out_path, "poster": poster_path, "audio": audio, "jar_box": jb, "layout": layout,
                "text_boxes": (last_meta or {}).get("boxes", []), "headline_px": (last_meta or {}).get("font", bf).size,
                "body_px": bf.size, "sku": sku, "cinematic": True}
    finally:
        rc.reset_sku(tok)


_PROCESS_START = __import__("time").monotonic()


def _budget_left() -> float:
    """Seconds left in this process's total cinematic budget (CINEMATIC_TOTAL_BUDGET_S, default 1500)."""
    import time
    return float(os.getenv("CINEMATIC_TOTAL_BUDGET_S", "1500")) - (time.monotonic() - _PROCESS_START)


def render_cinematic_until_pass(sku, beats, out_path, *, seconds=10.0, seed=0, max_tries=None, gate=None) -> dict | None:
    """Render, run the unchanged visual gate, re-render with a new layout/palette on failure.

    Bounded: at most CINEMATIC_MAX_TRIES attempts (default 2, hard cap 3), and no attempt starts unless
    the remaining process budget covers one more render (CINEMATIC_EST_RENDER_S, default 300). On
    exhaustion returns None so the caller falls back to the fast legacy renderer.
    """
    import time
    from content_generator.creative import visual_gate
    max_tries = min(3, max(1, int(max_tries or os.getenv("CINEMATIC_MAX_TRIES", "2"))))
    est = float(os.getenv("CINEMATIC_EST_RENDER_S", "300"))
    recent = visual_gate.recent_layouts()
    gate = gate or (lambda p, meta: visual_gate.evaluate_video(p, meta, recent))
    for i in range(max_tries):
        if _budget_left() < est:
            logger.warning("[cinematic] time budget low (%.0fs left); falling back to legacy renderer", _budget_left())
            return None
        t0 = time.monotonic()
        layout = LAYOUTS[(seed + i) % len(LAYOUTS)]
        meta = render_cinematic_video(sku, beats, out_path, seconds=seconds, seed=seed + i, layout=layout,
                                      palette_idx=seed + i + i // len(LAYOUTS))
        est = max(est, time.monotonic() - t0)
        verdict = gate(out_path, meta)
        meta["visual_gate"] = verdict
        if verdict.get("passed"):
            visual_gate.remember_layout(layout, os.path.basename(out_path))
            return meta
        logger.warning("[cinematic] %s try %d failed visual gate: %s", sku, i + 1, (verdict.get("reasons") or [])[:4])
        if visual_gate.is_vision_hold(verdict):
            logger.error("[cinematic] no vision scorer available — holding (fail fast, no re-render)")
            return None
    return None
