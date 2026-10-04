"""YouTube Shorts prompt — full publish-ready asset."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import COMMERCIAL_EMOTIONS, WEBSITE_URL, get_todays_viral_idea


def build(product: str, day: int) -> str:
    emotion   = COMMERCIAL_EMOTIONS[day % len(COMMERCIAL_EMOTIONS)]
    companion = get_todays_viral_idea(day + 15)

    return f"""{brand_block()}

Generate ONE complete publish-ready YouTube Shorts script for Purity Beans. Return a single JSON object.

PRODUCT: {product}
EMOTION ARC: {emotion[0]} — {emotion[1]}
TARGET DURATION: 20-40 seconds
COMPANION CONCEPT (shared with today's Instagram Story — the same vertical
video is posted to both): {companion}
IMPORTANT: This concept is deliberately DIFFERENT from today's Instagram Reels.
Do not reuse the reels' hooks or angles.

ABSOLUTE RULES:
- NEVER invent statistics
- NEVER make medical claims
- 'Purity Beans' MUST appear in script and description
- '{WEBSITE_URL}' MUST appear in cta and description
- scenes.on_screen = text displayed on screen only (max 4 words per scene)
- scenes.spoken = voiceover only, no production notes

{{
  "product": "{product}",
  "tagline": "Fresh ad tagline — max 6 words — NOT the brand tagline",
  "emotion_arc": "{emotion[0]}",
  "hook": "Opening line that stops the skip — max 10 words, creates instant curiosity",
  "scenes": [
    {{"scene": 1, "type": "problem",        "duration_s": 5, "on_screen": "4 WORDS MAX — precise painful Indian moment",       "spoken": "8-12 words — raw first-person pain, no product mention",     "visual_direction": "Specific shot, lighting, real scene"}},
    {{"scene": 2, "type": "agitation",      "duration_s": 5, "on_screen": "4 WORDS MAX — the betrayal made visible",           "spoken": "8-12 words — the reveal that makes them angry or curious",  "visual_direction": "Label close-up or chicory/preservative reveal"}},
    {{"scene": 3, "type": "product_reveal", "duration_s": 8, "on_screen": "READ THE JAR",                        "spoken": "Bold, Purista, Purica, and Prima are 100% coffee. Ultra Blend is 70% coffee.", "visual_direction": "Slow Purity Beans jar reveal, gold light, steam"}},
    {{"scene": 4, "type": "benefit",        "duration_s": 5, "on_screen": "4 WORDS MAX — specific result",                    "spoken": "8-12 words — transformation tied to this specific product",  "visual_direction": "Person + mug, natural light, real energy"}},
    {{"scene": 5, "type": "cta",            "duration_s": 5, "on_screen": "SHOP P3ONLINE.IN",                                 "spoken": "Visit p3online.in — real coffee, no compromises.",          "visual_direction": "Static Purity Beans product, logo, URL held 2 seconds"}}
  ],
  "cta": "Visit {WEBSITE_URL} — Purity Beans. 100% coffee jars, and Ultra Blend at 70% coffee.",
  "title": "YouTube Shorts title — max 60 chars, includes SEO keyword",
  "description": "Purity Beans. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. Purica is freeze-dried. Prima is Premium Agglomerate. Shop now: {WEBSITE_URL} #PurityBeans #InstantCoffee #PureCoffee #CoffeeIndia",
  "tags": ["purity beans", "premium instant coffee", "freeze dried coffee", "agglomerated coffee", "coffee without preservatives", "pure instant coffee india", "gourmet instant coffee", "indian coffee brand"],
  "audio_direction": "Music bed genre + tempo + voiceover tone (Indian accent, gender, age). Sound design cues.",
  "edit_pacing": "Cut timing per scene — e.g. 1.5s cuts scenes 1-2, 3s hold on scene 3 reveal"
}}"""
