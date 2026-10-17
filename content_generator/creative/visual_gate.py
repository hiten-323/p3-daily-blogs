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
    if data.get("score") is None:
        raise ValueError("no score in vision reply")
    return float(data.get("score")), [str(x) for x in data.get("issues") or []]


_UA = {"User-Agent": "PurityBeans/1.0"}
_HTTP_TIMEOUT = float(os.getenv("VISION_HTTP_TIMEOUT_S", "45"))

# Circuit breaker: a provider/model that answered 429/402/404 is skipped for the rest of the
# process (429: until its cool-down passes) so every re-render doesn't re-pay the same failures.
_DEAD: dict[str, float] = {}
_LIST_CACHE: dict[str, list] = {}


def _dead(key):
    import time
    until = _DEAD.get(key)
    return until is not None and time.monotonic() < until


def _mark(key, exc):
    import time
    code = getattr(exc, "code", None)
    if code == 429:
        _DEAD[key] = time.monotonic() + float(os.getenv("VISION_429_COOLDOWN_S", "600"))
    elif code in (401, 402, 403, 404, 410):
        _DEAD[key] = float("inf")


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _listed(cache_key, fn):
    if cache_key not in _LIST_CACHE:
        try:
            _LIST_CACHE[cache_key] = list(fn())
        except Exception:
            _LIST_CACHE[cache_key] = []
    return _LIST_CACHE[cache_key]


def _msg_text(msg):
    """Content, falling back to reasoning text (reasoning models may put the JSON there)."""
    c = msg.get("content")
    if isinstance(c, list):
        c = " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return (c or "") + "\n" + str(msg.get("reasoning_content") or msg.get("reasoning") or "") if not c else c


def _openai_vision(url, key, model, b64, extra=None):
    body = {"model": model, "temperature": 0.2, "max_tokens": 3000, "messages": [{"role": "user", "content": [
        {"type": "text", "text": _PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    body.update(extra or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "Authorization": f"Bearer {key}", **_UA})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        out = json.loads(raw)
    except ValueError:
        # Some gateways stream SSE ("data: {...}") or wrap errors in HTML/text.
        chunks = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
        parts = []
        for ch in chunks:
            if ch == "[DONE]":
                continue
            try:
                d = json.loads(ch)["choices"][0]
                parts.append(str((d.get("delta") or d.get("message") or {}).get("content") or ""))
            except Exception:
                continue
        if not parts:
            raise ValueError(f"non-JSON response: {raw[:60]!r}")
        return _parse("".join(parts))
    if "choices" not in out:
        raise ValueError(f"no choices: {str(out)[:60]}")
    return _parse(_msg_text(out["choices"][0].get("message") or {}))


def _try_models(prefix, models, call):
    errs = []
    for model in models:
        k = f"{prefix}:{model}"
        if _dead(k) or _dead(prefix):
            continue
        try:
            return call(model)
        except Exception as exc:
            _mark(k, exc)
            if getattr(exc, "code", None) in (401, 402):
                _mark(prefix, exc)  # key-level problem: whole provider is out
            errs.append(f"{model}:{str(exc)[:40]}")
    if errs:
        raise RuntimeError("; ".join(errs))
    raise RuntimeError("no live model")


def _gemini_models(key):
    """Configured models first, then whatever flash models the key can actually call."""
    models = [m for m in [os.getenv("GEMINI_VISION_MODEL", ""), os.getenv("GEMINI_MODEL", "")] if m]

    def ls():
        listed = _get_json(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=200")
        for m in listed.get("models") or []:
            name = str(m.get("name", "")).split("/")[-1]
            if "flash" in name and "generateContent" in (m.get("supportedGenerationMethods") or []) \
                    and not any(x in name for x in ("tts", "image", "live", "audio", "embedding")):
                yield name
    models += _listed("gemini", ls)
    return list(dict.fromkeys(models))[:4]


def _gemini(b64):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    body = {"contents": [{"parts": [{"text": _PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}]}

    def call(model):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **_UA})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as r:
            out = json.loads(r.read())
        return _parse(out["candidates"][0]["content"]["parts"][0]["text"])
    try:
        return _try_models("gemini", _gemini_models(key), call)
    except RuntimeError as exc:
        # quota 429 on every model = account quota: skip gemini for the cool-down
        if "429" in str(exc):
            _mark("gemini", type("E", (Exception,), {"code": 429})())
        raise


_VISION_HINTS = ("vision", "-vl", "vl-", "llama-4", "scout", "maverick", "gemma-3", "gemma-4", "pixtral",
                 "qwen2.5-vl", "qwen3-vl", "kimi", "phi-4-multimodal", "phi-3-vision", "nemotron")


def _groq_models(key):
    """Only models the key actually lists (no hardcoded ids that Groq may retire)."""
    env = [m for m in [os.getenv("GROQ_VISION_MODEL", "")] if m]

    def ls():
        listed = _get_json("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
        for m in listed.get("data") or []:
            mid = str(m.get("id", ""))
            if m.get("active", True) and any(x in mid.lower() for x in _VISION_HINTS) and "guard" not in mid:
                yield mid
    return list(dict.fromkeys(env + _listed("groq", ls)))[:3]


def _groq(b64):
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    return _try_models("groq", _groq_models(key), lambda m: _openai_vision(
        "https://api.groq.com/openai/v1/chat/completions", key, m, b64, {"max_tokens": 1024}))


def _github_models(b64):
    """Free GitHub Models vision fallback (gpt-4.1-mini / gpt-4o-mini accept images)."""
    key = (os.getenv("GITHUB_MODELS_TOKEN", "") or os.getenv("GH_MODELS_TOKEN", "")).strip()
    if not key:
        return None
    models = list(dict.fromkeys([m for m in [os.getenv("GITHUB_VISION_MODEL", ""), "openai/gpt-4.1-mini",
                                             "openai/gpt-4o-mini"] if m]))
    return _try_models("github_models", models, lambda m: _openai_vision(
        "https://models.github.ai/inference/chat/completions", key, m, b64, {"max_tokens": 1024}))


def _openrouter_models(key):
    env = [m for m in [os.getenv("OPENROUTER_VISION_MODEL", "")] if m]

    def ls():
        listed = _get_json("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {key}"})
        for m in listed.get("data") or []:
            mid = str(m.get("id", ""))
            mods = ((m.get("architecture") or {}).get("input_modalities") or [])
            if mid.endswith(":free") and "image" in mods:
                yield mid
    return list(dict.fromkeys(env + _listed("openrouter", ls)))[:4]


def _openrouter(b64):
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    models = [m for m in _openrouter_models(key) if m.endswith(":free")]  # never a paid slug
    return _try_models("openrouter", models, lambda m: _openai_vision(
        "https://openrouter.ai/api/v1/chat/completions", key, m, b64))


def _nvidia_models(key):
    """Discover NVIDIA vision models; prefer the newest Nemotron VL (e.g. nemotron-3.5-super-vl)."""
    env = [m for m in [os.getenv("NVIDIA_VISION_MODEL", "")] if m]

    def ls():
        listed = _get_json("https://integrate.api.nvidia.com/v1/models", {"Authorization": f"Bearer {key}"})
        ids = [str(m.get("id", "")) for m in listed.get("data") or []]
        ids = [i for i in ids if "embed" not in i and "retriever" not in i]
        nemo = sorted([i for i in ids if "nemotron" in i and "vl" in i.lower()], reverse=True)
        other = [i for i in ids if i not in nemo and any(x in i.lower() for x in ("vision", "-vl", "vl-"))]
        return nemo + other
    return list(dict.fromkeys(env + _listed("nvidia", ls)))[:3]


def _nvidia(b64):
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        return None
    return _try_models("nvidia", _nvidia_models(key), lambda m: _openai_vision(
        "https://integrate.api.nvidia.com/v1/chat/completions", key, m, b64))


# Free providers first; NVIDIA last (house rule).
VISION_PROVIDERS = [("gemini", _gemini), ("groq", _groq), ("github_models", _github_models),
                    ("openrouter", _openrouter), ("nvidia", _nvidia)]

_OUTAGE = {"n": 0}


def vision_outage() -> bool:
    """True once every scorer has failed VISION_OUTAGE_AFTER times in a row (default 2) this process.
    Callers stop re-rendering then and hold the piece instead of burning the run budget."""
    return _OUTAGE["n"] >= int(os.getenv("VISION_OUTAGE_AFTER", "2"))


def aesthetic_score(path) -> dict:
    if vision_outage():
        return {"provider": None, "score": None, "issues": [], "errors": ["vision_outage:all_providers_down"]}
    b64 = _jpeg_b64(path)
    errors = []
    for name, fn in VISION_PROVIDERS:
        if _dead(name):
            errors.append(f"{name}:circuit_open")
            continue
        try:
            res = fn(b64)
        except Exception as exc:  # rate limit / network: next provider
            errors.append(f"{name}:{str(exc)[:80]}")
            continue
        if res is None:
            continue
        score, issues = res
        _OUTAGE["n"] = 0
        return {"provider": name, "score": score, "issues": issues}
    _OUTAGE["n"] += 1
    return {"provider": None, "score": None, "issues": [], "errors": errors}


def is_vision_hold(verdict: dict) -> bool:
    return any(str(r).startswith("vision_score_unavailable") for r in (verdict or {}).get("reasons") or []) \
        or any(is_vision_hold(f) for f in (verdict or {}).get("frames") or [])


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
    """Sample frames through imageio's supported FFMPEG reader and gate each.

    imageio-ffmpeg provides the v2 FFMPEG reader; it is not a v3 plugin named
    ffmpeg. Sample by frame index rather than loading the entire video into
    memory, which is safer for longer or high-resolution renders.
    """
    from PIL import Image
    try:
        import imageio.v2 as imageio
        reader = imageio.get_reader(path, format="FFMPEG")
    except Exception as exc:
        return {"passed": False, "reasons": [f"video_unreadable:{type(exc).__name__}"]}
    try:
        try:
            total = int(reader.count_frames())
        except Exception:
            try:
                total = int(reader.get_length())
            except Exception:
                total = 0
        if total <= 0:
            return {"passed": False, "reasons": ["video_unreadable"]}
        count = max(1, min(int(samples or 1), total))
        indices = sorted({round(i * (total - 1) / max(1, count - 1)) for i in range(count)})
        try:
            picks = [reader.get_data(idx) for idx in indices]
        except Exception as exc:
            return {"passed": False, "reasons": [f"video_frame_read_failed:{type(exc).__name__}"]}
    finally:
        try:
            reader.close()
        except Exception:
            pass

    results = []
    tmp = path + ".gateframe.jpg"
    try:
        for k, fr in enumerate(picks):
            Image.fromarray(fr).save(tmp, quality=90)
            m = dict(meta or {}, path=tmp, requires_jar=bool((meta or {}).get("jar_box")))
            if k < len(picks) - 1:  # entry frames: background depth only; final frame gets full + vision
                m = {"path": tmp, "requires_jar": False}
                r, met = heuristic_checks(Image.open(tmp), m)
                results.append({"passed": not r, "reasons": r, "metrics": met})
            else:
                results.append(evaluate(m, recent_layouts, vision=vision))
    finally:
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
