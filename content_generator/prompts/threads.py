"""Threads post prompt — snappy, conversation-starting, native micro-content."""
from content_generator.prompts.brand import brand_block


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE ultra-viral, conversation-starting, follower-converting Threads post. Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

NATIVE THREADS ARCHITECTURE (OPTIMIZED FOR REPLIES, QUOTES & FOLLOWS):
1. CONVERSATION HOOK: Raw observation or contrarian stance that sparks immediate mental reaction (e.g. 'Unpopular opinion: most bitter instant coffee is just water that was too hot.').
2. UNVARNISHED INSIGHT: 1-2 punchy lines breaking down the reality (freeze-drying vs spray drying, dose per cup, or 85°C extraction) — never attack chicory or other brands.
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
