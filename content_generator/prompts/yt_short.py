"""YouTube Shorts prompt — full publish-ready asset."""
import json

from content_generator.prompts.brand import brand_block
from content_generator.rotation import COMMERCIAL_EMOTIONS, WEBSITE_URL, get_todays_viral_idea

# Every scenes[] object. A missing key fails YoutubeShortSchema and burns a ladder attempt.
SCENE_FIELDS = ("scene", "type", "duration_s", "on_screen", "spoken", "visual_direction")

_SCENE_EXAMPLE = {
    "scene": 1,
    "type": "problem",
    "duration_s": 5,
    "on_screen": "READ THE JAR",
    "spoken": "The label says what the cup actually is.",
    "visual_direction": "Close-up of the jar label in warm light",
}


def scene_contract() -> str:
    """Hard scene schema for the generator and for ladder rewrites."""
    fields = ", ".join(SCENE_FIELDS)
    return (
        "REQUIRED SCENE FIELDS: every object in scenes MUST include all of these keys: "
        f"{fields}. Do not omit any of them. Do not leave any of them as an empty string. "
        "scene is an integer, duration_s is a number of seconds, and on_screen, spoken, "
        "and visual_direction are non-empty strings. "
        "Example of one complete scene object:\n"
        + json.dumps(_SCENE_EXAMPLE, indent=2)
    )


def build(product: str, day: int) -> str:
    emotion   = COMMERCIAL_EMOTIONS[day % len(COMMERCIAL_EMOTIONS)]
    companion = get_todays_viral_idea(day + 15)

    prompt = f"""{brand_block()}

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
- Bold is agglomerated pure coffee. You must not call Bold freeze-dried. Purica and Purista are freeze-dried. Do not name a process for Ultra Blend. Never write the word fully.

{scene_contract()}

{{
  "product": "{product}",
  "tagline": "A new ad tagline — max 6 words — NOT the brand tagline",
  "emotion_arc": "{emotion[0]}",
  "hook": "Specific surprising awe hook — max 10 words. Name a concrete jar, clock time, or contradiction. Never open with Most people never / Most people don't / Did you know.",
  "scenes": [
    {{"scene": 1, "type": "problem",   "duration_s": 5, "on_screen": "4 WORDS MAX — one specific moment", "spoken": "8-12 words — the problem, with stakes, no product mention", "visual_direction": "Specific shot the viewer recognises"}},
    {{"scene": 2, "type": "tension",   "duration_s": 5, "on_screen": "4 WORDS MAX — the stakes rise", "spoken": "8-12 words — what goes wrong if they keep doing it", "visual_direction": "The tension, closer, not a product dump"}},
    {{"scene": 3, "type": "turn",      "duration_s": 6, "on_screen": "4 WORDS MAX — the unexpected turn", "spoken": "8-12 words — the fact they did not expect", "visual_direction": "The turn: label, spoon, or cup, still tense"}},
    {{"scene": 4, "type": "payoff",    "duration_s": 7, "on_screen": "4 WORDS MAX — the hook settles", "spoken": "Pay off the hook before any CTA. Bold, Purista, Purica, and Prima are pure coffee. Ultra Blend is a smooth 70% coffee, 30% chicory milk coffee.", "visual_direction": "The payoff, then the jar only after the answer is clear"}},
    {{"scene": 5, "type": "cta",       "duration_s": 5, "on_screen": "SUBSCRIBE FOR THE NEXT", "spoken": "Subscribe for the next coffee truth. p3online.in.", "visual_direction": "Hold the payoff image, subscribe cue last"}}
  ],
  "cta": "Subscribe for daily pure coffee craft. Explore pure coffee jars at {WEBSITE_URL}",
  "title": "YouTube Shorts title — max 60 chars, includes SEO keyword",
  "description": "Purity Beans. Bold, Purista, Purica, and Prima are pure coffee. Ultra Blend is a smooth 70% coffee, 30% chicory milk coffee. Purica is freeze-dried. Prima is Premium Agglomerate. Shop now: {WEBSITE_URL} #PurityBeans #InstantCoffee #PureCoffee #CoffeeIndia",
  "tags": ["purity beans", "premium instant coffee", "freeze dried coffee", "agglomerated coffee", "coffee without preservatives", "pure instant coffee india", "gourmet instant coffee", "indian coffee brand"],
  "audio_direction": "Music bed genre + tempo + voiceover tone (Indian accent, gender, age). Sound design cues.",
  "edit_pacing": "Cut timing per scene — tension scenes cut faster, hold the payoff before the CTA"
}}"""
    from content_generator.prompts.piece_craft import craft_block
    return prompt + "\n\n" + craft_block("yt_short")
