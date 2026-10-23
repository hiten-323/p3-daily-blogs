"""
Growth Reel prompt — follower-first, non-branded cinematic content.

This is the GROWTH TRACK: coffee-culture content designed purely to grow
followers. No jar, no logo, no brand mention beyond the posting account.
Opposite rules from the brand track — see GROWTH_MODE_CONTEXT in brand_guard.
"""
from content_generator.rotation import get_todays_viral_idea

GROWTH_TOPICS = [
    "Why coffee tastes bitter — the mistake almost everyone makes",
    "What baristas actually think when you order instant coffee",
    "The Rs 200-a-week habit nobody calculates",
    "How coffee is graded — and why you never see the grade on the pack",
    "The 30-day black coffee experiment",
    "Why cafe coffee and home coffee will never taste the same",
    "What freeze-drying actually does to a coffee bean",
    "The morning routine of people who never feel groggy",
    "Coffee myths your parents taught you",
    "Why the first sip always tastes the best — the science",
    "What happens to your brain 20 minutes after coffee",
    "The history of coffee in India nobody tells",
    "Why some coffee smells amazing but tastes flat",
    "The one thing coffee experts disagree on",
    "How much caffeine is actually in your cup",
    "Why hot water temperature changes everything",
    "The psychology of why we drink coffee at work",
    "Slow mornings vs rushed mornings — a visual essay",
    "What your coffee order says about you",
    "The most expensive coffee in the world vs yours",
    # Founder track — people follow people more than products
    "Why I started a coffee brand when everyone said the market was full",
    "The biggest mistake I made building a food brand in India",
    "What nobody tells you about competing with giant FMCG brands",
    "The day I read a competitor's ingredient label and got angry",
    "Bootstrapping a coffee brand: what Rs 0 in VC funding teaches you",
    "The hardest lesson from my first year selling coffee in India",
    "Why I print what we DON'T add on our label — a founder's reasoning",
    "What running a coffee brand taught me about Indian consumers",
]

GROWTH_FORMATS = [
    "mini documentary", "cinematic B-roll essay", "macro shot ASMR",
    "myth vs reality", "expectation vs reality", "30-day experiment story",
    "POV morning routine", "visual explainer", "unexpected comparison",
    "hidden facts listicle",
    "talking-head direct-to-camera (founder voice, one strong claim, no B-roll crutch)",
    "reverse-qualifier ('this is NOT for you if...' — exclusion drives curiosity)",
    "value-unlock (tease a free resource; commenting a keyword is how to get it)",
    "borrowed meme format (a relatable reaction clip + coffee-truth text overlay, "
    "low production; stays brand-safe, never off-colour)",
]

# Every Nth day is a value-unlock reel — the highest comment-driver, but only
# works because a REAL resource backs the promise (see assets/lead_magnets.py).
_VALUE_UNLOCK_EVERY = 4


def build(day: int, avoid: str = "") -> str:
    topic  = GROWTH_TOPICS[day % len(GROWTH_TOPICS)]
    fmt    = GROWTH_FORMATS[day % len(GROWTH_FORMATS)]

    # Value-unlock day: force the format and hand the LLM the real resource
    unlock_block = ""
    if day % _VALUE_UNLOCK_EVERY == 0:
        from content_generator.assets.lead_magnets import get_todays_lead_magnet
        lm = get_todays_lead_magnet(day)
        fmt = "value-unlock (comment-to-receive a free resource)"
        unlock_block = f'''
VALUE-UNLOCK MODE (today's highest-priority mechanic):
This reel gives away a REAL free resource. Build the whole reel around teasing
it, then make commenting the keyword the way to receive it.
- Keyword to comment: {lm['keyword']}
- What the reel promises: {lm['promise']}
- Do NOT reveal the full resource in the reel — the value is unlocked by commenting.
- CTA must be: "Comment {lm['keyword']} and I'll send it to you."
- The founder replies personally with the resource (no auto-DM). Set
  comment_trigger to exactly: "Comment {lm['keyword']} and I'll send you {lm['promise']}."
'''

    text = f"""GROWTH TRACK ASSET — follower-first, non-branded. GROWTH_MODE_CONTEXT rules apply.

Generate ONE complete growth-track Instagram Reel about coffee culture.
Return a single JSON object.

{avoid}

TODAY'S TOPIC: {topic}
FORMAT: {fmt}
{unlock_block}

HARD RULES:
- NO Purity Beans mention. NO jar. NO logo. NO product. NO website. NO buying language.
- This must look like a Netflix documentary clip or Apple ad, never an advertisement.
- Something visually changes every 2-3 seconds.
- Hook lands in 2 seconds.
- English only. Never invent statistics — use "many people" not fake percentages.
- CTA is follow/save/share/comment ONLY.

{{
  "id": "growth_reel",
  "track": "growth",
  "viral_idea": "One sentence: the core idea and why people will share it",
  "psychology_used": ["2-4 triggers from: curiosity gap, open loop, identity, contrarian, myth bust, transformation, emotional contrast, hidden secret"],
  "hook_options": [
    "12 alternate opening lines across 4 distinct modes (3 of each, output as a flat list):",
    "1-3. Tension (immediate friction/conflict)",
    "4-6. Counterintuitive Claim (contrarian truth)",
    "7-9. Exact Feeling (names a specific person's exact feeling/situation)",
    "10-12. Open Loop (opens a curiosity loop)"
  ],
  "chosen_hook": "The strongest of the 10 — the one the reel opens with",
  "title_options": ["3 alternate titles for A/B testing"],
  "script": [
    {{"time": "0-2s",  "beat": "pattern interrupt", "on_screen": "4 WORDS MAX", "voiceover": "The chosen hook, spoken", "visual": "exact shot description"}},
    {{"time": "2-6s",  "beat": "curiosity",          "on_screen": "...", "voiceover": "...", "visual": "..."}},
    {{"time": "6-15s", "beat": "story",              "on_screen": "...", "voiceover": "...", "visual": "..."}},
    {{"time": "15-25s","beat": "value",              "on_screen": "...", "voiceover": "...", "visual": "..."}},
    {{"time": "25-35s","beat": "unexpected insight", "on_screen": "...", "voiceover": "...", "visual": "..."}},
    {{"time": "35-45s","beat": "payoff",             "on_screen": "...", "voiceover": "...", "visual": "..."}},
    {{"time": "45-55s","beat": "soft CTA",           "on_screen": "FOLLOW FOR MORE", "voiceover": "...", "visual": "..."}}
  ],
  "ai_image_prompts": [
    "3-5 paste-ready cinematic image prompts. Photographic (never 'render'), natural light, macro detail, steam/texture/hands/beans. 9:16 vertical. Each prompt MUST include realism ingredients: skin pores if hands/faces present, one light source with correct shadows, natural grain, a lived-in imperfection (water ring, crumbs, steam fog on surface), slightly off-center framing. BANNED words: perfect, flawless, 3D, render, CGI, illustration. NO labels, NO products framed as ads, NO logos, NO text in image."
  ],
  "ai_video_prompts": [
    "3-5 matching motion prompts with real physics: steam disperses, liquid has weight, humans breathe with micro blinks. Slow motion or subtle handheld, 24fps film feel, something changes every 2-3s. Faces stay stable — no morphing."
  ],
  "audio": {{"plan": "Music mood and the one sound-design moment (e.g. pour at 6s)", "source": "generated"}},
  "sound_suggestion": "Same music mood in one line — voice-forward, no lyric clash",
  "loop_note": "One sentence: how the last frame connects back to the opening shot so the reel can loop",
  "text_overlay_style": "Subtitle/overlay treatment — font energy, when it changes",
  "caption": "120-200 words. Personal, curious, documentary voice. Zero selling. Ends with a question that invites comments.",
  "cta_options": ["3 soft CTAs for A/B testing — follow/save/share/comment style only"],
  "comment_trigger": "A question or opinion-bait line that demands a response",
  "save_trigger": "Why someone bookmarks this",
  "share_trigger": "Why sharing this feels like doing a friend a favor",
  "hashtags": "25 hashtags: 5 large (#coffee), 5 medium, 5 small, 5 niche, 5 India-local. NO brand hashtags.",
  "seo_keywords": ["5-8 search phrases people actually type"],
  "emotion_created": "The single dominant emotion: awe/curiosity/joy/nostalgia/surprise/comfort",
  "posting_time": "Best IST slot for this content type",
  "why_this_can_go_viral": "2-3 sentences of honest reasoning",
  "predicted_weak_point": "The one thing most likely to make people scroll away — so it can be fixed in edit",
  "story_version": "How to cut this into a 15s Instagram Story with a poll or slider",
  "shorts_version": "What changes for YouTube Shorts (title with search keyword, tighter cut)"
}}"""
    from content_generator.prompts.piece_craft import craft_block
    return text + "\n\n" + craft_block("growth_reel")


# Instagram-native V2 rules (shared growth/creative contract)
from content_generator.prompts.instagram_native import INSTAGRAM_NATIVE_RULES
