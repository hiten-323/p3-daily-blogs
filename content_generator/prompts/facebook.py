"""Facebook post prompt — community-driven, relatable, native Facebook engagement."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL

FB_HASHTAGS = "#PurityBeans #IndianCoffee #MorningCoffee #CoffeeLovers"


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE original, relatable, community-engaging Facebook post for Pure Pantry Provisions / Purity Beans. Return a single JSON object.

{avoid}

COMMUNITY ANGLE: [{angle[0]}] — {angle[1]}

PLATFORM INTENT (FACEBOOK 2026):
- Audience: Indian families, professionals, and home coffee drinkers (25-50).
- Tone: Warm, relatable, authentic, conversational. Zero LinkedIn corporate jargon. Zero hard sales infomercials.
- Distribution Levers: Comments, shares with friends/family, and dwell time.
- Structure:
  1. Relatable Opening Hook: Connect with a shared Indian coffee experience or common morning habit.
  2. Insight / Story: The truth about pure coffee vs commercial root fillers, brewing at home, or taste differences.
  3. Conversation Starter: A question that compels people to comment their own habits or tag a family member.
  4. Follow & Explore CTA: Invite following the page for daily coffee truths, with website link.

{{
  "angle": "{angle[0]}",
  "hook": "Relatable 1-line hook that connects with everyday Indian coffee drinkers.",
  "body": "150-250 words. Warm, engaging, storytelling style. Discusses real coffee vs filler, or brewing tips that anyone can try at home. Clear paragraph breaks.",
  "community_question": "A friendly, conversational question that asks about their morning routine, favorite mug, or family coffee debate.",
  "cta": "Follow our page for daily honest coffee tips. Discover 100% pure coffee at {WEBSITE_URL}",
  "hashtags": "{FB_HASHTAGS}"
}}"""
