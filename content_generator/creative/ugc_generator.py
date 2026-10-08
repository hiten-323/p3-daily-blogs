"""
UGC Generator — generates User Generated Content style assets using
the actual Purity Beans jar images as reference input to every AI tool.

Each daily run produces:
  - 1 avatar frame  : AI persona holding the real jar
  - 1 UGC frame     : lo-fi authentic scene with real jar
  - 1 reel hook     : cinematic scroll-stopper with real jar as hero

All prompts and image paths are written to output/ugc/ so you can
paste them directly into Nano Banana Pro → Seedance → OpenArt VFX.
"""
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os

from content_generator.creative.jar_composer import (
    get_daily_creative_package,
    build_avatar_prompt,
    build_ugc_prompt,
    build_reel_hook_prompt,
    AVATAR_PERSONAS,
    UGC_SCENES,
    REEL_HOOK_TEMPLATES,
)
from content_generator.creative.flux_generator import generate_image

logger = logging.getLogger(__name__)

_UGC_OUT_DIR = os.getenv("UGC_OUTPUT_DIR", os.path.join("output", "ugc"))


def generate_daily_ugc(day: int, product: str = None) -> dict:
    """
    Generate the full daily UGC package:
      - Avatar prompt + generated reference image
      - UGC scene prompt + generated reference image
      - Reel hook prompt + generated reference image
      - A paste-ready tool brief for Nano Banana Pro + Seedance

    Returns a dict with all prompts, image paths, and the tool brief.
    """
    os.makedirs(_UGC_OUT_DIR, exist_ok=True)
    date_str = today_ist().isoformat()

    package = get_daily_creative_package(day=day, product=product)

    results = {
        "day":      day,
        "date":     date_str,
        "product":  product,
        "avatar":   _process_creative(package["avatar"],   "avatar",    day),
        "ugc":      _process_creative(package["ugc"],      "ugc",       day),
        "reel_hook":_process_creative(package["reel_hook"],"reel_hook", day),
    }

    # Write paste-ready tool brief to output/ugc/
    brief_path = os.path.join(_UGC_OUT_DIR, f"tool_brief_{date_str}.json")
    try:
        with open(brief_path, "w", encoding="utf-8") as f:
            json.dump(_build_tool_brief(results, date_str), f, indent=2, ensure_ascii=False)
        logger.info("[ugc] Tool brief written -> %s", brief_path)
        results["tool_brief_path"] = brief_path
    except Exception as e:
        logger.warning("[ugc] Could not write tool brief: %s", e)

    return results


def _process_creative(package: dict, label: str, day: int) -> dict:
    """Generate a reference image for one creative package using the real jar photo."""
    image_prompt = package.get("image_prompt", "")
    hook_text = str(package.get("hook_text") or package.get("concept") or "REAL COFFEE. ZERO CHICORY.")[:60]

    image_path = None
    jar_asset_id = None
    render_source = None

    # Tier 1: Gemini multimodal scene editing (passes real jar photo PNG bytes as reference input)
    try:
        from content_generator.creative.gemini_scene import generate_scene_with_real_jar
        from content_generator.creative.real_jar_composer import pick_jar_photo
        candidate_jar = pick_jar_photo(day, idx=0, product=package.get("product"))
        image_path = generate_scene_with_real_jar(
            image_prompt[:400],
            day=day,
            product=package.get("product"),
            label=f"{label}_day{day}",
        )
        if image_path:
            jar_asset_id = candidate_jar
            render_source = "gemini_real_jar"
            logger.info("[ugc] Gemini placed real jar in UGC scene for %s: %s", label, image_path)
    except Exception as e:
        logger.debug("[ugc] Gemini real jar scene skipped for %s: %s", label, e)

    # Tier 2: Cinematic frame compositor (real jar photo knocked out on gradient)
    if not image_path:
        try:
            from content_generator.creative.cinematic_frame import compose_cinematic_frame
            from content_generator.creative.real_jar_composer import pick_jar_photo
            candidate_jar = pick_jar_photo(day, idx=0, product=package.get("product"), overlay_safe=True, prefer_front=True)
            image_path = compose_cinematic_frame(
                headline=hook_text,
                day=day,
                product=package.get("product"),
                width=1080,
                height=1920,
                label=f"{label}_day{day}",
            )
            if image_path:
                jar_asset_id = candidate_jar
                render_source = "cinematic_real_jar"
                logger.info("[ugc] Cinematic frame composed from real jar for %s: %s", label, image_path)
        except Exception as e:
            logger.debug("[ugc] Cinematic frame skipped for %s: %s", label, e)

    # Tier 3: Real jar post composer
    if not image_path:
        try:
            from content_generator.creative.real_jar_composer import compose_post_image, pick_jar_photo
            candidate_jar = pick_jar_photo(day, idx=0, product=package.get("product"), overlay_safe=True)
            image_path = compose_post_image(
                headline=hook_text,
                day=day,
                product=package.get("product"),
                width=1080,
                height=1920,
                label=f"{label}_day{day}",
            )
            if image_path:
                jar_asset_id = candidate_jar
                render_source = "real_jar"
                logger.info("[ugc] Real jar composer built image for %s: %s", label, image_path)
        except Exception as e:
            logger.debug("[ugc] Real jar composer fallback failed for %s: %s", label, e)

    # HARD INVARIANT: Zero escape hatches. A product creative CANNOT exist unless
    # a verified real-jar image is present. Never fall back to generic image generators.
    is_verified = bool(
        image_path
        and render_source
        and jar_asset_id
        and os.path.exists(image_path)
        and os.path.exists(jar_asset_id)
    )

    if image_path and not is_verified:
        logger.error("[ugc] Image %s generated without verified jar asset! Rejecting.", image_path)
        image_path = None
        render_source = None
        jar_asset_id = None

    return {
        **package,
        "generated_reference_image": image_path,
        "asset_real_jar_verified": is_verified,
        "jar_asset_id": jar_asset_id,
        "render_source": render_source,
    }


def _build_tool_brief(results: dict, date_str: str) -> dict:
    """
    Build a human-readable paste-ready brief for Nano Banana Pro + Seedance workflow.
    You paste this into the AI tools manually to create the final videos.
    """
    def _entry(data: dict, title: str) -> dict:
        entry = {
            "title":                   title,
            "step_1_NANO_BANANA_PRO":    data.get("image_prompt", ""),
            "step_2_SEEDANCE":          data.get("motion_prompt", ""),
            "reference_jar_files":      data.get("reference_jar_paths", []),
            "generated_reference":      data.get("generated_reference_image", ""),
            "asset_real_jar_verified":  data.get("asset_real_jar_verified", False),
            "jar_asset_id":             data.get("jar_asset_id", ""),
            "render_source":            data.get("render_source", ""),
        }
        if "ugc_caption" in data:
            entry["caption"] = data["ugc_caption"]
        if "hook_text" in data:
            entry["on_screen_text"] = data["hook_text"]
        if "persona" in data:
            entry["persona"] = data["persona"]["id"]
        if "scene" in data:
            entry["scene"] = data["scene"]["id"]
        if "template_id" in data:
            entry["hook_template"] = data["template_id"]
        return entry

    return {
        "date":        date_str,
        "day":         results["day"],
        "product":     results.get("product"),
        "workflow":    "Paste Step 1 into Nano Banana Pro → generate image → paste Step 2 into Seedance → animate → (optional) OpenArt VFX to insert founder face",
        "tool_chain":  ["Nano Banana Pro", "Seedance 2.0", "OpenArt VFX"],
        "assets": {
            "avatar":    _entry(results["avatar"],    "AVATAR — AI persona with real jar"),
            "ugc":       _entry(results["ugc"],       "UGC — authentic lo-fi scene with real jar"),
            "reel_hook": _entry(results["reel_hook"], "REEL HOOK — cinematic scroll-stopper"),
        },
        "openart_vfx_note": (
            "To insert founder face: upload your video clip to OpenArt VFX → "
            "Replace Background → choose the generated reference as target world. "
            "Your face stays. The Purity Beans world appears behind you."
        ),
    }


def get_all_avatars(product: str = None) -> list[dict]:
    """Return all 6 avatar prompts with jar references — useful for one-off batch generation."""
    return [
        build_avatar_prompt(persona_id=p["id"], product=product)
        for p in AVATAR_PERSONAS
    ]


def get_all_ugc_scenes(product: str = None) -> list[dict]:
    """Return all 6 UGC scene prompts with jar references — for batch generation."""
    return [
        build_ugc_prompt(scene_id=s["id"], product=product)
        for s in UGC_SCENES
    ]


def get_all_reel_hooks(product: str = None) -> list[dict]:
    """Return all 5 reel hook prompts with jar references — for batch generation."""
    return [
        build_reel_hook_prompt(hook_id=t["id"], product=product)
        for t in REEL_HOOK_TEMPLATES
    ]
