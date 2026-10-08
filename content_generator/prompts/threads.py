"""Threads post prompt — snappy, conversation-starting, high-engagement micro-content."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL

HASHTAG_SET = "#PurityBeans #CoffeeKnowledge #PureCoffee"


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE ultra-viral, high-engagement, follower-converting Threads post for Purity Beans (Pure Pantry Provisions). Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

VIRALITY & FOLLOWER ENGINE (THREADS 2026):
1. THE HOOK: Conversational disruption or surprising contrast (e.g. 'Unpopular truth:', 'Turn your instant coffee jar around right now.', 'Most people boil their coffee to death.').
2. THE PAYOFF: Expose the reality of instant coffee adulteration, freeze-drying vs spray-drying, or extraction temperature in 1-2 punchy sentences.
3. THE ENGAGEMENT TRIGGER: Prompt effortless comments or debate ('Check your kitchen jar right now — what does it say?', 'Agree or disagree?').
4. THE FOLLOWER CONVERSION: Give a clear reason to follow ('Follow for daily unfiltered coffee truths.').

PLATFORM CONSTRAINTS (THREADS):
- Character limit: MUST BE UNDER 480 CHARACTERS TOTAL.
- Style: Raw, conversational, direct, witty, insider perspective. Zero generic corporate speak.
- Structure:
  1. Disruptive hook.
  2. Concrete coffee fact / clean-label insight.
  3. Brand + follow bridge: Purity Beans (100% pure coffee, zero chicory).
  4. Link / CTA: {WEBSITE_URL}
  5. 2 hashtags: {HASHTAG_SET}

MANDATORY RULES:
- Must mention 'Purity Beans'.
- Must mention '{WEBSITE_URL}'.
- Total length of 'text' field MUST NOT EXCEED 480 characters.
- No medical claims or cures.

{{
  "angle": "{angle[0]}",
  "text": "Your sharp, punchy viral thread under 480 characters with Purity Beans and {WEBSITE_URL}."
}}"""
