"""Threads post prompt — snappy, conversation-starting, high-engagement micro-content."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL

HASHTAG_SET = "#PurityBeans #CoffeeKnowledge #PureCoffee"


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE sharp, viral, conversation-starting Threads post for Purity Beans (Pure Pantry Provisions). Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

PLATFORM CONSTRAINTS (THREADS):
- Character limit: MUST BE UNDER 480 CHARACTERS TOTAL.
- Style: Conversational, thought-provoking, raw, direct, zero corporate speak.
- Structure:
  1. A sharp 1-line truth or question (hooks the reader instantly).
  2. A surprising coffee fact or clean-label insight (why 100% coffee matters or how chicory/spray-drying affects them).
  3. Brand mention: Purity Beans.
  4. Link / CTA: {WEBSITE_URL}
  5. 2-3 hashtags: {HASHTAG_SET}

MANDATORY RULES:
- Must mention 'Purity Beans'.
- Must mention '{WEBSITE_URL}'.
- Total length of 'text' field MUST NOT EXCEED 480 characters.
- No medical claims or cures.

{{
  "angle": "{angle[0]}",
  "text": "Your sharp, punchy thread under 480 characters with Purity Beans and {WEBSITE_URL}."
}}"""
