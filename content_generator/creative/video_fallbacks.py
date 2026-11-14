"""Text-to-video and image-to-video fallbacks after the primary providers.

Order: CogVideoX-2B Space, HunyuanVideo on the Hugging Face router (fal-ai,
then wavespeed), then Wan 2.1 image-to-video on wavespeed. Each one is
skipped when HF_TOKEN is unset. Failures are obstacle lessons. The image
sent to image-to-video is a generated steam still, never a product photo.

These calls use the monthly Hugging Face inference allowance on HF_TOKEN.
They do not read any other secret.
"""
from __future__ import annotations

import base64
import logging
import os

logger = logging.getLogger(__name__)

COGVIDEO_SPACE = os.getenv("HF_COGVIDEO_SPACE", "zai-org/CogVideoX-2B-Space")
HUNYUAN_ROUTERS = (
    ("fal-ai", "tencent/HunyuanVideo"),
    ("wavespeed", "tencent/HunyuanVideo"),
)
WAN_I2V_ROUTER = ("wavespeed", "Wan-AI/Wan2.1-I2V-14B-480P")
SAFE_TAIL = (
    "no jar, no bottle, no packaging, no label, no logo, no text, "
    "no people, steam water and ambient light only, vertical 9:16"
)


def timeout_s() -> float:
    try:
        return max(5.0, float(os.getenv("VIDEO_FALLBACK_TIMEOUT_S", "60")))
    except ValueError:
        return 60.0


def safe_prompt(choice: dict | None) -> str:
    text = str((choice or {}).get("ai_prompt") or "steam rising from a cup of coffee").strip()
    if SAFE_TAIL not in text:
        text = f"{text}, {SAFE_TAIL}"
    return text[:1200]


def ambience_jpeg() -> bytes:
    """A small steam-colored still. It is not a photograph of a jar."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (64, 96), (28, 18, 14))
    draw = ImageDraw.Draw(image)
    for i, color in enumerate(((80, 60, 48), (140, 120, 100), (210, 200, 190))):
        draw.ellipse((18 - i * 2, 10 + i * 16, 46 + i * 2, 40 + i * 16), fill=color)
    import io
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def i2v_payload(prompt: str, image: bytes) -> dict:
    """Router body for image-to-video. The image is the ambience still."""
    from content_generator.creative.hf_video import NEGATIVE
    encoded = base64.b64encode(image).decode("ascii")
    return {
        "inputs": prompt,
        "parameters": {
            "negative_prompt": [NEGATIVE],
            "image": f"data:image/jpeg;base64,{encoded}",
        },
    }


def _token() -> str:
    from content_generator.creative import hf_video
    return hf_video._token()


def _lesson(choice: dict | None, name: str, kind: str) -> None:
    """Record a provider failure without the response body or the token."""
    label = "yt_short" if str((choice or {}).get("format") or "") == "short" else "growth_reel"
    reason = f"{name} {kind}"
    logger.info("[video_fallback] %s", reason)
    try:
        from content_generator.core.obstacle_lessons import platform_for, record
        record(
            platform_for(label), label, "video_fallback", "provider", reason,
            "This video provider failed. Use the next source. Do not generate a jar or a package.",
            fix="Skip this provider on timeout, quota, or an empty file. Keep AI video to steam, water, and ambience.",
        )
    except Exception:
        return


def _save_from(name: str, status, body: bytes, ctype: str, label: str, choice) -> str | None:
    from content_generator.creative import hf_video
    kind, extra = hf_video.interpret(status, body, ctype)
    if kind == "auth":
        hf_video._AUTH_DEAD = True
        _lesson(choice, name, "auth")
        return None
    if kind in {"quota", "busy", "timeout", "error"}:
        _lesson(choice, name, kind)
        return None
    saved = hf_video._consume(
        kind, extra, body, label, name, timeout_s(),
        {"Authorization": f"Bearer {_token()}"},
    )
    if not saved:
        _lesson(choice, name, kind or "empty")
    return saved


def cogvideo(choice: dict, label: str, seconds: int = 5) -> str | None:
    from content_generator.creative import hf_video
    if not _token():
        logger.info("[video_fallback] hf_cogvideo skipped (HF_TOKEN unset)")
        return None
    if hf_video._AUTH_DEAD:
        logger.info("[video_fallback] hf_cogvideo skipped (token rejected)")
        return None
    prompt = safe_prompt(choice)
    try:
        status, body, ctype = hf_video._space(COGVIDEO_SPACE, prompt, _token(), timeout_s())
    except Exception as exc:
        _lesson(choice, "hf_cogvideo", type(exc).__name__)
        return None
    return _save_from("hf_cogvideo", status, body, ctype, label, choice)


def hunyuan(choice: dict, label: str, seconds: int = 5) -> str | None:
    from content_generator.creative import hf_video
    if not _token():
        logger.info("[video_fallback] hf_hunyuan skipped (HF_TOKEN unset)")
        return None
    if hf_video._AUTH_DEAD:
        logger.info("[video_fallback] hf_hunyuan skipped (token rejected)")
        return None
    prompt = safe_prompt(choice)
    last = "empty"
    for router in HUNYUAN_ROUTERS:
        try:
            status, body, ctype = hf_video._inference(router, prompt, _token(), timeout_s())
        except Exception as exc:
            last = type(exc).__name__
            continue
        kind, extra = hf_video.interpret(status, body, ctype)
        if kind == "auth":
            hf_video._AUTH_DEAD = True
            _lesson(choice, "hf_hunyuan", "auth")
            return None
        if kind in {"quota", "busy", "timeout", "error"}:
            last = kind
            continue
        saved = hf_video._consume(
            kind, extra, body, label, "hf_hunyuan", timeout_s(),
            {"Authorization": f"Bearer {_token()}"},
        )
        if saved:
            return saved
        last = kind or "empty"
    _lesson(choice, "hf_hunyuan", last)
    return None


def wan_i2v(choice: dict, label: str, seconds: int = 5) -> str | None:
    """Image-to-video from an ambience still. Product photos are never the input."""
    from content_generator.creative import hf_video
    if not _token():
        logger.info("[video_fallback] hf_wan_i2v skipped (HF_TOKEN unset)")
        return None
    if hf_video._AUTH_DEAD:
        logger.info("[video_fallback] hf_wan_i2v skipped (token rejected)")
        return None
    still = ambience_jpeg()
    if still[:2] != b"\xff\xd8":
        _lesson(choice, "hf_wan_i2v", "error")
        return None
    payload = i2v_payload(safe_prompt(choice), still)
    provider, model_id = WAN_I2V_ROUTER
    url = hf_video._router_url(provider, model_id)
    headers = {"Authorization": f"Bearer {_token()}", "Accept": "video/mp4, application/json"}
    try:
        status, body, ctype = hf_video._request(url, payload, headers, timeout_s())
    except Exception as exc:
        _lesson(choice, "hf_wan_i2v", type(exc).__name__)
        return None
    deadline_kind, _extra = hf_video.interpret(status, body, ctype)
    if deadline_kind == "busy":
        status_url = hf_video._status_url(body)
        if status_url:
            import time
            deadline = time.monotonic() + timeout_s()
            while time.monotonic() < deadline:
                time.sleep(3)
                status, body, ctype = hf_video._request(status_url, None, headers, 20)
                kind, _extra = hf_video.interpret(status, body, ctype)
                if kind != "busy":
                    break
            else:
                _lesson(choice, "hf_wan_i2v", "timeout")
                return None
    return _save_from("hf_wan_i2v", status, body, ctype, label, choice)
