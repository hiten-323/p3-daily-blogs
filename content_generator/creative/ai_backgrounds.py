"""Fresh AI background clips per day for Shorts/Reels (background ONLY).

Provider order: Pixazo (when PIXAZO_API_KEY is set), then Runway (existing
runway_generator, when RUNWAY_API_KEY is set). Every prompt comes from the
concept library and forbids jars/packaging/text/logos: the official jar
cutout is always composited on top by cinematic_motion, never generated.

Returns a list of RGB numpy frames at (BH, BW) or None, so the caller falls
back to the per-concept procedural renderer. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))


def enabled() -> bool:
    return os.getenv("AI_VIDEO_BG", "1") != "0" and bool(os.getenv("PIXAZO_API_KEY") or os.getenv("RUNWAY_API_KEY"))


def _http_json(url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (provider URL from env/config)
        return json.loads(r.read().decode() or "{}")


def _find_url(obj):
    if isinstance(obj, str) and obj.startswith("http") and (".mp4" in obj or "video" in obj):
        return obj
    if isinstance(obj, dict):
        for k in ("video_url", "output_url", "url", "output", "result", "data", "video"):
            if k in obj:
                u = _find_url(obj[k])
                if u:
                    return u
        for v in obj.values():
            u = _find_url(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _find_url(v)
            if u:
                return u
    return None


def _pixazo(prompt: str, label: str, seconds: int) -> str | None:
    key = os.getenv("PIXAZO_API_KEY")
    if not key:
        return None
    url = os.getenv("PIXAZO_VIDEO_URL", "https://gateway.pixazo.ai/ltx-video/v1/generate")
    hdr = {"Ocp-Apim-Subscription-Key": key, "Authorization": f"Bearer {key}"}
    try:
        res = _http_json(url, {"prompt": prompt, "duration": seconds, "aspect_ratio": "9:16",
                               "negative_prompt": "jar, bottle, packaging, label, text, logo, watermark, people"},
                         hdr, timeout=120)
        vid = _find_url(res)
        poll = res.get("status_url") or res.get("polling_url") if isinstance(res, dict) else None
        deadline = time.monotonic() + float(os.getenv("AI_BG_TIMEOUT_S", "240"))
        while not vid and poll and time.monotonic() < deadline:
            time.sleep(6)
            res = _http_json(poll, None, hdr)
            vid = _find_url(res)
        if not vid:
            logger.info("[ai_bg] pixazo returned no video url")
            return None
        os.makedirs(_OUT, exist_ok=True)
        out = os.path.join(_OUT, f"{label}_pixazo_bg.mp4")
        urllib.request.urlretrieve(vid, out)  # noqa: S310
        return out
    except Exception as exc:
        logger.info("[ai_bg] pixazo failed: %s", type(exc).__name__)
        return None


def _runway(prompt: str, label: str, seconds: int) -> str | None:
    try:
        from content_generator.creative import runway_generator as rg
        if not rg.is_configured():
            return None
        return rg.generate_video(prompt, duration_seconds=5 if seconds <= 5 else 10, label=f"{label}_runway_bg")
    except Exception as exc:
        logger.info("[ai_bg] runway failed: %s", type(exc).__name__)
        return None


def load_frames(path: str, size, max_frames: int = 240):
    """Decode, centre-crop to 9:16 and resize to `size` (w, h). Returns list of uint8 arrays."""
    import numpy as np
    import imageio.v2 as imageio
    from PIL import Image
    w, h = size
    out = []
    r = imageio.get_reader(path, format="FFMPEG")
    try:
        for i, fr in enumerate(r):
            if i >= max_frames:
                break
            im = Image.fromarray(fr)
            sw, sh = im.size
            tw = min(sw, int(sh * w / h))
            th = min(sh, int(sw * h / w))
            im = im.crop(((sw - tw) // 2, (sh - th) // 2, (sw - tw) // 2 + tw, (sh - th) // 2 + th)).resize((w, h))
            out.append(np.asarray(im.convert("RGB")))
    finally:
        r.close()
    return out if len(out) >= 24 else None


def fetch_background(choice: dict, label: str, size, seconds: float = 5) -> tuple[list | None, str]:
    """Try providers for this concept's prompt. Returns (frames|None, source)."""
    if not enabled():
        return None, "procedural"
    prompt = choice.get("ai_prompt") or ""
    for name, fn in (("pixazo", _pixazo), ("runway", _runway)):
        path = fn(prompt, label, int(min(10, max(5, seconds))))
        if path and os.path.exists(path):
            try:
                frames = load_frames(path, size)
                if frames:
                    logger.info("[ai_bg] %s background for %s (%d frames)", name, choice.get("concept"), len(frames))
                    return frames, name
            except Exception as exc:
                logger.info("[ai_bg] %s clip unreadable: %s", name, type(exc).__name__)
    return None, "procedural"
