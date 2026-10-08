"""
Thumbnail generator — creates Reel / YouTube Short cover images.

Two modes:
  1. Flux AI (FLUX_API_KEY set) — photorealistic product shot
  2. Pillow render (Pillow installed) — text + brand treatment thumbnail
  3. Metadata only — returns prompt + spec for manual creation

Output: 1080x1920 (9:16 vertical) for Reels, 1280x720 (16:9) for YouTube.
"""
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))


def generate_reel_thumbnail(
    reel_data: dict,
    day: int,
    label: str = "reel",
) -> dict:
    """
    Generate or describe a Reel thumbnail.

    Returns:
    {
        "file_path":  "output/creative/reel_1_thumb_day42.jpg" or None,
        "mode":       "flux" | "pillow" | "prompt_only",
        "prompt":     "<image generation prompt>",
        "spec":       "1080x1920, 9:16 vertical",
        "hook_text":  "<hook for text overlay>",
    }
    """
    hook   = reel_data.get("hook_text", "")
    visual = reel_data.get("visual_direction", "")
    reel_id = reel_data.get("id", label)

    prompt = _build_thumbnail_prompt(hook, visual, "reel")

    # 1. Try Gemini scene with real jar
    try:
        from content_generator.creative.gemini_scene import generate_scene_with_real_jar
        path = generate_scene_with_real_jar(
            prompt[:400], day=day, label=f"{reel_id}_thumb_day{day}"
        )
        if path:
            return {"file_path": path, "mode": "gemini_scene", "prompt": prompt,
                    "spec": "1080x1920", "hook_text": hook}
    except Exception as e:
        logger.debug("[thumbnail] Gemini scene failed: %s", e)

    # 2. Try cinematic frame with real jar (white knocked out on cinematic gradient)
    try:
        from content_generator.creative.cinematic_frame import compose_cinematic_frame
        path = compose_cinematic_frame(
            headline=hook or "100% PURE COFFEE",
            day=day,
            label=f"{reel_id}_thumb_day{day}",
        )
        if path:
            return {"file_path": path, "mode": "cinematic_frame", "prompt": prompt,
                    "spec": "1080x1920", "hook_text": hook}
    except Exception as e:
        logger.debug("[thumbnail] Cinematic frame failed: %s", e)

    # 3. Try real jar composer
    try:
        from content_generator.creative.real_jar_composer import compose_reel_thumbnail
        path = compose_reel_thumbnail(reel_data, day, label=reel_id)
        if path:
            return {"file_path": path, "mode": "real_jar", "prompt": prompt,
                    "spec": "1080x1920", "hook_text": hook}
    except Exception as e:
        logger.debug("[thumbnail] Real jar composer failed: %s", e)

    # 4. Fallback Pillow render with real jar photo
    try:
        path = _render_pillow_thumbnail(hook, visual, day, label=f"{reel_id}_thumb")
        if path:
            return {"file_path": path, "mode": "pillow_real_jar", "prompt": prompt,
                    "spec": "1080x1920", "hook_text": hook}
    except Exception as e:
        logger.debug("[thumbnail] Pillow render failed: %s", e)

    return {
        "file_path": None,
        "mode":      "prompt_only",
        "prompt":    prompt,
        "spec":      "1080x1920 vertical, 9:16 aspect ratio",
        "hook_text": hook,
    }


def generate_yt_thumbnail(
    yt_data: dict,
    day: int,
) -> dict:
    """Generate YouTube Short thumbnail (1280x720) using real jar photo."""
    product = yt_data.get("product", "Purity Beans")
    prompt  = (
        f"YouTube thumbnail — {product} coffee jar, bold cinematic composition, "
        f"dark background, large readable headline space, warm gold accent light, "
        f"16:9 horizontal framing, premium FMCG editorial style"
    )

    # Try Gemini scene with real jar
    try:
        from content_generator.creative.gemini_scene import generate_scene_with_real_jar
        path = generate_scene_with_real_jar(prompt, day=day, label=f"yt_thumb_day{day}")
        if path:
            return {"file_path": path, "mode": "gemini_scene", "prompt": prompt, "spec": "1280x720"}
    except Exception as e:
        logger.debug("[thumbnail] Gemini YT scene failed: %s", e)

    # Try real jar composer
    try:
        from content_generator.creative.real_jar_composer import compose_post_image
        path = compose_post_image(
            headline=product, body="100% PURE COFFEE. ZERO CHICORY.",
            day=day, width=1280, height=720, label=f"yt_thumb_day{day}"
        )
        if path:
            return {"file_path": path, "mode": "real_jar", "prompt": prompt, "spec": "1280x720"}
    except Exception as e:
        logger.debug("[thumbnail] Real jar composer failed: %s", e)

    return {"file_path": None, "mode": "prompt_only", "prompt": prompt, "spec": "1280x720"}


def _build_thumbnail_prompt(hook: str, visual: str, content_type: str) -> str:
    from content_generator.creative.brand_guardrails import enforce_brand_prompt
    base = (
        f"Instagram Reel thumbnail — Purity Beans coffee product hero shot, "
        f"vertical 9:16 framing, bold text space in upper third for hook overlay, "
        f"dark cinematic background, warm amber light beam, premium FMCG aesthetic"
    )
    if visual:
        base = f"{visual}. {base}"
    return enforce_brand_prompt(base)


def _render_pillow_thumbnail(
    hook_text: str,
    visual_note: str,
    day: int,
    label: str = "thumb",
) -> str | None:
    """Render a branded thumbnail with real jar photo using Pillow."""
    try:
        from content_generator.creative.real_jar_composer import compose_post_image
        return compose_post_image(
            headline=hook_text or "100% PURE COFFEE",
            body="ZERO CHICORY. 100% COFFEE.",
            day=day,
            idx=7,
            width=1080,
            height=1920,
            label=f"{label}_day{day}",
        )
    except Exception as e:
        logger.debug("[thumbnail] Real jar compose failed in _render_pillow_thumbnail: %s", e)
        return None
