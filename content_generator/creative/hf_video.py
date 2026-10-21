"""Hugging Face background clips: LTX-Video, then Wan.

The free hf-inference router does not serve these video models. LTX uses the
running ZeroGPU Space Lightricks/ltx-video-distilled (Gradio `/text_to_video`).
Wan uses Wan-AI/Wan2.1 (`/t2v_generation_async`). If a Space does not return a
video, the same prompt is sent through the Hugging Face router to the fal-ai
provider mapped on the model card. Timeouts, quota and busy responses are
logged and skipped. A missing HF_TOKEN skips both models. Nothing here draws
a jar.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

LTX_MODEL = os.getenv("HF_LTX_MODEL", "Lightricks/LTX-Video-0.9.7-distilled")
WAN_MODEL = os.getenv("HF_WAN_MODEL", "Wan-AI/Wan2.1-T2V-1.3B")
LTX_SPACE = os.getenv("HF_LTX_SPACE", "Lightricks/ltx-video-distilled")
WAN_SPACE = os.getenv("HF_WAN_SPACE", "Wan-AI/Wan2.1")
# Hub inferenceProviderMapping provider ids. The router path is
# https://router.huggingface.co/{provider}/{providerId}
LTX_ROUTER = ("fal-ai", "fal-ai/ltx-video-13b-distilled")
WAN_ROUTER = ("fal-ai", "fal-ai/wan/v2.1/1.3b/text-to-video")
NEGATIVE = "jar, bottle, packaging, label, text, logo, watermark, brand, people, hands"
USER_AGENT = "PurityBeansBackground/1.0"

_OUT = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_AUTH_DEAD = False


def reset_session() -> None:
    global _AUTH_DEAD
    _AUTH_DEAD = False


def _timeout() -> float:
    try:
        return max(5.0, float(os.getenv("HF_BG_TIMEOUT_S", "180")))
    except ValueError:
        return 180.0


def _token() -> str:
    return os.getenv("HF_TOKEN", "").strip()


def _space_host(space_id: str) -> str:
    owner, _, name = space_id.partition("/")
    slug = f"{owner}-{name}".replace("_", "-").lower()
    return f"https://{slug}.hf.space"


def space_call(space_id: str, prompt: str) -> tuple[str, list]:
    """Gradio api name and data list for a Space. No network."""
    if "wan" in (space_id or "").lower():
        # Wan-AI/Wan2.1 exposes t2v_generation_async(prompt, resolution, watermark, seed).
        return "t2v_generation_async", [prompt, "720*1280", False, -1]
    # Lightricks/ltx-video-distilled generate() / api_name text_to_video.
    # Mode must be explicit: the UI default is image-to-video.
    return "text_to_video", [
        prompt, NEGATIVE, None, None, 512, 704, "text-to-video",
        2, 9, 42, True, 3, False,
    ]


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
    media = _media_url(text)
    if media and status not in (401, 403, 402, 429):
        return "url", media
    if status in (401, 403) or "invalid username or password" in low or "invalid token" in low or "unauthorized" in low:
        return "auth", None
    if status in (429, 402) or "quota" in low or "rate limit" in low or "too many requests" in low or "payment required" in low:
        return "quota", None
    if status in (503, 504, 529) or "currently loading" in low or "estimated_time" in low or "overloaded" in low or "busy" in low:
        return "busy", None
    if "in_queue" in low or "in_progress" in low:
        return "busy", None
    return "error", None


def _media_url(text: str) -> str | None:
    """Pull an http(s) video URL out of JSON or a Gradio SSE stream."""
    if "event:" in text[:80] or "\ndata:" in text[:200]:
        for payload in _sse_payloads(text):
            found = _walk_url(payload)
            if found:
                return found
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = text
    return _walk_url(payload)


def _sse_payloads(text: str) -> list:
    found = []
    for block in text.split("\n\n"):
        data_lines = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        try:
            found.append(json.loads(raw))
        except ValueError:
            found.append(raw)
    return found


def _walk_url(obj) -> str | None:
    if isinstance(obj, str) and obj.startswith("http") and (".mp4" in obj or "video" in obj or "file=" in obj):
        return obj
    if isinstance(obj, dict):
        for key in ("video_url", "media_url", "url", "output", "path"):
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
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers},
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


def _download(url: str, label: str, name: str, timeout: float, headers: dict | None = None) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return _save(response.read(), label, name)
    except Exception as exc:
        logger.info("[hf_bg] download failed: %s", type(exc).__name__)
        return None


def _router_url(provider: str, provider_id: str) -> str:
    return f"https://router.huggingface.co/{provider}/{provider_id}?_subdomain=queue"


def _inference(target: tuple[str, str], prompt: str, token: str, timeout: float):
    """POST the fal-ai (or other) provider route and poll while it stays queued."""
    provider, provider_id = target
    headers = {"Authorization": f"Bearer {token}", "Accept": "video/mp4, application/json"}
    body = {"inputs": prompt, "parameters": {"negative_prompt": [NEGATIVE]}}
    status, raw, ctype = _request(_router_url(provider, provider_id), body, headers, min(timeout, 60))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        kind, _extra = interpret(status, raw, ctype)
        if kind != "busy":
            return status, raw, ctype
        status_url = _status_url(raw)
        if not status_url:
            return status, raw, ctype
        time.sleep(3)
        status, raw, ctype = _request(status_url, None, headers, 30)
    return "timeout", b"", ""


def _status_url(raw: bytes) -> str | None:
    try:
        payload = json.loads(raw.decode() or "{}")
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("status_url", "response_url"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("https://"):
            return value
    return None


def _space(space_id: str, prompt: str, token: str, timeout: float):
    host = _space_host(space_id)
    api_name, data = space_call(space_id, prompt)
    headers = {"Authorization": f"Bearer {token}"}
    status, body, ctype = _request(
        f"{host}/gradio_api/call/{api_name}",
        {"data": data},
        headers,
        min(timeout, 30),
    )
    kind, _extra = interpret(status, body, ctype)
    if kind in {"video", "url", "auth", "quota", "timeout"}:
        return status, body, ctype
    event_id = ""
    try:
        event_id = json.loads(body.decode() or "{}").get("event_id") or ""
    except (ValueError, AttributeError):
        event_id = ""
    if not event_id:
        return status, body, ctype
    status, body, ctype = _request(
        f"{host}/gradio_api/call/{api_name}/{event_id}",
        None,
        headers,
        timeout,
    )
    return status, body, ctype


def _consume(kind: str, extra: str | None, body: bytes, label: str, name: str, timeout: float, headers: dict | None = None) -> str | None:
    if kind == "video":
        return _save(body, label, name)
    if kind == "url" and extra:
        return _download(extra, label, name, timeout, headers)
    return None


def _run(source: str, space: str, router: tuple[str, str], prompt: str, label: str) -> str | None:
    global _AUTH_DEAD
    token = _token()
    if not token:
        logger.info("[hf_bg] %s skipped (HF_TOKEN unset)", source)
        return None
    if _AUTH_DEAD:
        logger.info("[hf_bg] %s skipped (token rejected)", source)
        return None
    timeout = _timeout()
    auth_headers = {"Authorization": f"Bearer {token}"}
    try:
        status, body, ctype = _space(space, prompt, token, timeout)
    except Exception as exc:
        logger.info("[hf_bg] %s space failed: %s", source, type(exc).__name__)
        status, body, ctype = "error", b"", ""
    kind, extra = interpret(status, body, ctype)
    if kind == "auth":
        _AUTH_DEAD = True
        logger.info("[hf_bg] %s space auth rejected — skipping huggingface", source)
        return None
    saved = _consume(kind, extra, body, label, source, timeout, auth_headers)
    if saved:
        logger.info("[hf_bg] %s space clip for %s", source, label)
        return saved
    logger.info("[hf_bg] %s space %s — trying router", source, kind)
    try:
        status, body, ctype = _inference(router, prompt, token, timeout)
    except Exception as exc:
        logger.info("[hf_bg] %s router failed: %s", source, type(exc).__name__)
        return None
    kind, extra = interpret(status, body, ctype)
    if kind == "auth":
        _AUTH_DEAD = True
        logger.info("[hf_bg] %s router auth rejected", source)
        return None
    if kind in {"quota", "busy", "timeout"}:
        logger.info("[hf_bg] %s router %s — skipping", source, kind)
        return None
    saved = _consume(kind, extra, body, label, source, timeout, auth_headers)
    if not saved:
        logger.info("[hf_bg] %s router %s — skipping", source, kind)
    return saved


def ltx(choice: dict, label: str, seconds: int = 5) -> str | None:
    prompt = (choice or {}).get("ai_prompt") or ""
    return _run("hf_ltx", LTX_SPACE, LTX_ROUTER, prompt, label)


def wan(choice: dict, label: str, seconds: int = 5) -> str | None:
    prompt = (choice or {}).get("ai_prompt") or ""
    return _run("hf_wan", WAN_SPACE, WAN_ROUTER, prompt, label)
