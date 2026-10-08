"""4-part Instagram Story sequence prompt."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL, get_todays_viral_idea


def build(day: int = 0) -> str:
    # Story + YouTube Short share ONE companion concept (same video is reused
    # for both). Offset keeps it DISTINCT from today's reels.
    companion = get_todays_viral_idea(day + 15)

    return f"""{brand_block()}

Generate ONE 4-story Instagram Story sequence for Purity Beans. Return a single JSON object.

COMPANION CONCEPT (shared with today's YouTube Short — the same vertical video
is posted to both): {companion}
IMPORTANT: This concept is deliberately DIFFERENT from today's Instagram Reels.
Do not reuse the reels' hooks or angles.

{{
  "story_1": {{
    "type": "poll",
    "headline": "2-4 WORDS ALL CAPS — pattern interrupt. E.g. THIS OR THAT / HOT TAKE / REAL TALK",
    "subtext": "Context line — max 8 words",
    "poll_question": "Max 10 words — polarising, instantly answerable",
    "option_a": "Max 4 words — the wrong choice most people make",
    "option_b": "Max 4 words — the Purity Beans direction"
  }},
  "story_2": {{
    "type": "bts",
    "badge": "BEHIND THE SCENES",
    "headline": "Max 12 words — raw sourcing fact or industry truth. Unscripted feel.",
    "body": "2-3 sentences — unfiltered Indian coffee supply chain reality. One specific shocking detail.",
    "screenshot_hook": "The one fact that makes them screenshot and share"
  }},
  "story_3": {{
    "type": "clean_truth",
    "headline": "THE INGREDIENT TRUTH",
    "fact": "Verifiable coffee truth: e.g. Rs 18/cup home calculation vs Rs 250 cafe cup, or 100% Arabica vs chicory root filler. ZERO fabrication: NEVER invent fake customer counts, fake DMs, or synthetic handles.",
    "sticker_prompt": "Interactive quiz or emoji slider sticker for audience engagement"
  }},
  "story_4": {{
    "type": "cta",
    "headline": "Max 10 words — low-pressure value question",
    "reply_keyword": "1-2 WORDS ALL CAPS",
    "offer": "What they get on reply — specific and immediate. Max 15 words.",
    "question_sticker": "Fun easy question for the sticker — one-sentence answer",
    "link": "https://{WEBSITE_URL}"
  }}
}}"""


# Instagram-native V2 rules (shared growth/creative contract)
from content_generator.prompts.instagram_native import INSTAGRAM_NATIVE_RULES
