"""Platform-specific evening growth reel prompts for Instagram, Facebook, and YouTube Shorts.

Constructs dedicated, platform-optimized growth reels for the evening window (21:53 IST),
ingesting performance history to be demonstrably superior to previous generation results.
"""
from __future__ import annotations

import json
from content_generator.core.history_benchmark import build_history_benchmark_prompt
from content_generator.prompts.brand import brand_block
from content_generator.prompts.piece_craft import craft_block
from content_generator.rotation import PRODUCTS, WEBSITE_URL, pick

# Distinct evening angles tailored for prime time leisure scroll (7:30 PM - 10:30 PM IST)
EVENING_ANGLES = [
    "The 8 PM coffee craving: why your brain actually wants warmth, not caffeine",
    "What cafes do with unsold brewed coffee vs what's in your freeze-dried jar",
    "Why some instant coffee dissolves instantly while premium coffee takes 5 seconds",
    "The truth about coffee bitterness: bean variety vs roasting burn",
    "Why you should never use boiling water on pure coffee grounds",
    "The secret ratio baristas use to balance coffee and milk at home",
    "Why reading the ingredients on your instant coffee pack changes everything",
    "The difference between freeze-dried coffee crystals and spray-dried powder",
]


def build_instagram_evening_growth(day: int, product: str = "", avoid: str = "", history_context: str = "") -> str:
    """Instagram Evening Growth Reel: Cinematic ASMR, audio-sync cuts, high save & share trigger."""
    product = product or str(pick(PRODUCTS, day))
    angle = EVENING_ANGLES[day % len(EVENING_ANGLES)]
    benchmark = history_context or build_history_benchmark_prompt("instagram", day)

    return f"""INSTAGRAM EVENING GROWTH REEL — FOLLOWER-FIRST CINEMATIC ASMR.

Goal: Maximize save rate, audio-synced engagement, and follower conversion during evening peak scroll.

{avoid}
{benchmark}

TODAY'S PRODUCT REFERENCE: {product}
EVENING FOCUS ANGLE: {angle}

HARD PRODUCTION RULES:
1. Land the hook visually and verbally within 0-1.5 seconds.
2. Structure for high save & share value: deliver an actionable brew secret, label truth, or visual sensory delight.
3. Audio sync: describe exact sound beats (crystal clink, kettle pour, steam hiss).
4. Strictly NO commercial puffery or spammy buy language.
5. End with a follow trigger: "Follow @purepantryprovisions for the daily unfiltered coffee truth."

Return ONLY a single valid JSON object with these keys:
{{
  "id": "reel_1",
  "track": "growth",
  "hook": "Opening spoken line with immediate friction/contrast (must land in 1.5s)",
  "chosen_hook": "Same strong opening line",
  "hook_options": [
    "3 high-friction tension hooks",
    "3 counterintuitive contrarian hooks",
    "3 exact feeling hooks"
  ],
  "title": "Short aesthetic title for Instagram Reels tab",
  "caption": "120-180 words. Spoken, personal coffee lover voice with line breaks. Ends with follow reason & save prompt.",
  "cta": "Follow @purepantryprovisions for daily coffee truths. Save this reel for tomorrow's brew.",
  "hashtags": "#PurityBeans #CoffeeCulture #CoffeeReels #BaristaLife #IndianCoffee #AestheticCoffee",
  "audio": {{
    "mood": "Lo-fi vinyl warm beats or acoustic rhythm",
    "sound_design": "Detailed foley cues (pour at 3s, spoon clink at 7s)"
  }},
  "script": [
    {{"time": "0-2s", "beat": "visual_pattern_interrupt", "on_screen": "4 WORDS MAX", "spoken": "The opening hook line", "visual": "Macro crystal pour or kettle steam"}},
    {{"time": "2-6s", "beat": "curiosity_escalation", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "6-14s", "beat": "demonstration_truth", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "14-22s", "beat": "sensory_payoff", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "22-30s", "beat": "soft_follow_cta", "on_screen": "FOLLOW FOR DAILY BREW TRUTHS", "spoken": "...", "visual": "Final smooth cup swirl"}}
  ],
  "loop_trigger": "How the final shot seamlessly connects back to the opening shot",
  "save_mechanic": "Why viewers bookmark this reel (e.g. precise temperature/ratio guideline)"
}}

{craft_block("growth_reel")}
"""


def build_facebook_evening_growth(day: int, product: str = "", avoid: str = "", history_context: str = "") -> str:
    """Facebook Evening Growth Reel: Relatable conversational debate & community discussion."""
    product = product or str(pick(PRODUCTS, day))
    angle = EVENING_ANGLES[day % len(EVENING_ANGLES)]
    benchmark = history_context or build_history_benchmark_prompt("facebook", day)

    return f"""FACEBOOK EVENING GROWTH REEL & VIDEO — COMMUNITY DISCUSSION & CONVERSATION.

Goal: Drive deep comment section debates and community shares across Indian coffee drinkers (ages 25-55).

{avoid}
{benchmark}

TODAY'S PRODUCT REFERENCE: {product}
TOPIC: {angle}

HARD PRODUCTION RULES:
1. Hook must feel like a direct, relatable conversation or founder question from across the kitchen counter.
2. Fuel comment debate: challenge a common household habit vs the barista way.
3. Clean, legible captions formatted for Facebook newsfeed browsing.
4. Discussion prompt: explicitly ask an engaging question at the end to spark comment replies.

Return ONLY a single valid JSON object with these keys:
{{
  "id": "growth_reel_fb",
  "track": "growth",
  "hook": "Conversational opening sentence that poses an undeniable household coffee question",
  "chosen_hook": "Same hook line",
  "title": "Engaging question-style title for Facebook Video",
  "caption": "150-250 words. Warm, conversational tone with paragraphs. Includes true coffee bean facts. Ends with community debate question.",
  "community_question": "One specific question that demands a quick comment (e.g. 'Do you boil your milk with the coffee, or pour it over? Tell me below.')",
  "cta": "Follow @purepantryprovisions for real coffee insights. Share this with the coffee lover in your house.",
  "hashtags": "#PurityBeans #IndianCoffeeLovers #CoffeeTalk #HomeBrewing #PureCoffee",
  "script": [
    {{"time": "0-3s", "beat": "relatable_hook", "on_screen": "DO YOU DO THIS?", "spoken": "The opening household question", "visual": "Pouring coffee into a mug"}},
    {{"time": "3-8s", "beat": "common_mistake", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "8-18s", "beat": "barista_explanation", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "18-26s", "beat": "the_solution", "on_screen": "...", "spoken": "...", "visual": "..."}},
    {{"time": "26-32s", "beat": "comment_trigger", "on_screen": "WHAT'S YOUR ROUTINE?", "spoken": "Tell me how you brew in the comments", "visual": "Warm kitchen table scene"}}
  ]
}}

{craft_block("facebook_post")}
"""


def build_youtube_evening_growth(day: int, product: str = "", avoid: str = "", history_context: str = "") -> str:
    """YouTube Shorts Evening Growth Reel: Search-optimized, rapid retention loop, subscribe trigger."""
    product = product or str(pick(PRODUCTS, day))
    angle = EVENING_ANGLES[day % len(EVENING_ANGLES)]
    benchmark = history_context or build_history_benchmark_prompt("youtube", day)

    return f"""YOUTUBE SHORTS EVENING GROWTH REEL — SEARCH ALGORITHM & RETENTION LOOP.

Goal: Maximize replay-driven retention through rapid cuts, a search-driven title, and a seamless loop.

{avoid}
{benchmark}

FEATURED COFFEE PRODUCT: {product}
FOCUS TOPIC: {angle}

HARD PRODUCTION RULES:
1. Hook lands in 0-1.5 seconds — first on_screen text and first spoken line ARE the hook. Name a jar, a clock time, or a label contradiction.
2. YouTube SEO title: under 60 characters, high-intent search keywords, include #Shorts. Write a real title, never the words "Punchy YouTube SEO Search Title".
3. Scene pacing: every scene must change visual angle every 1.5 to 2.5 seconds. visual_direction is cinematic (macro jar, pour, steam, label in hand), not a typography card.
4. Seamless ending: the final spoken line must flow right back into the first word of the hook.
5. Subscriber CTA: "Subscribe for the next coffee truth." Never use an Instagram-handle follow CTA or a food-science CTA. The shop URL belongs in the description only.
6. Description must include the words Purity Beans and {WEBSITE_URL}, with at most 3 hashtags plus #Shorts / #PurityBeans.
7. Never invent statistics, prices, stock, reviews, or health claims. Never write 100%, fresh, lab tested, single-origin, or any bean/beans wording except the brand name Purity Beans. Ultra Blend is 70/30 coffee and chicory — never call it pure. Purica/Purista are freeze-dried; Bold/Prima are agglomerated.
8. NEVER copy instruction text or schema labels into hook, title, tagline, or description. The strings in the schema below are field names and guidance, not copy to return.

Return ONLY a single valid JSON object with these keys (values are guidance, not copy):
{{
  "id": "evening_yt_short",
  "track": "growth",
  "product": "{product}",
  "tagline": "A 6-word tagline you invent, not a schema label",
  "title": "A real searchable title under 60 characters ending in #Shorts",
  "hook": "A real 1.5s spoken hook naming a jar or contradiction",
  "chosen_hook": "The same hook line you actually wrote",
  "description": "Purity Beans. Two or three sentences of coffee craft, then {WEBSITE_URL} #PurityBeans #Shorts",
  "cta": "Subscribe for the next coffee truth.",
  "scenes": [
    {{"scene": 1, "type": "hook", "duration_s": 2, "on_screen": "4 WORDS MAX", "spoken": "Your real hook, not a label", "visual_direction": "Macro jar or pour in motion"}},
    {{"scene": 2, "type": "tension", "duration_s": 4, "on_screen": "4 WORDS MAX", "spoken": "The stakes in 8-12 words", "visual_direction": "Tighter shot, steam or spoon"}},
    {{"scene": 3, "type": "turn", "duration_s": 6, "on_screen": "4 WORDS MAX", "spoken": "The unexpected label fact", "visual_direction": "Label in hand, still tense"}},
    {{"scene": 4, "type": "revelation", "duration_s": 6, "on_screen": "4 WORDS MAX", "spoken": "Pay off the hook; say Purity Beans", "visual_direction": "The jar in warm light after the answer"}},
    {{"scene": 5, "type": "payoff_loop", "duration_s": 4, "on_screen": "SUBSCRIBE FOR MORE", "spoken": "Subscribe for the next coffee truth.", "visual_direction": "Looping cut leading right back to scene 1"}}
  ],
  "loop_mechanic": "How the final line and shot restart scene 1"
}}

{craft_block("yt_short")}
"""
