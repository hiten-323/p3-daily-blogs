"""Per-platform prompt blocks. Each one is the native job, not a shared caption."""
from __future__ import annotations
from content_generator.core import price_truth as _PT

from content_generator.prompts.growth_engine.plans import (
    BANNED_OPENERS,
    LABEL_PLATFORM,
    asset_plan,
)

_NATIVE = {
    "reel": (
        "IG Reel. Three hook variants. First frame carries the tension. "
        "Voiceover and on-screen text complement each other. One pattern interrupt that serves the story. "
        "A payoff, a loop or a clean ending, a caption that adds a fact the frames did not already say, "
        "one comment prompt, one follow line, one commercial line, and a small hashtag set. "
        "It must work with the sound off. Use the real jar when the SKU is in frame. "
        "Hook in the first 1.5 seconds names a specific, checkable thing (a label line, a granule test, "
        f"a brewing step, or for Ultra Blend only: about ₹{_PT.ultra('per_cup')} a cup). Value is one verified fact from the catalog, shown not claimed. "
        "End with: Follow @purepantryprovisions for <specific next promise> and Shop p3online.in."
    ),
    "carousel": (
        "IG carousel. Slide 1 is a specific curiosity. One idea per slide. "
        "The last slide delivers the takeaway and one next action. "
        "The caption adds context and a reason to save or share. Keep the existing slide schema."
    ),
    "ig_single": (
        "IG single image. One visual concept, one short headline, one caption, one follow reason, one action. "
        "The official approved jar card stays sharp and legible. No AI scene, no quote poster."
    ),
    "stories": (
        "IG Stories as one connected sequence: a relatable hook, then a useful fact or demo, "
        "then one real interaction, then the product next step. "
        "A link sticker only uses a verified destination. No fake poll results."
    ),
    "facebook": (
        "Facebook. A direct opener about a real situation, a practical insight, "
        "one discussion prompt, and one product or business-inquiry CTA. "
        "Write it as its own post. Do not paste the Instagram caption. "
        "First line is a household moment people recognise (the morning cup, guests, the kitchen shelf). "
        "Give one verified, practical takeaway (dose, water temperature, storage, jar choice by taste). "
        "Close with a question to comment on, then Follow @purepantryprovisions and Shop p3online.in."
    ),
    "threads": (
        "Threads. One observation or question under the character limit. "
        "A reason to reply. Product only when it adds. No hashtag pile and no forced link. "
        "Open with a crisp, specific take about brewing or taste (not about other brands), "
        "add one verified detail, end with a reply question and a light Follow @purepantryprovisions; "
        "p3online.in only once, at the end."
    ),
    "linkedin": (
        "LinkedIn. A professional opener on a real business question, a lesson, "
        "an observation labelled as an observation, and a qualified wholesale or distribution next step. "
        "Name the B2B audience. No invented metrics and no motivational filler."
    ),
    "yt_short": (
        "YouTube Short. A hook, a fast setup, a payoff, a subscribe line that says what the next video is for, "
        "and a separate product CTA only if this one is commercial. Title and description stand alone."
    ),
    "blog": (
        "Shopify blog. An intent-aligned title, a meta description, an intro about why the search matters, "
        "accurate sections, catalog links only, and a conclusion with one CTA. "
        "Keep the existing word-count and schema rules. No fake research."
    ),
    "whatsapp": (
        "WhatsApp or B2B note, only when outreach is enabled and the lead is verified. "
        "Short, relevant, one next step. No fake prior contact and no follow-up to an opt-out."
    ),
}


CHICORY_POLICY = (
    "CHICORY POLICY, EVERY DAY AND EVERY SKU: Never attack chicory, roasted root, or 'filler', and never "
    "frame chicory as a trick, adulterant, scam or villain. Never compare 'zero chicory' or '0% chicory' jars "
    "against Ultra Blend, and never contrast our jars with chicory mixtures. Praise Bold, Purista, Purica and "
    "Prima on their own merits (bean, process, taste, lead-free glass jar). "
    "Ultra Blend gets a positive, honest story: 70% coffee and 30% chicory, a smooth, rounded milk coffee in the "
    "South Indian tradition. State the 70/30 ratio plainly and proudly."
)


def ultra_positive_story(sku: str) -> str:
    """The blend story that must be in the prompt before any Ultra Blend asset is written."""
    from content_generator.core.product_truth import name_contains_chicory

    if not name_contains_chicory(str(sku or "")):
        return ""
    return (
        "ULTRA BLEND STORY, REQUIRED BEFORE YOU WRITE: "
        "Ultra Blend is 70% coffee and 30% chicory, a smooth milk coffee. "
        "Say that ratio accurately. Never call it pure, pure coffee, zero chicory, chicory-free, or no chicory. "
        "Do not attack chicory, roasted root, or filler. Do not make this jar the problem another jar solves. "
        "Tell it positively: a smooth, rounded milk coffee, 70/30, honestly labelled."
    )


def _process_match_rule() -> str:
    from content_generator.core.process_match import PROCESS_MATCH_RULE
    return PROCESS_MATCH_RULE


def generation_preface(sku: str, day: int = 0) -> str:
    """Shared rules appended to every generation prompt for this day."""
    banned = "; ".join(f'"{line}"' for line in BANNED_OPENERS[:5])
    story = ultra_positive_story(sku)
    lines = [
        "GROWTH ENGINE v1 — binding. Do not copy one caption across platforms.",
        "Journey, in this order: STOP, CURIOSITY, VALUE, TRUST, FOLLOW, BUY.",
        "STOP is a specific hook. CURIOSITY must be paid off. VALUE is one concrete takeaway.",
        "TRUST uses the real jar and the catalog. FOLLOW is a specific promise. BUY is one verified next step.",
        f"Banned openers: {banned}.",
        "Do not repeat today's hook or CTA on another platform. Same fact, different treatment.",
        "No invented prices, stock, reviews, awards, or health claims. Shopify catalog is the source of truth.",
        "Never write fresh, freshly, freshness, fresher, freshest, lab tested, lab-tested, or zero acidity. The word refresh is allowed.",
        f"Featured SKU: {sku or 'unset'}. The SKU controls which claims are allowed.",
        CHICORY_POLICY,
        _process_match_rule(),
    ]
    if story:
        lines.append(story)
    lines.append(f"Day {int(day or 0)}.")
    return "\n".join(lines)


def prompt_block(label: str, sku: str = "", day: int = 0, *, variant: int = 0) -> str:
    """Native instructions plus the declared plan for this asset."""
    platform = LABEL_PLATFORM.get(label, label)
    if platform not in _NATIVE:
        return ""
    if label == "reel_2":
        variant = max(variant, 1)
    plan = asset_plan(platform, day, sku, variant=variant)
    secondary = plan["secondary_objective"] or "none"
    return "\n".join([
        f"PLATFORM MODULE ({platform}).",
        _NATIVE[platform],
        f"Primary objective: {plan['primary_objective']}.",
        f"Secondary objective: {secondary}.",
        f"Audience: {plan['audience']}.",
        f"Angle: {plan['angle']}. Rationale: {plan['rationale']}",
        f"Follow promise: {plan['follow_promise']}",
        "Write only this platform. Do not reuse another asset's hook or CTA.",
        ultra_positive_story(sku),
        _process_match_rule(),
        _viral_hooks(label),
        _obstacle_lessons(label),
        _platform_learning(platform),
    ]).strip()


def _platform_learning(platform: str) -> str:
    """Inject measured lessons from this platform only; sparse evidence stays silent."""
    platform_name = {
        "reel": "instagram", "carousel": "instagram", "ig_single": "instagram",
        "stories": "instagram", "instagram": "instagram", "instagram_post": "instagram",
        "facebook": "facebook", "threads": "threads", "linkedin": "linkedin",
        "yt_short": "youtube", "youtube": "youtube", "blog": "shopify", "whatsapp": "whatsapp",
    }.get(str(platform or "").lower(), str(platform or "").lower())
    try:
        from content_generator.core.learning_engine import get_platform_learning_block
        return get_platform_learning_block(platform_name)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug("[learning] platform prompt block unavailable: %s", exc)
        return ""


def _viral_hooks(label: str) -> str:
    from content_generator.core.viral_gate import hook_block
    return hook_block(label)


def _obstacle_lessons(label: str) -> str:
    try:
        from content_generator.core.obstacle_lessons import prompt_block as lessons
        return lessons(label)
    except Exception:
        return ""
