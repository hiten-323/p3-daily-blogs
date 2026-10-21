"""Pexels and Pixabay coffee footage for the daily concept background.

Search is limited to the day's concept (steam, pour, beans, crema, cafe,
rain window). Vertical HD is preferred. Clip ids used in the last 30 days
are stored under output/learning and skipped. Metadata, and a frame when it
is readable, reject other brands' logos, packaging and text.

The file returned is a background plate only. cinematic_motion composites
the official jar cutout on top. This module never fetches or draws a jar.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

WINDOW_DAYS = int(os.getenv("STOCK_CLIP_WINDOW_DAYS", "30"))
_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_RESERVED: set[str] = set()

QUERIES = {
    "steam": "coffee steam",
    "pour": "coffee pour",
    "beans": "coffee beans",
    "crema": "coffee crema",
    "cafe": "coffee cafe",
    "rain_window": "rain window cafe",
}

CONCEPT_QUERY = {
    "granule_dissolve": "pour",
    "steam_backlight": "steam",
    "crema_swirl": "crema",
    "golden_hour_kitchen": "cafe",
    "rain_window_cafe": "rain_window",
    "marble_spotlight": "beans",
    "bean_cascade": "beans",
    "ink_in_water": "pour",
    "night_city_bokeh": "cafe",
    "sunrise_window": "cafe",
    "light_tunnel": "steam",
    "monsoon_chai_time": "rain_window",
    "velvet_orbit": "beans",
    "ember_glow": "beans",
}

_BRAND = re.compile(
    r"\b(?:logos?|packaging|packages?|labels?|watermark|subtitles?|captions?|branded|"
    r"jars?|bottles?|nescafe|nescaf[eé]|starbucks|dunkin|lavazza|nespresso|nestl[eé]|"
    r"illy|folgers|maxwell|davidoff|tim\s*hortons|peet'?s|costa\s+coffee|"
    r"text\s+overlay|product\s+shot)\b",
    re.I,
)


def reset_session() -> None:
    _RESERVED.clear()


def history_path() -> str:
    return os.getenv("STOCK_CLIP_HISTORY", os.path.join("output", "learning", "stock_clip_history.json"))


def query_for(concept: str | None, scene: str | None = None) -> str:
    key = CONCEPT_QUERY.get(concept or "", "")
    if not key and scene:
        for name in QUERIES:
            if name in (scene or ""):
                key = name
                break
    return QUERIES.get(key or "", QUERIES["cafe"])


def _safe(exc: BaseException, secrets: list[str]) -> str:
    text = f"{type(exc).__name__}"
    for secret in secrets:
        if secret and secret in str(exc):
            text = "redacted"
            break
    return text


def _strip_secrets(url: str, secrets: list[str] | None = None) -> str:
    """Remove known secret values from a URL without dropping unrelated query keys."""
    cleaned = url or ""
    parts = urllib.parse.urlsplit(cleaned)
    query = []
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if any(secret and (secret == value or secret in value) for secret in (secrets or [])):
            continue
        query.append((key, value))
    cleaned = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))
    for secret in secrets or []:
        if secret:
            cleaned = cleaned.replace(secret, "")
    return cleaned


def _strings(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _strings(value, out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _strings(value, out)


def clip_branded(meta: dict) -> bool:
    """True when titles, tags or page text advertise a logo, package or other brand."""
    parts: list[str] = []
    _strings(meta, parts)
    return bool(_BRAND.search(" ".join(parts)))


def frame_has_overlay_text(frame) -> bool:
    """Detect a band of glyph-like strokes. Smooth footage returns False.

    Only used when a frame is readable. A failure to decode is not a rejection.
    """
    import numpy as np
    img = np.asarray(frame)
    if img.ndim != 3 or img.shape[0] < 24 or img.shape[1] < 24:
        return False
    gray = img.mean(axis=2)
    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
    frac = (gx > 45).mean(axis=1)
    glyph = (frac > 0.08) & (frac < 0.42)
    best = run = 0
    for flag in glyph:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best >= 4


def _score(width: int, height: int) -> tuple[int, int, int] | None:
    if width < 64 or height < 64 or max(width, height) < 640:
        return None
    vertical = 1 if height >= int(width * 1.05) else 0
    hd = 1 if height >= 720 or width >= 1280 else 0
    return (vertical, hd, width * height)


def best_pexels_file(video: dict) -> dict | None:
    best = None
    best_score = None
    for item in video.get("video_files") or []:
        link = item.get("link") or item.get("url")
        score = _score(int(item.get("width") or 0), int(item.get("height") or 0))
        if not link or score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best = {"link": link, "width": int(item["width"]), "height": int(item["height"]), "_score": score}
    return best


def best_pixabay_file(hit: dict) -> dict | None:
    best = None
    best_score = None
    for item in (hit.get("videos") or {}).values():
        if not isinstance(item, dict):
            continue
        link = item.get("url") or item.get("link")
        score = _score(int(item.get("width") or 0), int(item.get("height") or 0))
        if not link or score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best = {"link": link, "width": int(item["width"]), "height": int(item["height"]), "_score": score}
    return best


def rank_stock_clips(provider: str, payload: dict, used_ids: set[str]) -> list[tuple[dict, dict]]:
    rows = payload.get("videos") if provider == "pexels" else payload.get("hits") or []
    ranked = []
    for video in rows or []:
        if not isinstance(video, dict) or clip_branded(video):
            continue
        clip_id = f"{provider}:{video.get('id')}"
        if clip_id in used_ids:
            continue
        picked = best_pexels_file(video) if provider == "pexels" else best_pixabay_file(video)
        if picked:
            ranked.append((picked["_score"], video, picked))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(video, picked) for _, video, picked in ranked]


def load_history(path: str | None = None) -> list[dict]:
    try:
        with open(path or history_path(), encoding="utf-8") as handle:
            rows = json.load(handle)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def save_history(rows: list[dict], path: str | None = None) -> None:
    dest = path or history_path()
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(rows[-400:], handle, indent=1)


def recent_ids(on_date: str | None, path: str | None = None, days: int | None = None) -> set[str]:
    import datetime as dt
    window = WINDOW_DAYS if days is None else days
    try:
        today = dt.date.fromisoformat(str(on_date)[:10]) if on_date else dt.date.today()
    except ValueError:
        today = dt.date.today()
    found = set()
    for row in load_history(path):
        try:
            seen = dt.date.fromisoformat(str(row.get("date"))[:10])
        except (TypeError, ValueError):
            continue
        age = (today - seen).days
        if 0 <= age < window and row.get("id"):
            found.add(str(row["id"]))
    return found


def remember(pending: dict, path: str | None = None) -> None:
    if not pending or not pending.get("id"):
        return
    rows = [row for row in load_history(path) if row.get("id") != pending.get("id") or row.get("date") != pending.get("date")]
    rows.append({
        "id": pending.get("id"),
        "source": pending.get("source"),
        "date": pending.get("date"),
        "format": pending.get("format"),
        "concept": pending.get("concept"),
        "attribution": pending.get("attribution") or {},
    })
    save_history(rows, path)
    _RESERVED.add(str(pending["id"]))


def release(clip_id: str) -> None:
    _RESERVED.discard(str(clip_id or ""))


def _attribution(provider: str, video: dict) -> dict:
    if provider == "pexels":
        user = video.get("user") or {}
        return {
            "provider": "pexels",
            "clip_id": str(video.get("id")),
            "page_url": video.get("url"),
            "author": user.get("name"),
            "author_url": user.get("url"),
            "license": "Pexels License",
        }
    user = video.get("user")
    user_id = video.get("user_id")
    return {
        "provider": "pixabay",
        "clip_id": str(video.get("id")),
        "page_url": video.get("pageURL"),
        "author": user,
        "author_url": f"https://pixabay.com/users/{user}-{user_id}/" if user and user_id else None,
        "license": "Pixabay License",
    }


def _open(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310


def _search(provider: str, key: str, query: str) -> dict:
    if provider == "pexels":
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({
            "query": query, "orientation": "portrait", "size": "large", "per_page": "15",
        })
        req = urllib.request.Request(url, headers={"Authorization": key})
        with _open(req, 20) as response:
            payload = json.loads(response.read().decode() or "{}")
        if payload.get("videos"):
            return payload
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({
            "query": query, "size": "large", "per_page": "15",
        })
        req = urllib.request.Request(url, headers={"Authorization": key})
        with _open(req, 20) as response:
            return json.loads(response.read().decode() or "{}")
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({
        "key": key, "q": query, "per_page": "15", "safesearch": "true", "video_type": "film",
    })
    req = urllib.request.Request(url)
    with _open(req, 20) as response:
        return json.loads(response.read().decode() or "{}")


def _download(url: str, dest: str, secrets: list[str]) -> bool:
    clean = _strip_secrets(url, secrets)
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        urllib.request.urlretrieve(clean, dest)  # noqa: S310
    except Exception as exc:
        logger.info("[stock] download failed: %s", _safe(exc, secrets))
        return False
    return os.path.isfile(dest) and os.path.getsize(dest) > 1000


def _overlay_detectable(path: str) -> bool:
    try:
        import imageio.v2 as imageio
        reader = imageio.get_reader(path, format="FFMPEG")
        try:
            frame = reader.get_data(0)
        finally:
            reader.close()
    except Exception:
        return False
    return frame_has_overlay_text(frame)


def _result(provider: str, choice: dict, video: dict, path: str) -> dict:
    clip_id = f"{provider}:{video.get('id')}"
    _RESERVED.add(clip_id)
    return {
        "path": path,
        "id": clip_id,
        "source": provider,
        "date": choice.get("date"),
        "format": choice.get("format"),
        "concept": choice.get("concept"),
        "attribution": _attribution(provider, video),
    }


def _fetch(provider: str, key: str, choice: dict, label: str) -> dict | None:
    query = query_for(choice.get("concept"), choice.get("scene"))
    try:
        payload = _search(provider, key, query)
    except Exception as exc:
        logger.info("[stock] %s search failed: %s", provider, _safe(exc, [key]))
        return None
    used = recent_ids(choice.get("date")) | set(_RESERVED)
    for video, picked in rank_stock_clips(provider, payload, used):
        dest = os.path.join(_OUT, f"{label}_{provider}_bg.mp4")
        link = _strip_secrets(picked["link"], [key])
        if not _download(link, dest, [key]):
            continue
        if _overlay_detectable(dest):
            logger.info("[stock] %s clip rejected (overlay text)", provider)
            try:
                os.remove(dest)
            except OSError:
                pass
            continue
        logger.info("[stock] %s %s for %s", provider, query, choice.get("concept"))
        return _result(provider, choice, video, dest)
    logger.info("[stock] %s had no usable clip for %s", provider, query)
    return None


def pexels(choice: dict, label: str, seconds: int = 5) -> dict | None:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        logger.info("[stock] pexels skipped (PEXELS_API_KEY unset)")
        return None
    return _fetch("pexels", key, choice, label)


def pixabay(choice: dict, label: str, seconds: int = 5) -> dict | None:
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        logger.info("[stock] pixabay skipped (PIXABAY_API_KEY unset)")
        return None
    return _fetch("pixabay", key, choice, label)
