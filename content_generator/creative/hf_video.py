"""Hugging Face background clips: LTX-Video, then Wan.

Uses the free inference endpoint and, if that does not return a video, the
matching Space. Timeouts, quota and busy responses are logged and skipped.
A missing HF_TOKEN skips both models. Nothing here draws a jar.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

LTX_MODEL = os.getenv("HF_LTX_MODEL", "Lightricks/LTX-Video")
WAN_MODEL = os.getenv("HF_WAN_MODEL", "Wan-AI/Wan2.1-T2V-1.3B")
LTX_SPACE = os.getenv("HF_LTX_SPACE", "Lightricks/LTX-Video")
WAN_SPACE = os.getenv("HF_WAN_SPACE", "Wan-AI/Wan2.1")
NEGATIVE = "jar, bottle, packaging, label, text, logo, watermark, brand, people, hands"

_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_AUTH_DEAD = False


def reset_session() -> None:
    global _AUTH_DEAD
    _AUTH_DEAD = False


def _timeout() -> float:
    try:
        return max(5.0, float(os.getenv("HF_BG_TIMEOUT_S", "90")))
    except ValueError:
        return 90.0


def _token() -> str:
    return os.getenv("HF_TOKEN", "").strip()


def interpret(status, body: bytes, content_type: str = "") -> tuple[str, str | None]:
    """Classify a provider response. Never includes the token."""
    if status == "timeout":
        return "timeout", None
    if status == "error":
        return "error", None
    raw = body or b""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype.startswith("video/") or (len(raw) > 12 and raw[4:8] == b"ftyp"):
        return "video", None
    text = raw.decode("utf-8", "replace")
    low = text.lower()
    if status in (401, 403) or "invalid username or password" in low or "invalid token" in low or "unauthorized" in low:
        return "auth", None
    if status in (429, 402) or "quota" in low or "rate limit" in low or "too many requests" in low:
        return "quota", None
    if status in (503, 504, 529) or "currently loading" in low or "estimated_time" in low or "overloaded" in low or "busy" in low:
        return "busy", None
    url = _find_video_url(text)
    if url:
        return "url", url
    return "error", None


def _find_video_url(text: str) -> str | None:
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = text
    return _walk_url(payload)


def _walk_url(obj) -> str | None:
    if isinstance(obj, str) and obj.startswith("http") and (".mp4" in obj or "video" in obj):
        return obj
    if isinstance(obj, dict):
        for key in ("video_url", "url", "output", "path"):
            if key in obj:
                found = _walk_url(obj[key])
                if found:
                    return found
        for value in obj.values():
            found = _walk_url(value)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = _walk_url(value)
            if found:
                return found
    return None


def _request(url: str, payload, headers: dict, timeout: float) -> tuple[object, bytes, str]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": "PurityBeansBackground/1.0", "Content-Type": "application/json", **headers},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except TimeoutError:
        return "timeout", b"", ""
    except Exception as exc:
        code = getattr(exc, "code", "error")
        body = b""
        reader = getattr(exc, "read", None)
        if callable(reader):
            try:
                body = reader() or b""
            except Exception:
                body = b""
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            return "timeout", b"", ""
        return code, body[:4000], ""


def _save(content: bytes, label: str, name: str) -> str | None:
    if not content or (len(content) < 32 or content[4:8] != b"ftyp"):
        return None
    os.makedirs(_OUT, exist_ok=True)
    dest = os.path.join(_OUT, f"{label}_{name}_bg.mp4")
    with open(dest, "wb") as handle:
        handle.write(content)
    return dest


def _download(url: str, label: str, name: str, timeout: float) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return _save(response.read(), label, name)
    except Exception as exc:
        logger.info("[hf_bg] download failed: %s", type(exc).__name__)
        return None


def _inference(model: str, prompt: str, token: str, timeout: float):
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "video/mp4"}
    body = {"inputs": prompt, "parameters": {"negative_prompt": NEGATIVE, "num_frames": 25}}
    return _request(url, body, headers, timeout)


def _space_host(space_id: str) -> str:
    owner, _, name = space_id.partition("/")
    slug = f"{owner}-{name}".replace("_", "-").lower()
    return f"https://{slug}.hf.space"


def _space(space_id: str, prompt: str, token: str, timeout: float):
    host = _space_host(space_id)
    headers = {"Authorization": f"Bearer {token}"}
    status, body, ctype = _request(
        f"{host}/gradio_api/call/generate",
        {"data": [prompt, NEGATIVE]},
        headers,
        min(timeout, 30),
    )
    kind, extra = interpret(status, body, ctype)
    if kind in {"video", "url", "auth", "quota", "timeout"}:
        return status, body, ctype
    event_id = ""
    try:
        event_id = json.loads(body.decode() or "{}").get("event_id") or ""
    except (ValueError, AttributeError):
        event_id = ""
    if not event_id:
        return status, body, ctype
    deadline = time.monotonic() + max(1.0, timeout - 5)
    status, body, ctype = _request(
        f"{host}/gradio_api/call/generate/{event_id}", None, headers, max(1.0, deadline - time.monotonic()),
    )
    return status, body, ctype


def _consume(kind: str, extra: str | None, body: bytes, label: str, name: str, timeout: float) -> str | None:
    if kind == "video":
        return _save(body, label, name)
    if kind == "url" and extra:
        return _download(extra, label, name, timeout)
    return None


def _run(source: str, model: str, space: str, prompt: str, label: str, seconds: int) -> str | None:
    global _AUTH_DEAD
    token = _token()
    if not token:
        logger.info("[hf_bg] %s skipped (HF_TOKEN unset)", source)
        return None
    if _AUTH_DEAD:
        logger.info("[hf_bg] %s skipped (token rejected)", source)
        return None
    timeout = _timeout()
    try:
        status, body, ctype = _inference(model, prompt, token, timeout)
    except Exception as exc:
        logger.info("[hf_bg] %s inference failed: %s", source, type(exc).__name__)
        status, body, ctype = "error", b"", ""
    kind, extra = interpret(status, body, ctype)
    if kind == "auth":
        _AUTH_DEAD = True
        logger.info("[hf_bg] %s auth rejected — skipping huggingface", source)
        return None
    saved = _consume(kind, extra, body, label, source, timeout)
    if saved:
        logger.info("[hf_bg] %s inference clip for %s", source, label)
        return saved
    logger.info("[hf_bg] %s inference %s — trying space", source, kind)
    try:
        status, body, ctype = _space(space, prompt, token, timeout)
    except Exception as exc:
        logger.info("[hf_bg] %s space failed: %s", source, type(exc).__name__)
        return None
    kind, extra = interpret(status, body, ctype)
    if kind == "auth":
        _AUTH_DEAD = True
        logger.info("[hf_bg] %s space auth rejected", source)
        return None
    if kind in {"quota", "busy", "timeout"}:
        logger.info("[hf_bg] %s space %s — skipping", source, kind)
        return None
    saved = _consume(kind, extra, body, label, source, timeout)
    if not saved:
        logger.info("[hf_bg] %s space %s — skipping", source, kind)
    return saved


def ltx(choice: dict, label: str, seconds: int = 5) -> str | None:
    prompt = (choice or {}).get("ai_prompt") or ""
    return _run("hf_ltx", LTX_MODEL, LTX_SPACE, prompt, label, seconds)


def wan(choice: dict, label: str, seconds: int = 5) -> str | None:
    prompt = (choice or {}).get("ai_prompt") or ""
    return _run("hf_wan", WAN_MODEL, WAN_SPACE, prompt, label, seconds)
