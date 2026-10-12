"""
Jar Composer — converts actual Purity Beans jar PNGs into usable references
for every image/video generation API in the pipeline.

Three generation modes:
  - avatar_mode   : AI character (persona) holding / interacting with the jar
  - ugc_mode      : lo-fi authentic "real customer" frame with jar in scene
  - reel_hook_mode: cinematic scroll-stopping still frame using jar as hero

Every mode uses the actual jar images from brand_assets/ as reference input.
"""
import base64
import logging
import os
import random

from content_generator.core.brand_guard import (
    PRODUCTS, SIZES, ANGLES, get_product_references, REFERENCE_IMAGES
)

logger = logging.getLogger(__name__)

_BRAND_ASSETS_DIR = "brand_assets"

# Realism suffixes appended to every generated prompt.
# These are what separate "AI slop" from believable content.

REALISM_PHOTO = (
    "Photographed look, not rendered: visible skin pores and texture, natural asymmetric face, "
    "flyaway hairs, real fabric wrinkles, one believable light source with correct shadow direction, "
    "mixed color temperature like a real room, natural grain, slight motion blur where relevant, "
    "subject slightly off-center. Lived-in environment details: a used spoon, water ring, "
    "charging cable, fingerprints on glass. "
    "The jar has a correct contact shadow and environment reflections on the glass; "
    "label texture catches light like printed paper. "
    "NO perfect symmetry, NO plastic skin, NO oversaturation, NO text in image, NO 3D-render look."
)

REALISM_UGC = (
    "Authentic phone-shot look: shot on iPhone, slightly wrong white balance, window overexposed, "
    "minor tilt, thumb-distance vertical framing, natural grain, imperfect focus. "
    "Real kitchen/desk clutter in frame. If it looks like a professional brand shoot it fails — "
    "it must look like a real customer casually filmed their own life. "
    "NO studio lighting, NO perfect composition, NO text in image."
)

REALISM_MOTION = (
    "Physics-true motion: steam rises and disperses naturally, liquid has weight, humans breathe "
    "with visible chest movement and micro blinks. Subtle handheld sway or slow locked-off push only. "
    "24fps film feel. No floaty camera moves, no morphing, no extra fingers appearing, "
    "faces stay stable and consistent throughout."
)


# ── Avatar personas ───────────────────────────────────────────────────────────

AVATAR_PERSONAS = [
    {
        "id": "urban_professional",
        "description": "Indian working professional, 28-35, smart casual, confident expression",
        "setting": "modern home office desk, soft natural light, laptop in background",
        "action": "holding the Purity Beans jar at chest level, looking directly at camera",
        "emotion": "calm confidence — they know something others don't",
    },
    {
        "id": "college_student",
        "description": "Indian college student, 20-24, casual hoodie, earphones around neck",
        "setting": "study desk at night, books stacked, warm lamp light",
        "action": "pointing at the Purity Beans jar with one finger, eyebrow raised",
        "emotion": "discovery — just found something the market hides",
    },
    {
        "id": "home_brewer",
        "description": "Indian woman, 30-38, home setting, relaxed morning look",
        "setting": "kitchen counter, morning light, simple Indian kitchen background",
        "action": "holding the Purity Beans jar in one hand, mug in other",
        "emotion": "morning ritual pride — this is my daily choice",
    },
    {
        "id": "fitness_person",
        "description": "Indian fitness enthusiast, 25-32, gym wear, post-workout glow",
        "setting": "gym bag on kitchen counter, post-workout, natural light",
        "action": "comparing Purity Beans jar to a generic competing jar, pushing generic away",
        "emotion": "I refuse to compromise — same energy as training hard",
    },
    {
        "id": "founder_voice",
        "description": "Indian founder/entrepreneur, 30-40, smart casual, earnest look",
        "setting": "clean minimal desk, brand identity in background, professional but warm",
        "action": "holding Purity Beans jar while gesturing to explain something",
        "emotion": "transparency — I built this because I was tired of being fooled",
    },
    {
        "id": "curious_buyer",
        "description": "Indian person, 25-40, any gender, everyday appearance",
        "setting": "supermarket aisle or kitchen, realistic everyday environment",
        "action": "reading the back of the Purity Beans jar — ingredient label visible",
        "emotion": "relief and surprise — this label has nothing to hide",
    },
]


# ── UGC scene templates ───────────────────────────────────────────────────────

UGC_SCENES = [
    {
        "id": "morning_kitchen",
        "setting": "real Indian kitchen, morning, natural window light, slight hand-held feel",
        "jar_placement": "front and center on kitchen counter, spoon beside it",
        "vibe": "authentic morning routine, not a shoot — shot on phone",
        "caption_voice": "First person, casual. 'Started my day with this and I cannot go back.'",
    },
    {
        "id": "office_desk",
        "setting": "realistic office or WFH desk, monitor in background, papers around",
        "jar_placement": "beside laptop, partially open lid, fresh cup of coffee next to it",
        "vibe": "real person, real workspace, not staged",
        "caption_voice": "First person, busy tone. 'Keeps me going without the crash.'",
    },
    {
        "id": "late_night_study",
        "setting": "student desk at night, lamp on, books everywhere, phone charging",
        "jar_placement": "open jar with spoon, cup of coffee beside textbook",
        "vibe": "midnight grind, lo-fi aesthetic, slightly grainy",
        "caption_voice": "Relatable student voice. 'This is surviving finals season.'",
    },
    {
        "id": "label_reveal",
        "setting": "plain background, hand holding jar, rotating slowly to show label",
        "jar_placement": "jar held by hand, ingredient label facing camera",
        "vibe": "comparison/reveal style UGC — showing the clean label",
        "caption_voice": "Reaction voice. 'Read the back. Literally nothing added.'",
    },
    {
        "id": "comparison_unboxing",
        "setting": "counter top, two jars side by side",
        "jar_placement": "Purity Beans jar vs generic competitor jar (no branding visible on other)",
        "vibe": "real comparison UGC — hand points at ingredient difference",
        "caption_voice": "Expose voice. 'One of these is lying to you.'",
    },
    {
        "id": "gifting_setup",
        "setting": "premium gifting setup, kraft paper, ribbon, warm light",
        "jar_placement": "Purity Beans jar as centerpiece of gift arrangement",
        "vibe": "gifting season content, aspirational but real",
        "caption_voice": "Gift recommender. 'The gift that tells them you care about quality.'",
    },
]


# ── Reel hook templates (AI-generated visual hooks) ──────────────────────────

REEL_HOOK_TEMPLATES = [
    {
        "id": "shock_calm_contrast",
        "concept": "Purity Beans jar sits perfectly still, completely clean and lit in gold, "
                   "while all around it chicory powder, brown dust, and 'filler' particles "
                   "explode outward as if repelled by the jar. The jar never moves.",
        "camera": "locked-off close-up, slight push-in, 9:16 vertical",
        "motion": "Everything moves EXCEPT the Purity Beans jar. Particles scatter outward. "
                  "Gold light pulses gently on the jar. Background chaos, product stillness.",
        "hook_text": "IT REPELS THE FAKE",
    },
    {
        "id": "human_anchor_label",
        "concept": "Person crouching beside a giant Purity Beans jar (oversized for drama), "
                   "finger pointing directly at the ingredient label. Label glows slightly. "
                   "Expression: wide eyes, mouth open in surprise.",
        "camera": "low angle, slightly below subject, 9:16 vertical, cinematic",
        "motion": "Person stays still, pointing. Golden glow pulses on the label. "
                  "Tiny light particles drift upward from the label like steam.",
        "hook_text": "READ THE LABEL",
    },
    {
        "id": "impossible_scene",
        "concept": "Person calmly making coffee at their desk. Their Purity Beans jar is clean "
                   "and glowing. Around them, other (generic, unbranded) jars are visibly "
                   "murky and dark inside. The person does not notice — they only use Purity Beans.",
        "camera": "medium shot, slightly surreal depth of field, 9:16 vertical",
        "motion": "Other jars swirl with dark murky liquid. Purity Beans jar stays perfectly clear. "
                  "Person keeps making coffee, calm and unbothered.",
        "hook_text": "THEY DON'T NOTICE",
    },
    {
        "id": "before_after_split",
        "concept": "Screen split vertically. Left side: dark, industrial, murky — chicory. "
                   "Right side: clean, glowing, gold-lit — Purity Beans jar. "
                   "Hand moves from left side (disgust gesture) to right side (approval gesture).",
        "camera": "locked-off, split-screen, 9:16 vertical, high contrast",
        "motion": "Left side stays dark and murky. Right side glows warmer and cleaner. "
                  "Hand moves from left to right. Right side brightens at the end.",
        "hook_text": "SAME PRICE. NOT THE SAME.",
    },
    {
        "id": "revelation_closeup",
        "concept": "Extreme close-up of the Purity Beans jar ingredient label. "
                   "Text says only: Coffee. Nothing else. Hand slowly pulls away to reveal "
                   "the full jar. Then a competitor label appears (blurred, with long ingredient list). "
                   "Purity Beans label comes back in focus.",
        "camera": "macro lens, extreme close-up, pull focus, 9:16 vertical",
        "motion": "Start on ingredient text. Pull back slowly. Brief cut to blurred competitor. "
                  "Cut back to Purity Beans label — sharp, clean, proud.",
        "hook_text": "ONE INGREDIENT.",
    },
]


# ── Core functions ────────────────────────────────────────────────────────────

def get_jar_as_base64(product: str = None, size: str = None, angle: str = "front") -> str | None:
    """
    Load a jar PNG from brand_assets/ and return as base64-encoded string.
    Used to pass actual jar image to AI generation APIs.
    """
    if product and size:
        path = os.path.join(_BRAND_ASSETS_DIR, f"puritybeans_{product}_{size}_{angle}.png")
    elif product:
        # Pick first available size
        for s in SIZES:
            path = os.path.join(_BRAND_ASSETS_DIR, f"puritybeans_{product}_{s}_{angle}.png")
            if os.path.exists(path):
                break
    else:
        refs = [p for p in REFERENCE_IMAGES if os.path.exists(p)]
        path = refs[0] if refs else None

    if not path or not os.path.exists(path):
        logger.warning("[jar_composer] Jar image not found: %s", path)
        return None

    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        logger.info("[jar_composer] Loaded jar reference: %s (%d chars)", path, len(encoded))
        return encoded
    except Exception as e:
        logger.error("[jar_composer] Failed to load jar: %s", e)
        return None


def get_jar_paths_for_content(content_text: str, limit: int = 4) -> list[str]:
    """
    Return actual file paths of product-matched jar images.
    Used for APIs that accept file paths (fal.ai, OpenArt).
    """
    refs = get_product_references(content_text)
    if not refs:
        refs = [p for p in REFERENCE_IMAGES if os.path.exists(p)]
    # Prefer front + lifestyle angles
    preferred = [p for p in refs if "front" in p or "lifestyle" in p]
    fallback  = [p for p in refs if p not in preferred]
    result = (preferred + fallback)[:limit]
    logger.info("[jar_composer] Reference jars selected: %s", result)
    return result


def build_avatar_prompt(persona_id: str = None, product: str = None, day: int = 0) -> dict:
    """
    Build a complete avatar generation prompt package using the real jar as reference.

    Returns dict with:
        image_prompt       : paste into Nano Banana Pro / HF FLUX
        motion_prompt      : paste into Seedance / Veo
        reference_jar_paths: actual file paths to use as img2img reference
        ugc_caption        : ready-to-post caption for this avatar
        persona            : the persona dict used
    """
    persona = None
    if persona_id:
        persona = next((p for p in AVATAR_PERSONAS if p["id"] == persona_id), None)
    if not persona:
        persona = AVATAR_PERSONAS[day % len(AVATAR_PERSONAS)]

    jar_paths = get_jar_paths_for_content(product or "", limit=3)
    jar_note  = f"Reference jar images supplied: {', '.join(jar_paths)}" if jar_paths else ""

    image_prompt = (
        f"Hyperrealistic photographic portrait. {persona['description']}. "
        f"Setting: {persona['setting']}. "
        f"Action: {persona['action']}. "
        f"Emotion: {persona['emotion']}. "
        f"THE JAR MUST MATCH EXACTLY: use the supplied reference Purity Beans jar — "
        f"same label, same shape, same cap, same product name. Do not redesign. "
        f"Lighting: warm amber/gold accent on the jar, soft natural fill on face. "
        f"Style: photorealistic, 85mm portrait lens f/1.8, shallow depth of field, "
        f"dark or neutral background, editorial but authentic. "
        f"Vertical format 9:16. {REALISM_PHOTO} "
        f"{jar_note}"
    )

    motion_prompt = (
        f"The person stays natural and relaxed. The Purity Beans jar stays prominent and still. "
        f"Subtle: slight head tilt or natural breath motion. "
        f"Camera: slow steady push-in. "
        f"Light on jar glows softly. No sudden moves. {REALISM_MOTION}"
    )

    ugc_caption = (
        f"Switched to Purity Beans and I cannot explain why it hits different. "
        f"Zero chicory. No preservatives. Just coffee. "
        f"Available at p3online.in"
    )

    return {
        "image_prompt":        image_prompt,
        "motion_prompt":       motion_prompt,
        "reference_jar_paths": jar_paths,
        "ugc_caption":         ugc_caption,
        "persona":             persona,
    }


def build_ugc_prompt(scene_id: str = None, product: str = None, day: int = 0) -> dict:
    """
    Build a UGC-style content package using the real jar as reference.
    UGC = lo-fi, authentic, looks like a real customer shot it.

    Returns dict with:
        image_prompt       : paste into image generation tool
        motion_prompt      : paste into video generation tool
        reference_jar_paths: actual file paths for img2img reference
        ugc_caption        : authentic-sounding caption
        scene              : the scene dict used
    """
    scene = None
    if scene_id:
        scene = next((s for s in UGC_SCENES if s["id"] == scene_id), None)
    if not scene:
        scene = UGC_SCENES[day % len(UGC_SCENES)]

    jar_paths = get_jar_paths_for_content(product or "", limit=3)
    jar_note  = f"Reference jar images: {', '.join(jar_paths)}" if jar_paths else ""

    image_prompt = (
        f"Lo-fi authentic UGC photo style — looks like it was shot on an iPhone, "
        f"not a professional camera. Slight grain, natural imperfect light. "
        f"Setting: {scene['setting']}. "
        f"THE PURITY BEANS JAR MUST BE EXACTLY AS IN THE REFERENCE IMAGES — "
        f"same label, shape, cap, product name. Place: {scene['jar_placement']}. "
        f"Vibe: {scene['vibe']}. "
        f"Vertical 9:16. Warm, slightly imperfect, believably human. {REALISM_UGC} "
        f"{jar_note}"
    )

    motion_prompt = (
        f"Subtle hand-held camera feel — very slight shake, natural. "
        f"The Purity Beans jar stays visible throughout. "
        f"If a hand is present: natural finger movement or slight tilt of jar. "
        f"No dramatic sweeps. No speed ramps. "
        f"Looks like a person casually filming their own coffee routine. {REALISM_MOTION}"
    )

    return {
        "image_prompt":        image_prompt,
        "motion_prompt":       motion_prompt,
        "reference_jar_paths": jar_paths,
        "ugc_caption":         scene["caption_voice"],
        "scene":               scene,
    }


def build_reel_hook_prompt(hook_id: str = None, product: str = None, day: int = 0) -> dict:
    """
    Build a cinematic scroll-stopping reel hook package using the real jar.

    Returns dict with:
        image_prompt       : the still frame prompt (paste into Nano Banana Pro)
        motion_prompt      : the motion prompt (paste into Seedance)
        reference_jar_paths: actual file paths for img2img reference
        hook_text          : 4-word on-screen text overlay
        concept            : human-readable description of the hook
    """
    template = None
    if hook_id:
        template = next((t for t in REEL_HOOK_TEMPLATES if t["id"] == hook_id), None)
    if not template:
        template = REEL_HOOK_TEMPLATES[day % len(REEL_HOOK_TEMPLATES)]

    jar_paths = get_jar_paths_for_content(product or "", limit=4)
    jar_note  = f"REFERENCE JARS (match exactly — same label, shape, cap): {', '.join(jar_paths)}" if jar_paths else ""

    image_prompt = (
        f"Hyperrealistic cinematic still frame for Instagram Reel hook. "
        f"Concept: {template['concept']} "
        f"Camera: {template['camera']}. "
        f"THE PURITY BEANS JAR IS THE HERO — must match reference exactly. "
        f"No redesign. No alternate label. No generic jar. "
        f"Lighting: dark background, single warm amber/gold beam on the Purity Beans jar. "
        f"Style: photorealistic, editorial luxury FMCG, deep shadows, cinematic color grade. "
        f"Vertical 9:16. No text or typography in the image. {REALISM_PHOTO} "
        f"{jar_note}"
    )

    motion_prompt = (
        f"Motion for: {template['concept'][:100]}. "
        f"Camera: {template['camera']}. "
        f"Motion rules: {template['motion']} "
        f"The Purity Beans jar stays sharp and prominent at all times. "
        f"Slow, intentional motion. No cuts. No transitions. {REALISM_MOTION}"
    )

    result = {
        "image_prompt":        image_prompt,
        "motion_prompt":       motion_prompt,
        "reference_jar_paths": jar_paths,
        "hook_text":           template["hook_text"],
        "concept":             template["concept"],
        "template_id":         template["id"],
    }
    try:
        from content_generator.creative.product_reel_templates import select_product_reel
        selected = select_product_reel(product=product, text=product or "")
    except Exception:
        selected = None
    if selected:
        result["reference_reel_template_id"] = selected["template_id"]
        result["reference_reel_path"] = selected["path"]
        result["reference_reel_reusable"] = True
        result["reference_reel_audio_embedded"] = False
    return result


def get_daily_creative_package(day: int, product: str = None) -> dict:
    """
    Returns all three creative packages for a given day — avatar, UGC, and reel hook.
    Rotates through all templates so every day is different.
    """
    return {
        "avatar":    build_avatar_prompt(day=day, product=product),
        "ugc":       build_ugc_prompt(day=day, product=product),
        "reel_hook": build_reel_hook_prompt(day=day, product=product),
        "day":       day,
    }
