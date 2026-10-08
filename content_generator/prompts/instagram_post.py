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

    return f"""{brand_block()}

Generate ONE complete publish-ready Instagram feed post (single image) for Purity Beans. Return a single JSON object.

{avoid}

EMOTION TO EVOKE: {emotion[0]} — {emotion[1]}

ABSOLUTE RULES:
- NEVER invent statistics or percentages
- NEVER make medical claims
- Caption MUST be 150-250 words
- 'Purity Beans' MUST appear in caption
- '{WEBSITE_URL}' MUST appear in caption and CTA
- comment_trigger, save_trigger, share_trigger, hashtags are MANDATORY
- The first line must stop a scroll in under 2 seconds. A generic how-to title fails that test.

{{
  "caption": "HOOK LINE that stops the scroll (max 12 words, no emoji).\\n\\nShort story or insight coffee lovers relate to. Introduce Purity Beans naturally. Explain why real coffee drinkers should care. Mention: Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. Purica is freeze-dried. Prima is Premium Agglomerate.\\n\\nShop now: {WEBSITE_URL}\\n\\nThis caption must be 150-250 words. Paste-ready. Emotional storytelling with brand facts woven in naturally.",
  "cta": "Direct action with {WEBSITE_URL}",
  "comment_trigger": "Comment COFFEE if you are a real coffee lover who refuses to drink chicory.",
  "save_trigger": "Save this post before your next grocery run.",
  "share_trigger": "Share with someone who starts every morning with coffee.",
  "image_prompt": "Detailed image prompt — authentic Purity Beans jar photo from brand_assets/ (puritybeans_*.png), dark marble surface, warm amber studio light, premium editorial FMCG photography, 1080x1080. No text in image. Must strictly feature real jar photo, never generic coffee jars.",
  "image_alt": "Purity Beans glass jar — name the jar, do not call Ultra Blend 100% coffee",
  "post_type": "one of: product-truth / founder-moment / customer-story / cultural-hook / myth-busting",
  "hook_line": "The first line of the caption repeated here — must stop scroll before the More button cuts it",
  "seo_keywords": ["premium instant coffee", "gourmet instant coffee", "freeze dried coffee", "coffee without preservatives", "pure instant coffee india", "instant coffee brand india"],
  "hashtags": "{HASHTAG_25}"
}}"""


# Instagram-native V2 rules (shared growth/creative contract)
from content_generator.prompts.instagram_native import INSTAGRAM_NATIVE_RULES
