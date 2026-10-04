"""
Runway ML video generator — uses Runway Gen-3 Alpha API.

Setup:
    pip install runwayml
    export RUNWAY_API_KEY="your_key_here"   # get from runwayml.com

Generates short video clips (5–10 s) from text or image+text prompts.
Ideal for: Reel hero shots, product close-ups, steam rising from cup, etc.

Usage:
    from content_generator.creative.runway_generator import generate_video
    path = generate_video(
        "Purity Beans jar, dark marble surface, golden steam rising, cinematic",
        duration_seconds=5,
        label="reel_1_hero"
    )
    # Returns: "output/creative/reel_1_hero_20260609.mp4" or None
"""
from content_generator.core.ist_dates import today_ist
import logging
import os
import time

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("RUNWAY_API_KEY")
_MODEL   = os.getenv("RUNWAY_MODEL", "gen3a_turbo")   # gen3a_turbo or gen3a
_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

# Runway-specific brand prompt template
_BRAND_VIDEO_SUFFIX = (
    ", dark cinematic lighting, warm amber bokeh, Purity Beans premium FMCG aesthetic, "
    "editorial product video, no text overlays, no people, slow motion preferred"
)


def is_configured() -> bool:
    """Return True if Runway API is available and configured."""
    if not _API_KEY:
        return False
    try:
        import runwayml  # noqa: F401
        return True
    except ImportError:
        return False


def generate_video(
    prompt: str,
    duration_seconds: int  = 5,
    label: str             = "video",
    image_path: str        = None,
    seed: int              = None,
) -> str | None:
    """
    Generate a video clip using Runway Gen-3.

    Returns local .mp4 file path on success, None otherwise.

    Args:
        prompt:           Text description of the video scene
        duration_seconds: 5 or 10 (Runway Gen-3 Alpha constraint)
        label:            Output filename prefix
        image_path:       Optional reference image for image-to-video generation
        seed:             Optional reproducibility seed
    """
    safe_prompt = prompt + _BRAND_VIDEO_SUFFIX

    if not _API_KEY:
        logger.info("[runway] RUNWAY_API_KEY not set — skipping video generation")
        return None

    try:
        import runwayml
    except ImportError:
        logger.debug("[runway] runwayml not installed — pip install runwayml")
        return None

    try:
        client = runwayml.RunwayML(api_key=_API_KEY)
        logger.info("[runway] Generating %ds video: '%s...'", duration_seconds, safe_prompt[:50])

        task_args = {
            "model":       _MODEL,
            "prompt_text": safe_prompt,
            "duration":    duration_seconds,
        }
        if seed is not None:
            task_args["seed"] = seed

        if image_path and os.path.exists(image_path):
            task_args["prompt_image"] = _encode_image(image_path)

        task = client.image_to_video.create(**task_args)
        task_id = task.id

        # Poll for completion (Runway is async)
        return _poll_and_download(client, task_id, label)

    except Exception as e:
        logger.error("[runway] Generation failed: %s", e)
        return None


def generate_reel_clips(reel_data: dict, day: int) -> list[str]:
    """
    Generate video clips for each frame in a reel script.
    Returns list of file paths for available clips.
    """
    paths = []
    frames = reel_data.get("frames", [])
    for i, frame in enumerate(frames[:3]):  # max 3 clips per reel to control cost
        prompt = frame.get("visual_direction") or frame.get("on_screen", "")
        if not prompt:
            continue
        path = generate_video(
            prompt,
            duration_seconds=5,
            label=f"reel_{reel_data.get('id', 'unknown')}_frame{i+1}_day{day}",
        )
        if path:
            paths.append(path)
    return paths


def _poll_and_download(client, task_id: str, label: str, timeout: int = 300) -> str | None:
    """Poll Runway task until complete, then download the video."""
    import urllib.request
    import datetime

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            task = client.tasks.retrieve(task_id)
            status = task.status

            if status == "SUCCEEDED":
                video_url = task.output[0] if task.output else None
                if not video_url:
                    return None
                return _download_video(video_url, label)

            elif status == "FAILED":
                logger.error("[runway] Task %s FAILED", task_id)
                return None

            logger.debug("[runway] Task %s status: %s", task_id, status)
            time.sleep(10)

        except Exception as e:
            logger.error("[runway] Poll error: %s", e)
            return None

    logger.warning("[runway] Task %s timed out after %ds", task_id, timeout)
    return None


def _download_video(url: str, label: str) -> str | None:
    import urllib.request
    import datetime

    os.makedirs(_OUT_DIR, exist_ok=True)
    date_str = today_ist().isoformat()
    filename = f"{label}_{date_str}.mp4"
    filepath = os.path.join(_OUT_DIR, filename)

    try:
        urllib.request.urlretrieve(url, filepath)
        logger.info("[runway] Saved → %s", filepath)
        return filepath
    except Exception as e:
        logger.error("[runway] Download failed: %s", e)
        return None


def _encode_image(image_path: str) -> str:
    """Encode image file as base64 data URI for Runway API."""
    import base64
    ext  = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"
