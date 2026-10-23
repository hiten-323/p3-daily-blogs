"""Instagram single-image post prompt — full publish-ready asset."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import COMMERCIAL_EMOTIONS, WEBSITE_URL

HASHTAG_25 = (
    "#Coffee #CoffeeLover #InstantCoffee #MorningCoffee #CoffeeTime "
    "#PremiumCoffee #GlassJar #GourmetCoffee #PureCoffee #CoffeeCommunity "
    "#IndianCoffee #CoffeeIndia #MadeInIndia #IndianBrands #SupportIndianBrands "
    "#CoffeeAddict #CoffeeDaily #CoffeeGram #CoffeeCulture #CoffeeLife "
    "#PurityBeans #PurityBeansCoffee #PurityBeansExperience #BrewPure #PureCoffeeExperience"
)


def build(day: int, avoid: str) -> str:
    emotion = COMMERCIAL_EMOTIONS[day % len(COMMERCIAL_EMOTIONS)]

    prompt = f"""{brand_block()}

Generate ONE complete publish-ready Instagram feed post (single image) for Purity Beans. Return a single JSON object.

{avoid}

EMOTION TO EVOKE: {emotion[0]} — {emotion[1]}

FOLLOW-GROWTH SLOT — value first:
- Teach one specific craft point, myth, or ritual in the first half. The follow is earned by that lesson.
- No shop, price, offer, discount, buy, or order language anywhere in the caption or CTA.
- Purity Beans appears only as a soft end card: one true jar fact, then Follow @purepantryprovisions.
- The first line is a specific, surprising hook. A generic how-to title or a sales claim fails.

ABSOLUTE RULES:
- NEVER invent statistics or percentages
- NEVER make medical claims
- Caption MUST be 150-250 words
- 'Purity Beans' MUST appear once, near the end
- '{WEBSITE_URL}' may appear once in the soft end card, never as a shop command
- comment_trigger, save_trigger, share_trigger, hashtags are MANDATORY

{{
  "caption": "HOOK LINE that names a specific coffee moment (max 12 words, no emoji).\\n\\nTeach the lesson first: the tension, the turn, then the payoff. A reader should be able to use the idea with any cup. Only after the payoff, one soft end card: Purity Beans, one true fact about today's jar (Ultra Blend is 70% coffee and 30% chicory; freeze-dried is only Purica and Purista; agglomerated is only Bold and Prima). Do not promote Prima.\\n\\nFollow @purepantryprovisions for the next check you can use tomorrow.\\n\\nThis caption must be 150-250 words. Paste-ready. Value first. No shop language.",
  "cta": "Follow @purepantryprovisions for the next coffee lesson. {WEBSITE_URL}",
  "comment_trigger": "Comment LABEL if you want the next check for reading a coffee jar.",
  "save_trigger": "Save this post before your next grocery run.",
  "share_trigger": "Share with someone who starts every morning with coffee.",
  "image_prompt": "Detailed image prompt — authentic Purity Beans jar photo from brand_assets/ (puritybeans_*.png), dark marble surface, warm amber studio light, premium editorial FMCG photography, 1080x1080. No text in image. Must strictly feature real jar photo, never generic coffee jars.",
  "image_alt": "Purity Beans glass jar — name the jar, do not call Ultra Blend pure coffee",
  "post_type": "one of: product-truth / founder-moment / customer-story / cultural-hook / myth-busting",
  "hook_line": "The first line of the caption repeated here — must stop scroll before the More button cuts it",
  "seo_keywords": ["premium instant coffee", "gourmet instant coffee", "freeze dried coffee", "coffee without preservatives", "pure instant coffee india", "instant coffee brand india"],
  "hashtags": "{HASHTAG_25}"
}}"""
    from content_generator.prompts.piece_craft import craft_block
    return prompt + "\n\n" + craft_block("instagram_post")


# Instagram-native V2 rules (shared growth/creative contract)
from content_generator.prompts.instagram_native import INSTAGRAM_NATIVE_RULES
