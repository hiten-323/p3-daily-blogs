"""Instagram Carousel prompt — full publish-ready asset."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL, get_todays_viral_idea

HASHTAG_25 = (
    "#Coffee #CoffeeLover #InstantCoffee #MorningCoffee #CoffeeTime "
    "#PremiumCoffee #GlassJar #GourmetCoffee #PureCoffee #CoffeeCommunity "
    "#IndianCoffee #CoffeeIndia #MadeInIndia #IndianBrands #SupportIndianBrands "
    "#CoffeeAddict #CoffeeDaily #CoffeeGram #CoffeeCulture #CoffeeLife "
    "#PurityBeans #PurityBeansCoffee #PurityBeansExperience #BrewPure #PureCoffeeExperience"
)


# Carousels are the highest save/comment surface — run the value-unlock here
# too, offset from the reel so the feed never has two "comment X" posts in a row.
_UNLOCK_EVERY = 4
_UNLOCK_OFFSET = 2


def build(mech: tuple, avoid: str, day: int = 0) -> str:
    viral_idea = get_todays_viral_idea(day)

    unlock_block = ""
    if (day + _UNLOCK_OFFSET) % _UNLOCK_EVERY == 0:
        from content_generator.assets.lead_magnets import get_todays_lead_magnet
        lm = get_todays_lead_magnet(day)
        unlock_block = f'''
VALUE-UNLOCK CAROUSEL (today's highest-priority mechanic):
The final slide gives away a REAL free resource in exchange for a comment.
- Keyword to comment: {lm['keyword']}
- What it unlocks: {lm['promise']}
- Slides 1-N teach enough to prove the resource is worth having, but do NOT
  give away the resource itself.
- FINAL SLIDE heading must be: "COMMENT {lm['keyword']}"
  body: "Comment {lm['keyword']} and I'll send you {lm['promise']}."
- Set comment_trigger to exactly: "Comment {lm['keyword']} and I'll send you {lm['promise']}."
- The founder replies personally with the resource (no auto-DM).
'''

    return f"""{brand_block()}{unlock_block}

Generate ONE complete publish-ready Instagram Carousel for Purity Beans. Return a single JSON object.

{avoid}

SAVE MECHANIC: [{mech[0]}] — {mech[1]}
TODAY'S VIRAL CONTENT ANGLE: {viral_idea}
Every slide must make the viewer think: I need to save this for later.
PURPOSE: Maximize saves and shares through comparison, myth-busting, coffee tips, education, or buying guide.

SUBJECT TEST (mandatory before writing):
Ask: Is this something urban Indian coffee drinkers are curious about but nobody has explained simply?
If yes → proceed. If no → reframe until it passes. The best carousel design cannot save a topic nobody cares about.

PSYCHOLOGY REQUIREMENT:
Pick ONE primary frame from the PSYCHOLOGY FRAMES list above.
Put its id in "psychology_frame". The frame must drive the cover hook, the emotional arc, and the share/save triggers.
Jar facts support the frame — they are not the frame. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. Never apply the 100% coffee line to Ultra Blend.

ABSOLUTE RULES:
- NEVER invent statistics or percentages
- NEVER make medical claims
- Minimum 6 slides, maximum 8 slides
- Final slide MUST include CTA + {WEBSITE_URL} + mention of Purity Beans
- caption MUST be present and 200-300 words. An empty caption is invalid.
- The cover heading must stop a scroll in under 2 seconds. A generic title fails that test.
- comment_trigger, save_trigger, share_trigger, hashtags, psychology_frame are MANDATORY

{{
  "id": "carousel_1",
  "psychology_frame": "one of: revelation | clean_label | ritual | sensory | social_currency | accessible_premium | certainty",
  "save_mechanic": "{mech[0]}",
  "title": "7 WORDS MAX — curiosity + utility that forces the save",
  "slides": [
    {{"slide": 1, "heading": "COVER HOOK — 6 WORDS MAX", "body": "Pattern interrupt. Promise that forces the swipe. What they will learn.", "visual": "Dark marble, Purity Beans jar hero, single gold beam"}},
    {{"slide": 2, "heading": "The Problem", "body": "What most people do not know about their daily coffee. Specific, relatable, not statistical.", "visual": "Dark bg, white text, one visual accent"}},
    {{"slide": 3, "heading": "Myth Busted", "body": "The assumption everyone holds that is actually wrong. Contrarian and surprising.", "visual": "Ingredient or product detail close-up"}},
    {{"slide": 4, "heading": "The Revelation", "body": "The I-did-not-know-this moment. Specific truth about coffee purity vs adulterants.", "visual": "Before/after or label close-up"}},
    {{"slide": 5, "heading": "Why It Matters", "body": "Specific Indian scenario — what this means for a real coffee lover in India.", "visual": "Indian person + coffee, natural light"}},
    {{"slide": 6, "heading": "Purity Beans Difference", "body": "Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. Purica is freeze-dried. Prima is Premium Agglomerate. Shop {WEBSITE_URL}", "visual": "Product hero — full Purity Beans jar, cinematic, gold accent"}},
    {{"slide": 7, "heading": "Save & Follow", "body": "Save this guide for your next coffee run. Follow @puritybeans so you never drink fake coffee again. Visit {WEBSITE_URL}", "visual": "Brand CTA — dark bg, Purity Beans logo, minimal gold"}}
  ],
  "caption": "HOOK LINE that stops the scroll.\\n\\nWhat you will learn in this carousel (preview the value). Tell the story of why this matters to a real coffee lover. Mention Purity Beans naturally. Include: Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. Purica is freeze-dried 100% Arabica. Prima is Premium Agglomerate 100% Arabica.\\n\\nThis is a 200-300 word paste-ready caption with emotional storytelling and brand facts.\\n\\nSave this post & Follow @puritybeans for daily coffee truths. Shop now: {WEBSITE_URL}",
  "cta": "Save this post + Follow @puritybeans. Explore pure coffee at {WEBSITE_URL}",
  "comment_trigger": "Comment SAVE if you are switching to real coffee this week.",
  "save_trigger": "Save this carousel — it will change how you buy coffee forever.",
  "share_trigger": "Share with someone who deserves to know what is really in their coffee.",
  "seo_keywords": ["premium instant coffee", "gourmet instant coffee", "freeze dried coffee", "agglomerated coffee", "coffee without preservatives", "pure instant coffee india", "instant coffee brand india"],
  "hashtags": "{HASHTAG_25}"
}}"""


# Instagram-native V2 rules (shared growth/creative contract)
from content_generator.prompts.instagram_native import INSTAGRAM_NATIVE_RULES
