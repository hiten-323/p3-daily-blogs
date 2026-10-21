"""Per-concept procedural (or AI-clip) backdrops with distinct camera motion.

Used by cinematic_motion.render_cinematic_video when a daily concept from
shorts_concepts is supplied. Background only: the official jar cutout is
composited on top by the caller and is never drawn or generated here.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BW, BH = 540, 960

_TONES = {
    "rich":   dict(),
    "noir":   dict(deep=(0.55, None), mid=(0.75, None)),
    "golden": dict(glow=(0.70, (240, 170, 70)), mid=(0.80, (150, 90, 30))),
    "cool":   dict(deep=(0.70, (14, 26, 44)), mid=(0.78, (40, 60, 80))),
    "velvet": dict(mid=(0.75, None), glow=(0.75, "accent")),
    "neon":   dict(glow=(0.72, (70, 200, 215)), deep=(0.75, (10, 12, 30))),
    "dawn":   dict(glow=(0.70, (255, 172, 112)), mid=(0.82, (170, 90, 70))),
}


def grade_toward_palette(frame, pal: dict):
    """Pull a background plate 30% toward the jar-label deep/glow colours."""
    img = np.asarray(frame, np.float32)
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    deep = np.array(pal["deep"], np.float32)
    glow = np.array(pal["glow"], np.float32)
    lum = img.mean(axis=2, keepdims=True) / 255.0
    graded = deep * (1 - lum) + glow * lum
    return np.clip(img * 0.7 + graded * 0.3, 0, 255).astype("uint8")


def tone_palette(pal: dict, tone: str) -> dict:
    """Blend at most ~30% toward a mood colour, so the jar-label palette still leads."""
    out = {k: tuple(int(v) for v in c) for k, c in pal.items()}
    for key, (keep, target) in _TONES.get(tone, {}).items():
        base = np.array(out[key], np.float32)
        if target is None:
            col = base * keep
        else:
            tgt = np.array(out["accent"] if target == "accent" else target, np.float32)
            col = base * keep + tgt * (1 - keep)
        out[key] = tuple(int(np.clip(v, 0, 255)) for v in col)
    return out


def _noise(h, w, scale, rng):
    small = rng.random((max(2, h // scale), max(2, w // scale))).astype(np.float32)
    return np.asarray(Image.fromarray((small * 255).astype("uint8")).resize((w, h), Image.BICUBIC), np.float32) / 255.0


def camera(motion: str, u: float):
    """(zoom, dx, dy, blur, time_warp) for normalised time u in [0, 1]."""
    s = 0.5 - 0.5 * math.cos(math.pi * u)  # ease in-out
    z, dx, dy, blur, tw = 1.06, 0.0, 0.0, 0.0, u
    if motion == "push_in":
        z = 1.02 + 0.16 * s
    elif motion == "pull_out":
        z = 1.20 - 0.16 * s
    elif motion == "orbit":
        z, dx, dy = 1.12, 44 * math.sin(2 * math.pi * u * 0.8), 18 * math.cos(2 * math.pi * u * 0.8)
    elif motion == "parallax_pan_l":
        z, dx = 1.14, 50 - 100 * s
    elif motion == "parallax_pan_r":
        z, dx = 1.14, -50 + 100 * s
    elif motion == "rack_focus":
        z, blur = 1.06 + 0.05 * s, 7.0 * abs(math.cos(math.pi * u)) ** 3
    elif motion == "speed_ramp":
        tw = u + 0.22 * math.sin(2 * math.pi * u) / (2 * math.pi) * 4
        z = 1.04 + 0.12 * tw
    elif motion == "crane_up":
        z, dy = 1.14, 60 - 120 * s
    elif motion == "dolly_zoom":
        z = 1.02 + 0.26 * s ** 2
    return z, dx, dy, blur, tw


class ConceptBackdrop:
    def __init__(self, pal, seed, scene, motion, light_path, horizon, ai_frames=None):
        self.pal = {k: np.array(v, np.float32) for k, v in pal.items()}
        self.scene, self.motion = scene, motion
        self.rng = np.random.default_rng(seed)
        self.light, self.horizon = light_path, horizon
        self.ai = ai_frames
        yy, xx = np.mgrid[0:BH, 0:BW].astype(np.float32)
        self.xx, self.yy = xx, yy
        r = self.rng
        self.noise = [_noise(BH * 2, BW, s, r) for s in (64, 26)]
        self.marble = _noise(BH, BW, 90, r)
        self.grain = [r.normal(0, 6.0, (BH, BW, 1)).astype(np.float32) for _ in range(4)]
        n = 320 if scene in ("granules", "embers", "tunnel") else 160
        self.p = dict(x=r.uniform(0, BW, n), y=r.uniform(-BH, BH, n), s=r.uniform(0.6, 2.6, n),
                      v=r.uniform(20, 70, n), ph=r.uniform(0, 6.28, n), d=r.uniform(0.3, 1.4, n),
                      a=r.uniform(0, 6.28, n), hue=r.random(n))
        self.bok = [dict(x=r.uniform(0, BW), y=r.uniform(0, BH * 0.7), r=r.uniform(8, 46), a=r.uniform(0.12, 0.38),
                         vx=r.uniform(-6, 6), ph=r.uniform(0, 6.28), hue=r.random()) for _ in range(40)]
        v = 1 - 0.62 * np.clip(np.sqrt(((xx - BW / 2) / (BW / 1.25)) ** 2 + ((yy - BH / 2) / (BH / 1.25)) ** 2), 0, 1) ** 2
        self.vig = v[..., None]

    # ── base gradient with drifting key light ──────────────────────────────
    def _base(self, te):
        p = self.pal
        lx0, ly0, lx1, ly1 = self.light
        lx = (lx0 + (lx1 - lx0) * te) * BW
        ly = (ly0 + (ly1 - ly0) * te) * BH
        d = np.sqrt((self.xx - lx) ** 2 + (self.yy - ly) ** 2) / math.hypot(BW, BH)
        tt = np.clip(d * 1.9, 0, 1)[..., None]
        img = p["glow"] * (1 - tt) ** 1.6 + p["mid"] * (1 - tt) * tt * 2 + p["deep"] * tt ** 1.4
        hz = self.horizon * BH
        plane = np.clip((self.yy - hz) / max(1, BH - hz), 0, 1)[..., None]
        img = img * (1 - 0.45 * plane) + p["deep"] * 0.45 * plane
        edge = np.exp(-((self.yy - hz) ** 2) / (2 * (BH * 0.004) ** 2))[..., None]
        return img + p["accent"] * 0.22 * edge

    def _dots(self, canvas, pts, blur=0):
        layer = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for x, y, r, col in pts:
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)) if blur else layer)

    def _scene(self, te, t):
        p, q, s = self.pal, self.p, self.scene
        img = self._base(te)
        xx, yy = self.xx, self.yy
        acc = p["accent"]
        if s == "spotlight":
            img = img * 0.55
            cone = np.clip(1 - np.abs(xx - BW * (0.5 + 0.08 * math.sin(t * 0.6))) / (60 + yy * 0.32), 0, 1) ** 1.5
            img = img + (p["glow"] * 0.55 + 70) * cone[..., None] * 0.55
            veins = np.exp(-((self.marble - 0.5) ** 2) / 0.0008) * (yy > self.horizon * BH)
            img = img + 60 * veins[..., None]
        elif s == "swirl":
            cy = BH * 0.80
            sx, sy = (xx - BW / 2) / BW, (yy - cy) / BH * 2.6
            r = np.sqrt(sx ** 2 + sy ** 2)
            th = np.arctan2(sy, sx)
            sw = (0.5 + 0.5 * np.sin(22 * r + 4 * th - 5.5 * te * math.pi)) * np.exp(-r * 1.6)
            img = img + ((acc * 0.6 + p["mid"] * 0.4) - img) * (0.55 * sw)[..., None]
        elif s == "light_sweep":
            for k, w in ((0, 0.010), (0.35, 0.02), (0.7, 0.006)):
                band = np.exp(-(((xx / BW) * 0.9 - (yy / BH) * 0.4 - (-0.6 + 1.9 * te - k)) ** 2) / w)
                img = img + (acc * 0.55 + 60) * 0.35 * band[..., None]
        elif s == "sunrise":
            sky = np.clip(1 - yy / (BH * 0.7), 0, 1)[..., None]
            img = img * (1 - 0.5 * sky) + (p["glow"] * 0.7 + np.array([80, 40, 0], np.float32)) * 0.5 * sky
            sun_y = BH * (0.55 - 0.25 * te)
            ds = np.sqrt((xx - BW * 0.5) ** 2 + (yy - sun_y) ** 2)
            img = img + 255 * np.exp(-(ds / 70) ** 2)[..., None] * 0.6 + acc * np.exp(-(ds / 260) ** 2)[..., None] * 0.4
            th = np.arctan2(yy - sun_y, xx - BW * 0.5)
            rays = (0.5 + 0.5 * np.sin(th * 18 + t * 0.4)) * np.exp(-ds / 420)
            img = img + 40 * rays[..., None]
            for fx in (0.33, 0.66):  # window mullions
                img = img * (1 - 0.7 * np.exp(-((xx - BW * fx) ** 2) / 30)[..., None] * sky)
        elif s == "velvet":
            folds = 0.5 + 0.5 * np.sin(xx / 34 + 2.2 * np.sin(yy / 160 + t * 0.7) + self.noise[0][:BH] * 3)
            img = img * (0.6 + 0.55 * folds[..., None])
        elif s == "tunnel":
            cx, cy = BW / 2, BH * 0.42
            th = np.arctan2(yy - cy, xx - cx)
            r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            streak = (np.sin(th * 46) > 0.92) * np.clip(np.sin(r / 22 - t * 14) * 0.5 + 0.5, 0, 1) * np.clip(r / 300, 0, 1)
            img = img * 0.7 + (acc * 0.7 + p["glow"] * 0.3) * streak[..., None] * 0.9
            img = img + p["glow"] * np.exp(-(r / 90) ** 2)[..., None] * 0.6
        elif s == "ink":
            off = int(t * 18) % BH
            n1 = np.roll(self.noise[0], -off, axis=0)[:BH]
            n2 = np.roll(self.noise[1], off // 2, axis=1)[:BH]
            plume = np.clip((n1 * 0.6 + n2 * 0.4 - 0.42 + 0.12 * math.sin(t)) * 3.4, 0, 1) ** 1.4
            img = img * (1 - 0.6 * plume[..., None]) + (p["mid"] * 0.5 + acc * 0.5) * 0.6 * plume[..., None]
        canvas = Image.fromarray(np.clip(img, 0, 255).astype("uint8")).convert("RGBA")
        # particle / overlay layers
        if s in ("steam", "monsoon", "rain_steam"):
            off = int((t * 30) % BH)
            n1 = np.roll(self.noise[0], -off, axis=0)[:BH]
            n2 = np.roll(self.noise[1], -int(off * 1.7), axis=0)[:BH]
            wx = np.clip(1 - np.abs((xx - BW * 0.5 - 40 * np.sin(yy / 80 + t)) / (BW * 0.48)), 0, 1)
            amt = 1.0 if s == "steam" else 0.5
            st = np.clip((n1 * 0.6 + n2 * 0.4 - 0.42) * 3.2, 0, 1) * wx * np.clip(yy / (BH * 0.2), 0, 1) * amt
            sl = Image.new("RGBA", (BW, BH), tuple(int(c) for c in (p["ink"] * 0.8 + p["glow"] * 0.2)) + (0,))
            sl.putalpha(Image.fromarray((st * 220).astype("uint8")).filter(ImageFilter.GaussianBlur(4)))
            canvas.alpha_composite(sl)
            if s == "steam":  # strong backlight halo
                halo = np.exp(-(((xx - BW / 2) / 180) ** 2 + ((yy - BH * 0.35) / 260) ** 2))
                hl = Image.new("RGBA", (BW, BH), tuple(int(c) for c in p["glow"]) + (0,))
                hl.putalpha(Image.fromarray((halo * 120).astype("uint8")))
                canvas.alpha_composite(hl)
        if s in ("rain", "monsoon"):
            lay = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            ys = (q["y"] + q["v"] * 9 * t) % (BH * 2) - BH * 0.5
            for i in range(len(ys)):
                L = 10 + 26 * q["d"][i]
                d.line((q["x"][i], ys[i], q["x"][i] - 3, ys[i] + L), fill=(210, 225, 240, int(60 + 70 * q["d"][i])), width=1)
            canvas.alpha_composite(lay)
            self._dots(canvas, [(b["x"] + b["vx"] * t, b["y"], b["r"] * 0.7,
                                 tuple(int(c) for c in (acc * 0.8 + 50)) + (int(255 * b["a"]),)) for b in self.bok], blur=8)
            if s == "monsoon":
                leaf = np.clip(np.sin(xx / 22 + self.marble * 9) * np.sin(yy / 30 + t * 0.6), 0, 1) * (xx < BW * 0.22)
                lf = Image.new("RGBA", (BW, BH), (30, 80, 40, 0))
                lf.putalpha(Image.fromarray((leaf * 150).astype("uint8")).filter(ImageFilter.GaussianBlur(3)))
                canvas.alpha_composite(lf)
        if s in ("city_bokeh", "light_sweep", "spotlight", "embers", "sunrise", "velvet", "swirl", "ink", "tunnel"):
            pal3 = [acc, p["glow"], np.array([80, 200, 210], np.float32) if s == "city_bokeh" else p["ink"]]
            k = 40 if s == "city_bokeh" else 16
            self._dots(canvas, [(b["x"] + b["vx"] * t * (2 if s == "city_bokeh" else 1),
                                 b["y"] - (t * 14 if s == "embers" else 0),
                                 b["r"] * (1.2 if s == "city_bokeh" else 0.6),
                                 tuple(int(c) for c in pal3[int(b["hue"] * 3) % 3]) + (int(255 * b["a"] * (0.7 + 0.3 * math.sin(b["ph"] + t * 1.4))),))
                                for b in self.bok[:k]], blur=7)
        if s in ("granules", "embers", "cascade", "light_sweep", "spotlight", "tunnel", "sunrise"):
            lay = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            if s == "embers":
                ys = BH - ((q["y"] + BH + q["v"] * t) % (BH * 2))
                xs = q["x"] + 14 * np.sin(q["ph"] + t * 1.7 + ys / 70)
            elif s == "tunnel":
                ang, rad = q["a"], ((q["y"] + BH) / (2 * BH) + t * 0.35 * q["d"]) % 1.0
                xs, ys = BW / 2 + np.cos(ang) * rad ** 2 * BW, BH * 0.42 + np.sin(ang) * rad ** 2 * BH
            elif s in ("light_sweep", "spotlight", "sunrise"):  # dust motes
                ys = (q["y"] + 6 * t * q["d"]) % BH
                xs = q["x"] + 10 * np.sin(q["ph"] + t * 0.5)
            else:
                ys = (q["y"] + q["v"] * (3.2 if s == "cascade" else 1.0) * t) % (BH * 2) - BH * 0.5
                xs = q["x"] + 18 * np.sin(q["ph"] + t * 1.1 + ys / 120)
            lim = 110 if s == "cascade" else len(xs)
            for i in range(lim):
                z = q["d"][i]
                if s == "cascade":
                    rw, rh = 9 * z + 5, 6 * z + 3.5
                    ang = q["a"][i] + t * 3 * (q["hue"][i] - 0.5)
                    bean = Image.new("RGBA", (int(rw * 2 + 4), int(rh * 2 + 4)), (0, 0, 0, 0))
                    bd = ImageDraw.Draw(bean)
                    bd.ellipse((2, 2, rw * 2 + 2, rh * 2 + 2), fill=(70, 38, 18, 245), outline=(120, 70, 36, 255))
                    bd.line((rw * 0.4 + 2, rh + 2, rw * 1.6 + 2, rh + 2), fill=(30, 14, 6, 255), width=2)
                    bean = bean.rotate(math.degrees(ang), expand=True)
                    lay.alpha_composite(bean, (int(np.clip(xs[i], 0, BW - bean.width)), int(np.clip(ys[i], 0, BH - bean.height))))
                    continue
                r = q["s"][i] * z * (1.6 if s == "embers" else 1)
                if s in ("embers", "tunnel"):
                    col = tuple(int(c) for c in (acc * 0.6 + np.array([255, 140, 40]) * 0.4)) + (220,)
                elif s in ("light_sweep", "spotlight", "sunrise"):
                    col = (255, 240, 210, 110)
                else:
                    col = tuple(int(c) for c in acc) + (200,) if q["hue"][i] < 0.35 else (58, 34, 18, 225)
                d.ellipse((xs[i] - r, ys[i] - r * 0.8, xs[i] + r, ys[i] + r * 0.8), fill=col)
            canvas.alpha_composite(lay.filter(ImageFilter.GaussianBlur(0.6)) if s != "cascade" else lay)
        return canvas

    def _ai(self, te, t):
        fr = self.ai[int(te * (len(self.ai) - 1))]
        return Image.fromarray(grade_toward_palette(fr, self.pal)).convert("RGBA")

    def frame(self, t, dur, out_size):
        u = min(1.0, max(0.0, t / dur))
        z, dx, dy, blur, tw = camera(self.motion, u)
        te = min(1.0, max(0.0, tw))
        canvas = self._ai(te, t) if self.ai else self._scene(te, t * (0.6 + 0.8 * te if self.motion == "speed_ramp" else 1))
        cw, ch = BW / z, BH / z
        x0 = (BW - cw) / 2 + dx / z
        y0 = (BH - ch) / 2 + dy / z
        x0, y0 = min(max(0, x0), BW - cw), min(max(0, y0), BH - ch)
        canvas = canvas.transform((BW, BH), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.BILINEAR)
        if blur > 0.4:
            canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
        arr = np.asarray(canvas.convert("RGB"), np.float32)
        arr = (arr + self.grain[int(t * 30) % 4]) * self.vig
        return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).resize(out_size, Image.BILINEAR).convert("RGBA")
