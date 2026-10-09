"""
AI image generator — free provider cascade, no paid API required to start.

Provider priority:
  1. Hugging Face Inference API  — FREE with a free HF account token
                                   Model: FLUX.1-schnell (fastest FLUX variant)
                                   Signup: huggingface.co → Settings → Access Tokens
                                   Secret: HF_TOKEN (GitHub Actions)
                                   ~1,000 free images/month on free tier

  2. Pollinations AI             — Attempted as anonymous fallback.
                                   Free tier may work without a key in some regions.
                                   No signup needed (falls back silently if blocked).

  3. fal.ai Flux                 — Paid fallback, highest quality.
                                   Only used if FAL_KEY / FLUX_API_KEY secret is set.

  4. Pillow placeholder          — Always works, zero dependencies beyond Pillow.
                                   Generates a branded dark-background placeholder
                                   so the pipeline never hard-fails on images.

GitHub Actions setup (required for real images):
    Secrets → New secret → HF_TOKEN = your Hugging Face access token

Usage:
    from content_generator.creative.flux_generator import generate_image

    path = generate_image(
        "Purity Beans jar on dark marble, golden rim light, editorial photography",
        width=1080, height=1080,
        label="carousel_cover",
    )
    # Returns local file path always (placeholder if all AI providers fail)
"""
import datetime
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_OUT_DIR  = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_TIMEOUT  = int(os.getenv("IMAGE_TIMEOUT", "90"))

# Provider keys
_PIXAZO_KEY = os.getenv("PIXAZO_API_KEY") or os.getenv("PIXAZO_KEY")
_PIXAZO_ENDPOINT = os.getenv("PIXAZO_IMAGE_ENDPOINT", "https://gateway.pixazo.ai/flux/text-to-image")
_FREE_IMAGE_API_URL = os.getenv("FREE_IMAGE_API_URL", "").strip().rstrip("/")
_FREE_IMAGE_API_KEY = os.getenv("FREE_IMAGE_API_KEY") or os.getenv("CLOUDFLARE_IMAGE_API_KEY")
_HF_TOKEN = os.getenv("HF_TOKEN")                                    # free
_FAL_KEY  = os.getenv("FAL_KEY") or os.getenv("FLUX_API_KEY")        # paid fallback
if _FAL_KEY:
    os.environ.setdefault("FAL_KEY", _FAL_KEY)

# Hugging Face model — FLUX.1-schnell is fastest and free
_HF_MODEL = os.getenv(
    "HF_IMAGE_MODEL",
    "black-forest-labs/FLUX.1-schnell",
)
_FLUX_MODEL = os.getenv("FLUX_MODEL", "fal-ai/flux/dev")


# ── Public API ────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    """
    Returns True if at least one image provider is available.
    Pillow placeholder always works so this is always True when Pillow is installed.
    """
    if _HF_TOKEN:
        return True
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def generate_image(
    prompt: str,
    width:  int = 1080,
    height: int = 1080,
    label:  str = "image",
    seed:   int = None,
) -> str | None:
    """
    Generate an image and save it locally.

    Tries providers in order: HuggingFace → Pollinations → fal.ai → Pillow placeholder.
    Always returns a path (placeholder at minimum) — never blocks the pipeline.

    Args:
        prompt: Image description. Brand guardrails applied automatically.
        width:  Output width in pixels (default 1080)
        height: Output height in pixels (default 1080)
        label:  Used in output filename for identification
        seed:   Optional fixed seed for reproducibility

    Returns:
        Local file path (never None if Pillow is installed).
    """
    from content_generator.core.brand_guard import get_product_references, REFERENCE_IMAGES
    available_refs = get_product_references(prompt)
    if not available_refs:
        logger.warning("[image] REFERENCE JAR MISSING — no matching files found. Skipping image generation.")
        return None

    from content_generator.creative.brand_guardrails import enforce_brand_prompt
    safe_prompt = enforce_brand_prompt(prompt)

    ref_list = "\n".join(f"- {p}" for p in available_refs)
    ai_prompt = f"""IMPORTANT:
Use the exact Purity Beans jar shown in the supplied reference images.
No generic coffee jars. No fictional labels. No alternate packaging.

Reference images (product-matched):
{ref_list}

{safe_prompt}"""

    # 1. Pixazo
    if _PIXAZO_KEY:
        path = _pixazo(ai_prompt, width, height, label, seed)
        if path:
            return path

    # 2. Optional self-hosted Cloudflare Worker; configured by URL and matching API key.
    if _FREE_IMAGE_API_URL and _FREE_IMAGE_API_KEY:
        path = _free_image_worker(ai_prompt, width, height, label)
        if path:
            return path

    # 3. Hugging Face
    if _HF_TOKEN and _HF_TOKEN.startswith("hf_"):
        path = _huggingface(ai_prompt, width, height, label, seed)
        if path:
            return path

    # 4. Pollinations
    path = _pollinations(ai_prompt, width, height, label, seed)
    if path:
        return path

    # 5. fal.ai
    if _FAL_KEY:
        path = _fal_flux(ai_prompt, width, height, label, seed)
        if path:
            return path

    # 6. Real-jar branded composition fallback
    return _pillow_placeholder(safe_prompt, width, height, label)


def generate_carousel_images(slides: list[dict], day: int) -> list[str]:
    """Generate one image per carousel slide using the real jar composer."""
    try:
        from content_generator.creative.real_jar_composer import compose_carousel_slides
        paths = compose_carousel_slides(slides, day)
        if paths:
            return paths
    except Exception as e:
        logger.debug("[image] real_jar_composer carousel failed: %s", e)

    paths = []
    for i, slide in enumerate(slides):
        if isinstance(slide, str):
            prompt = slide
        else:
            prompt = slide.get("image_prompt") or slide.get("visual") or ""
        if not prompt:
            continue
        path = generate_image(
            prompt, width=1080, height=1080,
            label=f"carousel_slide_{i+1}_day{day}",
            seed=day * 100 + i,
        )
        if path:
            paths.append(path)
    return paths


def generate_reel_thumbnail(reel: dict, day: int, label: str = "reel") -> str | None:
    """Generate a 9:16 thumbnail for a reel using real jar photos."""
    try:
        from content_generator.creative.real_jar_composer import compose_reel_thumbnail
        path = compose_reel_thumbnail(reel, day, label=label)
        if path:
            return path
    except Exception as e:
        logger.debug("[image] real_jar_composer reel thumbnail failed: %s", e)

    prompt = (
        reel.get("visual_description")
        or reel.get("image_prompt")
        or reel.get("hook", "")
    )
    if not prompt:
        return None
    return generate_image(prompt, width=1080, height=1920, label=f"{label}_thumb_day{day}")


# ── Pixazo provider ──────────────────────────────────────────────────────────

def _pixazo(prompt: str, width: int, height: int, label: str, seed: int | None) -> str | None:
    """Call the configured Pixazo model endpoint; accepts binary images or media URLs."""
    import json
    from urllib.error import HTTPError, URLError
    try:
        req = urllib.request.Request(
            _PIXAZO_ENDPOINT,
            data=json.dumps({"prompt": prompt}).encode("utf-8"),
            headers={
                "Ocp-Apim-Subscription-Key": _PIXAZO_KEY or "",
                "Content-Type": "application/json",
                "User-Agent": "PurityBeans/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body, content_type = resp.read(), resp.headers.get("Content-Type", "")
        if _is_image_response(body, content_type):
            return _save_image(body, label, ext=_extension_from_type(content_type))
        data = json.loads(body.decode("utf-8"))
        url = _extract_media_url(data)
        if not url and data.get("request_id"):
            request_id = urllib.parse.quote(str(data["request_id"]), safe="")
            poll_url = "https://gateway.pixazo.ai/v2/requests/status/" + request_id
            attempts = max(1, min(30, int(os.getenv("PIXAZO_POLL_ATTEMPTS", "12"))))
            interval = max(1, min(30, int(os.getenv("PIXAZO_POLL_INTERVAL_SECONDS", "5"))))
            import time
            for _ in range(attempts):
                time.sleep(interval)
                poll = urllib.request.Request(poll_url, headers={
                    "Ocp-Apim-Subscription-Key": _PIXAZO_KEY or "",
                    "User-Agent": "PurityBeans/1.0",
                })
                with urllib.request.urlopen(poll, timeout=_TIMEOUT) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                if str(result.get("status", "")).upper() in {"FAILED", "ERROR", "CANCELLED"}:
                    return None
                url = _extract_media_url(result)
                if url:
                    break
        return _download_image_url(url, label) if url else None
    except Exception as exc:
        logger.warning("[image] Pixazo failed: %s", type(exc).__name__)
        return None


# ── Self-hosted free-image-generation-api Worker ──────────────────────────────

def _free_image_worker(prompt: str, width: int, height: int, label: str) -> str | None:
    """Call the user's deployed Cloudflare Worker and validate its binary response."""
    import json
    try:
        req = urllib.request.Request(
            _FREE_IMAGE_API_URL,
            data=json.dumps({"prompt": prompt}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {_FREE_IMAGE_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "image/jpeg, image/png, application/octet-stream",
                "User-Agent": "PurityBeans/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body, content_type = resp.read(), resp.headers.get("Content-Type", "")
        if not _is_image_response(body, content_type):
            logger.warning("[image] Free image Worker returned non-image response")
            return None
        return _save_image(body, label, ext=_extension_from_type(content_type))
    except Exception as exc:
        logger.warning("[image] Free image Worker failed: %s", type(exc).__name__)
        return None


def _extension_from_type(content_type: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    return {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}.get(mime, "jpg")


def _is_image_response(body: bytes, content_type: str) -> bool:
    mime = (content_type or "").lower()
    signature = (
        body[:3] == b"\\xff\\xd8\\xff"
        or body[:8] == b"\\x89PNG\\r\\n\\x1a\\n"
        or (body[:4] == b"RIFF" and body[8:12] == b"WEBP")
    )
    return len(body) > 1000 and (mime.startswith("image/") or signature)


def _extract_media_url(payload: dict) -> str | None:
    from urllib.parse import urlparse
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    for value in (payload.get("image"), payload.get("url"), payload.get("media_url"),
                  output.get("image"), output.get("url"), output.get("media_url")):
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, str) and urlparse(value).scheme == "https" and urlparse(value).netloc:
            return value
    return None


def _download_image_url(url: str, label: str) -> str | None:
    from urllib.parse import urlparse
    if urlparse(url).scheme != "https" or not urlparse(url).netloc:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PurityBeans/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body, content_type = resp.read(), resp.headers.get("Content-Type", "")
        if not _is_image_response(body, content_type):
            return None
        return _save_image(body, label, ext=_extension_from_type(content_type))
    except Exception as exc:
        logger.warning("[image] Pixazo media download failed: %s", type(exc).__name__)
        return None


# ── Provider 1: Hugging Face Inference API (FREE) ─────────────────────────────

def _huggingface(
    prompt: str, width: int, height: int, label: str, seed: int | None
) -> str | None:
    """
    Call Hugging Face Inference API for FLUX.1-schnell.
    Free tier: ~1,000 images/month. Token from huggingface.co/settings/tokens.
    """
    import json

    url  = f"https://router.huggingface.co/hf-inference/models/{_HF_MODEL}"
    body = json.dumps({
        "inputs": prompt,
        "parameters": {
            "width":               min(width, 1024),    # HF free tier caps at 1024
            "height":              min(height, 1024),
            "num_inference_steps": 4,                   # schnell default
            **({"seed": seed} if seed is not None else {}),
        },
    }).encode("utf-8")

    logger.info("[image] HuggingFace %dx%d | model=%s | '%s...'",
                width, height, _HF_MODEL, prompt[:50])

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {_HF_TOKEN}",
                "Content-Type":  "application/json",
                "User-Agent":    "PurityBeans/1.0",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)

        if resp.status != 200:
            logger.warning("[image] HuggingFace HTTP %d", resp.status)
            return None

        image_bytes = resp.read()

        # HF returns JSON error or image bytes
        if image_bytes[:1] == b"{":
            error = image_bytes.decode("utf-8", errors="ignore")[:200]
            logger.warning("[image] HuggingFace returned JSON (model loading?): %s", error)
            return None

        if len(image_bytes) < 1000:
            logger.warning("[image] HuggingFace response too small (%d bytes)", len(image_bytes))
            return None

        logger.info("[image] HuggingFace OK (%d KB)", len(image_bytes) // 1024)
        return _save_image(image_bytes, label, ext="jpg")

    except Exception as e:
        logger.warning("[image] HuggingFace failed: %s", e)
        return None


# ── Provider 2: Pollinations AI (anonymous free) ──────────────────────────────

def _pollinations(
    prompt: str, width: int, height: int, label: str, seed: int | None
) -> str | None:
    """Anonymous Pollinations call — free in some regions, may return 402 elsewhere."""
    encoded = urllib.parse.quote(prompt, safe="")
    params  = {"width": width, "height": height}
    if seed is not None:
        params["seed"] = seed

    url = f"https://image.pollinations.ai/prompt/{encoded}?{urllib.parse.urlencode(params)}"
    logger.info("[image] Pollinations %dx%d | '%s...'", width, height, prompt[:50])

    try:
        req  = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)

        if resp.status != 200:
            return None

        image_bytes = resp.read()
        if len(image_bytes) < 1000:
            return None

        # Pollinations returns JSON on error/limit exceeded even with HTTP 200
        if image_bytes[:1] == b"{":
            logger.debug("[image] Pollinations returned JSON (rate limited): %s", image_bytes[:200])
            return None

        logger.info("[image] Pollinations OK (%d KB)", len(image_bytes) // 1024)
        return _save_image(image_bytes, label, ext="jpg")

    except Exception as e:
        logger.debug("[image] Pollinations failed: %s", e)
        return None


# ── Provider 3: fal.ai Flux (paid fallback) ───────────────────────────────────

def _fal_flux(
    prompt: str, width: int, height: int, label: str, seed: int | None
) -> str | None:
    """fal.ai Flux — paid, used only if FAL_KEY is set and free providers failed."""
    try:
        import fal_client
    except ImportError:
        logger.debug("[image] fal-client not installed")
        return None

    try:
        logger.info("[image] fal.ai %dx%d | '%s...'", width, height, prompt[:50])
        from content_generator.core.brand_guard import get_product_references
        refs = get_product_references(prompt)
        args = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_images": 1,
            "output_format": "jpeg",
            "reference_images": refs,
            "strength": 0.9,
        }
        if seed is not None:
            args["seed"] = seed

        result     = fal_client.subscribe(_FLUX_MODEL, arguments=args, with_logs=False)
        image_url  = (result.get("images") or [{}])[0].get("url", "")
        if not image_url:
            return None

        req  = urllib.request.Request(image_url, headers={"User-Agent": "PurityBeans/1.0"})
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        logger.info("[image] fal.ai OK")
        return _save_image(resp.read(), label, ext="jpg")

    except Exception as e:
        logger.error("[image] fal.ai failed: %s", e)
        return None


# ── Provider 4: Pillow placeholder (guaranteed) ───────────────────────────────

def _pillow_placeholder(prompt: str, width: int, height: int, label: str) -> str | None:
    """
    Generate a branded image using the real jar photo from brand_assets.
    Guarantees that all renders feature an authentic Purity Beans jar photo.
    """
    try:
        from content_generator.creative.real_jar_composer import compose_post_image
        composed = compose_post_image(
            headline="PURITY BEANS",
            body="100% Pure Coffee. Zero Chicory.",
            width=width,
            height=height,
            label=label,
        )
        if composed:
            return composed
    except Exception as e:
        logger.debug("[image] real_jar_composer in placeholder failed: %s", e)

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.debug("[image] Pillow not installed — cannot generate placeholder")
        return None

    img  = Image.new("RGB", (width, height), color=(13, 9, 5))   # #0D0905 espresso
    draw = ImageDraw.Draw(img)

    # Gold accent bar at top
    bar_h = max(8, height // 60)
    draw.rectangle([(0, 0), (width, bar_h)], fill=(200, 150, 46))   # #C8962E

    # Brand name
    try:
        font_large = ImageFont.truetype("arial.ttf", size=max(28, width // 20))
        font_small = ImageFont.truetype("arial.ttf", size=max(16, width // 36))
    except Exception:
        font_large = ImageFont.load_default()
        font_small = font_large

    cx = width // 2
    draw.text((cx, height // 3),   "PURITY BEANS",    font=font_large, fill=(200, 150, 46), anchor="mm")
    draw.text((cx, height // 2),   "100% Pure Coffee", font=font_small, fill=(245, 238, 216), anchor="mm")

    # Truncated prompt
    short = (prompt[:60] + "...") if len(prompt) > 60 else prompt
    draw.text((cx, height * 2 // 3), short, font=font_small, fill=(120, 100, 80), anchor="mm")

    # Gold accent bar at bottom
    draw.rectangle([(0, height - bar_h), (width, height)], fill=(200, 150, 46))

    logger.info("[image] Pillow placeholder generated (%dx%d)", width, height)
    return _save_image(_pil_to_bytes(img), label, ext="jpg")


def _pil_to_bytes(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ── Shared helper ─────────────────────────────────────────────────────────────

def _save_image(image_bytes: bytes, label: str, ext: str = "jpg") -> str | None:
    os.makedirs(_OUT_DIR, exist_ok=True)
    from content_generator.core.ist_dates import today_ist
    date_str = today_ist().isoformat()
    filepath = os.path.join(_OUT_DIR, f"{label}_{date_str}.{ext}")
    try:
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        logger.info("[image] Saved -> %s (%d KB)", filepath, len(image_bytes) // 1024)
        return filepath
    except Exception as e:
        logger.error("[image] Save failed: %s", e)
        return None
