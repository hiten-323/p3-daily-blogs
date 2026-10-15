"""Pre-publish visual-quality gate for every image and video piece.

Heuristic checks (deterministic, offline):
  * contrast / legibility of text regions (WCAG-style luminance ratio)
  * headline size hierarchy (headline >= 1.6x body, >= 4.5% of width)
  * background not flat or pale (colour variance, saturation, luminance range)
  * jar sharp, fully in frame, no overlap with text
  * layout variety vs the last 9 posted tiles
Plus a vision-model aesthetic score from a free provider (Gemini, then Groq
vision) with an 8.0 pass mark. A failing piece is re-rendered, never posted.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger(__name__)

AESTHETIC_PASS = 8.0
MIN_CONTRAST = 4.5
MIN_BG_STD = 14.0
MIN_BG_SAT = 0.22
MAX_BG_MEAN_LUMA = 175.0
MIN_LUMA_RANGE = 90.0
MIN_JAR_SHARPNESS = 60.0
HIERARCHY_RATIO = 1.6
RECENT_WINDOW = 9
MAX_SAME_LAYOUT_IN_WINDOW = 3


def _luma(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a, b):
    la, lb = sorted((_luma(a), _luma(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _text_contrast(img, box):
    """Contrast between the brightest/darkest clusters inside a text box."""
    import numpy as np
    x0, y0, x1, y1 = [int(v) for v in box]
    crop = np.asarray(img.crop((max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1))).convert("RGB"),
                      dtype=np.float32).reshape(-1, 3)
    if len(crop) < 16:
        return 21.0
    l = crop @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    lo, hi = np.percentile(l, 10), np.percentile(l, 97)
    fg = crop[l >= hi].mean(0)
    bg = crop[l <= lo].mean(0)
    return contrast_ratio(fg, bg)


def background_stats(img, exclude=()):
    import numpy as np
    small = img.convert("RGB").resize((180, int(180 * img.height / img.width)))
    a = np.asarray(small, dtype=np.float32)
    mask = np.ones(a.shape[:2], bool)
    sx, sy = small.width / img.width, small.height / img.height
    for b in exclude:
        if b:
            mask[int(b[1] * sy):int(b[3] * sy) + 1, int(b[0] * sx):int(b[2] * sx) + 1] = False
    px = a[mask]
    luma = px @ np.array([0.299, 0.587, 0.114], np.float32)
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return {"std": float(px.std(0).mean()), "sat": float(sat.mean()), "luma_mean": float(luma.mean()),
            "luma_range": float(np.percentile(luma, 98) - np.percentile(luma, 2))}


def _sharpness(img):
    from PIL import ImageFilter, ImageStat
    return ImageStat.Stat(img.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]


def _overlap(a, b, pad=0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def heuristic_checks(img, meta: dict, recent_layouts=()) -> tuple[list[str], dict]:
    reasons, m = [], {}
    W, H = img.size
    for i, box in enumerate(meta.get("text_boxes") or []):
        c = _text_contrast(img, box)
        m.setdefault("contrast", []).append(round(c, 2))
        if c < MIN_CONTRAST:
            reasons.append(f"low_contrast_text_{i}:{c:.1f}")
    hp, bp = meta.get("headline_px"), meta.get("body_px")
    if hp and bp and hp < HIERARCHY_RATIO * bp:
        reasons.append(f"weak_hierarchy:{hp}/{bp}")
    if hp and hp < 0.045 * W:
        reasons.append(f"headline_too_small:{hp}")
    bs = background_stats(img, exclude=[meta.get("jar_box")] + list(meta.get("text_boxes") or []))
    m["background"] = bs
    if bs["std"] < MIN_BG_STD:
        reasons.append(f"flat_background:std={bs['std']:.1f}")
    if bs["sat"] < MIN_BG_SAT:
        reasons.append(f"pale_background:sat={bs['sat']:.2f}")
    if bs["luma_mean"] > MAX_BG_MEAN_LUMA:
        reasons.append(f"washed_out_background:luma={bs['luma_mean']:.0f}")
    if bs["luma_range"] < MIN_LUMA_RANGE:
        reasons.append(f"no_tonal_depth:range={bs['luma_range']:.0f}")
    jb = meta.get("jar_box")
    if jb:
        if jb[0] < 0 or jb[1] < 0 or jb[2] > W or jb[3] > H:
            reasons.append("jar_out_of_frame")
        crop = img.crop([int(max(0, v)) for v in (jb[0], jb[1], min(W, jb[2]), min(H, jb[3]))])
        sh = _sharpness(crop)
        m["jar_sharpness"] = round(sh, 1)
        if sh < MIN_JAR_SHARPNESS:
            reasons.append(f"jar_not_sharp:{sh:.0f}")
        for i, box in enumerate(meta.get("text_boxes") or []):
            if _overlap(jb, box, pad=-4):
                reasons.append(f"text_overlaps_jar_{i}")
    elif meta.get("requires_jar", True):
        reasons.append("no_jar_box")
    recent = list(recent_layouts)[-RECENT_WINDOW:]
    lay = meta.get("layout")
    if lay and recent:
        if recent[-1:] == [lay]:
            reasons.append(f"same_layout_as_last_tile:{lay}")
        if recent.count(lay) >= MAX_SAME_LAYOUT_IN_WINDOW:
            reasons.append(f"layout_overused_in_last_{RECENT_WINDOW}:{lay}")
    return reasons, m


# ── vision aesthetic score (free providers) ────────────────────────────────
_PROMPT = (
    "You are a senior art director for premium D2C coffee brands on Instagram. Score this creative 0-10 "
    "for visual appeal and scroll-stopping polish: rich colour and depth (not flat/pale), typographic "
    "hierarchy and legibility, product presentation (sharp jar sitting on a surface, nothing overlapping it), "
    "brand consistency, and how strongly it makes a viewer want to follow or buy. Be strict: 8+ only for work "
    'a top agency would post. Reply JSON only: {"score": <number>, "issues": ["..."]}'
)


def _jpeg_b64(path, max_side=768):
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _parse(text):
    mt = re.search(r"\{.*\}", text or "", re.S)
    data = json.loads(mt.group(0)) if mt else {}
    return float(data.get("score")), [str(x) for x in data.get("issues") or []]


def _gemini(b64):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")
    body = {"contents": [{"parts": [{"text": _PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    return _parse(out["candidates"][0]["content"]["parts"][0]["text"])


def _groq(b64):
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    model = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    body = {"model": model, "temperature": 0.2, "messages": [{"role": "user", "content": [
        {"type": "text", "text": _PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    return _parse(out["choices"][0]["message"]["content"])


VISION_PROVIDERS = [("gemini", _gemini), ("groq", _groq)]


def aesthetic_score(path) -> dict:
    b64 = _jpeg_b64(path)
    errors = []
    for name, fn in VISION_PROVIDERS:
        try:
            res = fn(b64)
        except Exception as exc:  # rate limit / network: next provider
            errors.append(f"{name}:{str(exc)[:80]}")
            continue
        if res is None:
            continue
        score, issues = res
        return {"provider": name, "score": score, "issues": issues}
    return {"provider": None, "score": None, "issues": [], "errors": errors}


def evaluate(meta: dict, recent_layouts=(), *, vision=None) -> dict:
    """Full gate for one image. meta comes from premium_cards.render (or any renderer)."""
    from PIL import Image
    img = Image.open(meta["path"])
    reasons, metrics = heuristic_checks(img, meta, recent_layouts)
    out = {"passed": False, "reasons": reasons, "metrics": metrics}
    if reasons:
        return out  # don't spend vision quota on a piece that already fails
    v = (vision or aesthetic_score)(meta["path"])
    out["vision"] = v
    if v.get("score") is None:
        if os.getenv("VISUAL_VISION_REQUIRED", "1") != "0":
            out["reasons"] = ["vision_score_unavailable"] + list(v.get("errors") or [])
            return out
        out["passed"] = True
        return out
    if v["score"] < AESTHETIC_PASS:
        out["reasons"] = [f"aesthetic_below_{AESTHETIC_PASS}:{v['score']:.1f}"] + v.get("issues", [])[:3]
        return out
    out["passed"] = True
    return out


def evaluate_video(path: str, meta: dict | None = None, recent_layouts=(), *, vision=None, samples=3) -> dict:
    """Sample frames (imageio ffmpeg plugin) and gate each; all must pass."""
    import imageio.v3 as iio
    from PIL import Image
    frames = list(iio.imiter(path, plugin="ffmpeg"))
    if not frames:
        return {"passed": False, "reasons": ["video_unreadable"]}
    picks = [frames[int(i * (len(frames) - 1) / max(1, samples - 1))] for i in range(samples)]
    results = []
    tmp = path + ".gateframe.jpg"
    for k, fr in enumerate(picks):
        Image.fromarray(fr).save(tmp, quality=90)
        m = dict(meta or {}, path=tmp, requires_jar=bool((meta or {}).get("jar_box")))
        if k < samples - 1:  # entry frames: background depth only; final frame gets full + vision
            m = {"path": tmp, "requires_jar": False}
            r, met = heuristic_checks(Image.open(tmp), m)
            results.append({"passed": not r, "reasons": r, "metrics": met})
        else:
            results.append(evaluate(m, recent_layouts, vision=vision))
    try:
        os.remove(tmp)
    except OSError:
        pass
    reasons = [x for r in results for x in r["reasons"]]
    return {"passed": all(r["passed"] for r in results), "reasons": reasons, "frames": results}


_LAYOUT_LOG = os.path.join("output", "learning", "visual_layouts.json")


def recent_layouts(n: int = RECENT_WINDOW) -> list[str]:
    try:
        with open(_LAYOUT_LOG) as f:
            return [r["layout"] for r in json.load(f)][-n:]
    except Exception:
        return []


def remember_layout(layout, label="") -> None:
    if not layout:
        return
    try:
        with open(_LAYOUT_LOG) as f:
            rows = json.load(f)
    except Exception:
        rows = []
    rows = (rows + [{"layout": layout, "label": label}])[-50:]
    os.makedirs(os.path.dirname(_LAYOUT_LOG), exist_ok=True)
    with open(_LAYOUT_LOG, "w") as f:
        json.dump(rows, f)
