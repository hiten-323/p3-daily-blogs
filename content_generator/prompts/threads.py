"""Threads post prompt — snappy, conversation-starting, native micro-content."""
from content_generator.prompts.brand import brand_block


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE ultra-viral, conversation-starting, follower-converting Threads post. Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

NATIVE THREADS ARCHITECTURE (OPTIMIZED FOR REPLIES, QUOTES & FOLLOWS):
1. CONVERSATION HOOK: Raw observation or contrarian stance that sparks immediate mental reaction (e.g. 'Unpopular opinion: most bitter instant coffee is just water that was too hot.').
2. UNVARNISHED INSIGHT: 1-2 punchy lines breaking down the reality (dose per cup, or 85°C extraction). Name the jar in the first lines and answer the hook before the CTA. Freeze-drying may be explained only when the linked jar is Purica or Purista (or Variety Box / Gourmet Duo Mini). Bold is agglomerated pure coffee. You must not call Bold freeze-dried. Do not name a process for Ultra Blend. A freeze-dried vs agglomerated comparison may link Bold for the agglomerated side only. Never attack chicory or other brands. Never write the word fully. Stay under 480 characters.
3. DISCUSSION SPARK: Prompt an effortless reply or quote ('Check the ingredient panel on your kitchen jar right now — what does it list?', 'Agree or disagree?').
4. FOLLOWER CONVERSION: Give a clear reason to follow ('Follow for daily coffee truths Big Coffee hides.').

PLATFORM RULES (STRICT):
- Total length MUST BE UNDER 480 CHARACTERS.
- LAYOUT: the CONVERSATION HOOK alone on the first line, then a blank line, then the insight that ANSWERS it (a concrete fact, check, comparison or action), then the discussion spark. Never one run-on paragraph.
- NO PROMOTIONAL LINKS (links suppress reach in the Threads algorithm).
- NO HASHTAG CLUTTER (Threads is conversation-led, not tag-stuffed).
- Raw, witty, insider perspective. Zero corporate pitch.
- Optional subtle brand signature only if natural (e.g., '— Hiten Jain / Purity Beans').

{{
  "angle": "{angle[0]}",
  "text": "Your sharp, conversational viral thread under 480 characters ending with a discussion prompt and follower reason."
}}"""


_ARTICLE_KEYS = ("blog_post", "sections", "introduction", "slides", "frames", "scenes")


def regeneration_prompt(piece: dict, feedback: str, threshold: float, brand: str,
                        from_scratch: bool = False) -> str:
    """Native Threads regen. The model must return text, not another platform's pack."""
    featured = (piece or {}).get("featured_product") or "the featured Purity Beans jar"
    reasons = " ".join(str(feedback or "").split())[:600]
    source = ""
    if not from_scratch and isinstance(piece, dict):
        text = str(piece.get("text") or piece.get("body") or "").strip()
        if text:
            source = "ORIGINAL TEXT (rewrite it; stay under 480 characters):\n" + text[:480] + "\n\n"
    return (
        f"{brand}\n\n"
        f"TASK: Write a native Threads post for {featured}. "
        f"It must pass an editorial score of {threshold}.\n"
        f"{source}"
        f"REJECTION TO FIX:\n{reasons}\n"
        "This is a Threads post, not a blog, a reel, or a Facebook article. "
        "Do not write an introduction, sections, slides, frames, or scenes. "
        'Return ONE JSON object with exactly this key: ["text"]. '
        "text is under 480 characters. Put the hook alone on the first line, then a blank line, "
        "then the payoff that answers the hook, then one reply prompt. "
        "Name the jar. No promotional link. No hashtag block. "
        "Do not include an editorial_score. Return ONLY the JSON object."
    )


def accept_threads_regen(improved: dict, original: dict | None = None) -> dict | None:
    """Keep a short native post. An article pack or an over-long line is not stored."""
    if not isinstance(improved, dict) or any(key in improved for key in _ARTICLE_KEYS):
        return None
    text = ""
    for key in ("text", "body", "content"):
        value = improved.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            break
    if not text:
        nested = improved.get("threads_post")
        if isinstance(nested, str):
            text = nested.strip()
    if len(text) < 20:
        return None
    if len(text) > 480:
        window = text[:480]
        end = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
        if end < 40:
            return None
        text = window[: end + 1].strip()
    if len(text) > 480 or len(text) < 20:
        return None
    merged = dict(improved)
    merged["text"] = text
    if isinstance(original, dict):
        for key in ("featured_product", "objective", "primary_cta", "success_metric", "day_number", "type", "regen_round"):
            if key not in merged and key in original:
                merged[key] = original[key]
    return merged
