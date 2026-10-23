"""Background plates for Shorts and Reels. The official jar is never generated.

Provider order: Kaggle clip bank, Hugging Face LTX-Video, Hugging Face Wan,
Pixazo, Runway, Pexels, Pixabay, then the coded concept renderer. A missing
secret skips that source. The Short and the Reel on the same day use different
sources when another configured source can supply a plate.

Every prompt comes from the concept library and forbids jars, packaging, text
and logos. cinematic_motion composites the real jar cutout on top and the
existing motion, variety and 8.0 gates still score the finished video.

Returns RGB frames at (BH, BW) or None so the caller falls back to the
procedural renderer. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))


PROVIDER_ORDER = (
    "kaggle_bank", "hf_ltx", "hf_wan", "pixazo", "runway", "pexels", "pixabay",
)

_SESSION: dict[tuple[str, str], str] = {}
_REJECTED: dict[tuple[str, str], set[str]] = {}
_PENDING: dict | None = None


def _attribution_path() -> str:
    return os.getenv("BACKGROUND_ATTRIBUTION", os.path.join("output", "learning", "background_attribution.json"))


def reset_session() -> None:
    global _PENDING
    _SESSION.clear()
    _REJECTED.clear()
    _PENDING = None
    from content_generator.creative import hf_video, kaggle_bank, stock_video
    hf_video.reset_session()
    kaggle_bank.reset_session()
    stock_video.reset_session()


def enabled() -> bool:
    return os.getenv("AI_VIDEO_BG", "1") != "0"


def _configured(name: str) -> bool:
    from content_generator.creative import kaggle_bank
    if name == "kaggle_bank":
        return kaggle_bank.available()
    env = {
        "hf_ltx": "HF_TOKEN", "hf_wan": "HF_TOKEN", "pixazo": "PIXAZO_API_KEY",
        "runway": "RUNWAY_API_KEY", "pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY",
    }.get(name)
    return bool(env and os.getenv(env, "").strip())


def _sibling_source(choice: dict) -> str | None:
    date, fmt = choice.get("date"), choice.get("format")
    if not date or not fmt:
        return None
    other = "reel" if fmt == "short" else "short"
    if (date, other) in _SESSION:
        return _SESSION[(date, other)]
    try:
        from content_generator.creative import shorts_concepts as scn
        for row in scn.load_history():
            if row.get("date") == date and row.get("format") == other and row.get("bg_source") not in (None, "", "procedural"):
                return row.get("bg_source")
    except Exception:
        return None
    return None


def _order(avoid: str | None) -> list[str]:
    names = list(PROVIDER_ORDER)
    if avoid and avoid in names and any(_configured(name) and name != avoid for name in names):
        names = [name for name in names if name != avoid] + [avoid]
    return names


def _http_json(url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": "PurityBeansBackground/1.0", "Content-Type": "application/json", **(headers or {})},
        method="POST" if data else "GET",
    )
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


# Documented text-to-video route. ltx-video/v1/generate returns 404.
# https://www.pixazo.ai/models/ltx — LTX 2.5 Lite, then poll v2/requests/status.
PIXAZO_TEXT_TO_VIDEO = "https://gateway.pixazo.ai/ltx-2-5-lite/v1/text-to-video"
_PIXAZO_DURATIONS = (6, 8, 10, 12, 14, 16, 18, 20)


def _pixazo_duration(seconds: int) -> int:
    """Lite and Pro accept only these lengths. Shorter asks use the 6 second floor."""
    for value in _PIXAZO_DURATIONS:
        if int(seconds or 0) <= value:
            return value
    return _PIXAZO_DURATIONS[0]


def _pixazo(prompt: str, label: str, seconds: int) -> str | None:
    key = os.getenv("PIXAZO_API_KEY")
    if not key:
        return None
    url = os.getenv("PIXAZO_VIDEO_URL", PIXAZO_TEXT_TO_VIDEO)
    hdr = {"Ocp-Apim-Subscription-Key": key, "Authorization": f"Bearer {key}"}
    body = {
        "prompt": prompt,
        "resolution": "720p",
        "duration": _pixazo_duration(seconds),
        "aspect_ratio": "9:16",
        "generate_audio": False,
    }
    try:
        res = _http_json(url, body, hdr, timeout=60)
        vid = _find_url(res)
        poll = ""
        if isinstance(res, dict):
            poll = res.get("polling_url") or ""
            request_id = res.get("request_id") or ""
            if not poll and request_id:
                poll = f"https://gateway.pixazo.ai/v2/requests/status/{request_id}"
            if str(res.get("status") or "").upper() == "ERROR":
                logger.info("[ai_bg] pixazo status error")
                return None
        deadline = time.monotonic() + float(os.getenv("AI_BG_TIMEOUT_S", "240"))
        while not vid and poll and time.monotonic() < deadline:
            time.sleep(6)
            res = _http_json(poll, None, hdr)
            if isinstance(res, dict) and str(res.get("status") or "").upper() == "ERROR":
                logger.info("[ai_bg] pixazo status error")
                return None
            vid = _find_url(res)
        if not vid:
            logger.info("[ai_bg] pixazo returned no video url")
            return None
        os.makedirs(_OUT, exist_ok=True)
        out = os.path.join(_OUT, f"{label}_pixazo_bg.mp4")
        req = urllib.request.Request(vid, headers={"User-Agent": "PurityBeansBackground/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            data = response.read()
        if len(data) < 1000:
            return None
        with open(out, "wb") as handle:
            handle.write(data)
        return out
    except Exception as exc:
        logger.info("[ai_bg] pixazo failed: %s", getattr(exc, "code", None) or type(exc).__name__)
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


def _providers() -> dict:
    from content_generator.creative import hf_video, kaggle_bank, stock_video
    return {
        "kaggle_bank": kaggle_bank.take,
        "hf_ltx": hf_video.ltx,
        "hf_wan": hf_video.wan,
        "pixazo": lambda choice, label, seconds: _pixazo(choice.get("ai_prompt") or "", label, seconds),
        "runway": lambda choice, label, seconds: _runway(choice.get("ai_prompt") or "", label, seconds),
        "pexels": stock_video.pexels,
        "pixabay": stock_video.pixabay,
    }


def _as_pending(name: str, result, choice: dict) -> dict | None:
    if not result:
        return None
    if isinstance(result, str):
        pending = {"path": result, "id": "", "source": name, "attribution": {"provider": name}}
    elif isinstance(result, dict) and result.get("path"):
        pending = dict(result)
        pending["source"] = name
    else:
        return None
    pending.setdefault("date", choice.get("date"))
    pending.setdefault("format", choice.get("format"))
    pending.setdefault("concept", choice.get("concept"))
    return pending


def commit_usage() -> None:
    """Record the plate that passed the motion and variety gates. Never raises."""
    global _PENDING
    pending = _PENDING
    _PENDING = None
    if not pending:
        return
    try:
        from content_generator.creative import kaggle_bank, stock_video
        if pending.get("source") in {"pexels", "pixabay"} and pending.get("id"):
            stock_video.remember(pending)
        elif pending.get("source") == "kaggle_bank" and pending.get("id"):
            kaggle_bank.remember(pending)
        _append_attribution(pending)
    except Exception as exc:
        logger.info("[ai_bg] usage record failed: %s", type(exc).__name__)


def _append_attribution(pending: dict) -> None:
    dest = _attribution_path()
    try:
        with open(dest, encoding="utf-8") as handle:
            rows = json.load(handle)
        if not isinstance(rows, list):
            rows = []
    except Exception:
        rows = []
    rows.append({
        "date": pending.get("date"),
        "format": pending.get("format"),
        "concept": pending.get("concept"),
        "source": pending.get("source"),
        "clip_id": pending.get("id"),
        "attribution": pending.get("attribution") or {},
    })
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(rows[-400:], handle, indent=1)


def _release(pending: dict | None) -> None:
    if not pending or not pending.get("id"):
        return
    from content_generator.creative import kaggle_bank, stock_video
    if pending.get("source") in {"pexels", "pixabay"}:
        stock_video.release(pending["id"])
    elif pending.get("source") == "kaggle_bank":
        kaggle_bank.release(pending["id"])


def reject_source(choice: dict, source: str) -> None:
    """A plate that failed the visual gate must not be the next try's first choice."""
    global _PENDING
    name = str(source or "")
    if not name or name == "procedural":
        return
    key = (str(choice.get("date") or ""), str(choice.get("format") or ""))
    _REJECTED.setdefault(key, set()).add(name)
    if _SESSION.get(key) == name:
        del _SESSION[key]
    if _PENDING and str(_PENDING.get("source") or name) == name:
        _release(_PENDING)
        _PENDING = None


def fetch_background(choice: dict, label: str, size, seconds: float = 5) -> tuple[list | None, str]:
    """Try providers for this concept. Returns (frames|None, source)."""
    global _PENDING
    _PENDING = None
    if not enabled():
        return None, "procedural"
    duration = int(min(10, max(5, seconds)))
    avoid = _sibling_source(choice)
    providers = _providers()
    rejected = _REJECTED.get((str(choice.get("date") or ""), str(choice.get("format") or "")), set())
    for name in _order(avoid):
        if name in rejected:
            logger.info("[ai_bg] %s skipped (plate failed the visual gate)", name)
            continue
        if not _configured(name):
            logger.info("[ai_bg] %s skipped (not configured)", name)
            continue
        try:
            pending = _as_pending(name, providers[name](choice, label, duration), choice)
        except Exception as exc:
            logger.info("[ai_bg] %s failed: %s", name, type(exc).__name__)
            continue
        if not pending or not os.path.exists(pending["path"]):
            continue
        try:
            frames = load_frames(pending["path"], size)
        except Exception as exc:
            logger.info("[ai_bg] %s clip unreadable: %s", name, type(exc).__name__)
            _release(pending)
            continue
        if not frames:
            _release(pending)
            continue
        _PENDING = pending
        if choice.get("date") and choice.get("format"):
            _SESSION[(choice["date"], choice["format"])] = name
        logger.info("[ai_bg] %s background for %s (%d frames)", name, choice.get("concept"), len(frames))
        return frames, name
    return None, "procedural"
