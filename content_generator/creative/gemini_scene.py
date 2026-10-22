"""
Gemini Scene Composer — puts the REAL jar into cinematic scenes.

Unlike FLUX/Pollinations (text-to-image — they invent fake jars), Gemini's
image model accepts the actual jar photo as INPUT and edits it into a scene:
dark marble, steam, golden light — with the real label preserved.

Quality tiers for brand images:
  1. Gemini scene (this module)    — real jar inside a cinematic scene
  2. Card composer (real_jar_composer) — real jar on branded canvas (always works)

Uses the REST API directly (no SDK dependency drift). Free-tier friendly:
only called for the highest-impact images (reel thumbnail + carousel cover),
everything else uses the card composer.

Required secret: GEMINI_API_KEY
"""
from __future__ import annotations
import base64
import datetime
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

_OUT_DIR  = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
# gemini-2.0-flash-exp and the 2.0 image previews were shut down (HTTP 404).
# Nano Banana 2.1 is the current image-edit model; the others are still served.
_LIVE_IMAGE_MODELS = (
    "gemini-nano-banana-2.1",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
)
_RETIRED_IMAGE_MODELS = {
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-exp-image-generation",
    "gemini-2.0-flash-preview-image-generation",
}
_DEAD_IMAGE_MODELS: set[str] = set()
_TIMEOUT  = 120


def _image_model_order() -> list[str]:
    """Configured live model first, then known-live fallbacks. Retired ids are skipped."""
    configured = os.getenv("GEMINI_IMAGE_MODEL", "").strip()
    ordered: list[str] = []
    if configured and configured not in _RETIRED_IMAGE_MODELS:
        ordered.append(configured)
    for model in _LIVE_IMAGE_MODELS:
        if model not in ordered:
            ordered.append(model)
    return [model for model in ordered if model not in _DEAD_IMAGE_MODELS]

def _build_scene_rules(aspect_desc: str = "Square 1:1 composition.") -> str:
    return (
        "Take the product jar from the supplied photo and place it in this scene. "
        "CRITICAL: keep the jar EXACTLY as photographed — same label, same text, "
        "same cap, same shape, same colors. Do not redesign, redraw, or alter the "
        "label in any way. Only change the environment around it. "
        "Photographic realism: commercial food photography shot on Hasselblad 85mm f/2.8 lens, "
        "shallow depth of field, natural morning window directional light with soft diffusion, "
        "correct contact shadow and ambient occlusion where the jar meets the tabletop, "
        "subtle environment reflections on the glass, zero artificial CGI or plastic sheen, "
        "completely realistic lifelike materials and natural grain. No text overlays. "
        f"{aspect_desc}"
    )


_SCENE_RULES = _build_scene_rules("Vertical 9:16 composition.")


def is_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _fetch_scene(api_key: str, body: bytes) -> dict | None:
    """POST the scene. A 404 retires that model for this process and tries the next."""
    import urllib.error

    models = _image_model_order()
    if not models:
        logger.warning("[gemini_scene] no live Gemini image model; falling back to the card composer")
        return None
    for model in models:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json",
                         "User-Agent": "PurityBeans/1.0"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if getattr(e, "code", None) == 404:
                _DEAD_IMAGE_MODELS.add(model)
                logger.warning("[gemini_scene] model %s not found (404); falling through", model)
                continue
            logger.warning("[gemini_scene] Gemini API failed: %s", e)
            return None
        except Exception as e:
            logger.warning("[gemini_scene] Gemini API failed: %s", e)
            return None
    logger.warning("[gemini_scene] no live Gemini image model; falling back to the card composer")
    return None


def generate_scene_with_real_jar(
    scene_prompt: str,
    day: int = 0,
    idx: int = 0,
    product: str | None = None,
    label: str = "gemini_scene",
) -> str | None:
    """
    Place the real jar photo into the described scene via Gemini image editing.
    Returns the saved file path, or None on any failure (callers fall back
    to the card composer).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    from content_generator.creative.real_jar_composer import pick_jar_photo
    jar_path = pick_jar_photo(day, idx, product)
    if not jar_path:
        return None

    try:
        with open(jar_path, "rb") as f:
            jar_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.warning("[gemini_scene] Could not read jar photo: %s", e)
        return None

    scene_text = scene_prompt
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        lower_label = str(label or "").lower()
        if "facebook" in lower_label:
            target_platform = "facebook"
        elif "youtube" in lower_label or "yt_" in lower_label or "short" in lower_label:
            target_platform = "youtube"
        else:
            target_platform = "instagram"
        dirs = get_visual_adaptation_directives(platform=target_platform)
        extras = []
        if dirs.get("boost_exposure"):
            extras.append("bright natural morning sunlight, high exposure, strong subject separation")
        if dirs.get("add_action_texture"):
            extras.append("visible action: rising aromatic steam from a just-poured cup")
        if dirs.get("break_centered_catalog"):
            extras.append("candid lifestyle depth with natural human context, warm organic materials")
        if extras:
            scene_text += "\nVISUAL DIRECTIVES: " + " | ".join(extras)
    except Exception:
        pass

    is_tall = any(k in str(label or "").lower() for k in ["reel", "story", "yt_short", "short", "vertical"])
    aspect_desc = "Vertical 9:16 composition." if is_tall else "Square 1:1 composition."
    rules = _build_scene_rules(aspect_desc)

    body = json.dumps({
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/png", "data": jar_b64}},
                {"text": f"{rules}\n\nSCENE: {scene_text}"},
            ]
        }],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")

    data = _fetch_scene(api_key, body)
    if not data:
        return None

    # Extract the returned image
    try:
        for cand in data.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    image_bytes = base64.b64decode(inline["data"])
                    if len(image_bytes) < 5000:
                        continue
                    os.makedirs(_OUT_DIR, exist_ok=True)
                    from content_generator.core.ist_dates import today_ist
                    date_str = today_ist().isoformat()
                    path = os.path.join(_OUT_DIR, f"{label}_{date_str}.jpg")
                    with open(path, "wb") as f:
                        f.write(image_bytes)
                    logger.info("[gemini_scene] Real jar placed in scene -> %s (base: %s)",
                                path, os.path.basename(jar_path))

                    try:
                        from content_generator.creative.jar_provenance import record_jar_provenance
                        record_jar_provenance(path, jar_asset_id=jar_path, render_source="gemini_real_jar")
                    except Exception as pe:
                        logger.debug("[gemini_scene] Provenance recording skipped: %s", pe)

                    return path
    except Exception as e:
        logger.warning("[gemini_scene] Response parse failed: %s", e)

    logger.warning("[gemini_scene] No image in Gemini response")
    return None
