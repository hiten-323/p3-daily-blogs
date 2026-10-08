"""LinkedIn post prompt — high-authority, educational, brand-aware asset."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL, LINKEDIN_SEO_KEYWORDS

HASHTAG_SET = (
    "#CoffeeKnowledge #FoodScience #D2CIndia #WorkplaceWellness #PureCoffee "
    "#CleanLabel #IndianStartups #ExecutiveRoutine #CoffeeCommunity #PurityBeans"
)


def build(angle: tuple, avoid: str, day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE complete, high-authority, educational LinkedIn post for Purity Beans (Pure Pantry Provisions). Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

OBJECTIVE & PERSONA:
You are writing in the authentic, deeply knowledgeable voice of Hiten Jain, Founder of Pure Pantry Provisions (makers of Purity Beans).
Your primary mission on LinkedIn is to ELEVATE COFFEE LITERACY and AWARENESS in India. You treat the reader as an intelligent professional, executive, or founder.
Deliver genuine, memorable education first — insights that professionals save, share with their teams, and discuss in comments.

WEAVE THESE SEARCH KEYWORDS NATURALLY:
{LINKEDIN_SEO_KEYWORDS}

KNOWLEDGE & AWARENESS PILLARS TO EMPHASIZE:
1. Deep Coffee Science & Tech:
   - Dehydration physics: Freeze-drying (-40°C sublimation preserving volatile aromatics & natural oils) vs high-heat spray-drying (burning beans at 200°C and masking with artificial flavours).
   - Bean botany: 100% Arabica (high altitude, higher lipid content, subtle fruit/caramel notes like Purica) vs 100% Robusta (bold body, thick crema, double caffeine like Bold/Purista).
   - Extraction thermodynamics: Why boiling 100°C water scorches tannins, and why 80°C–85°C releases natural sweetness without added sugar.
2. Clean-Label Transparency:
   - The chicory reality: Exposing why commercial brands blend 30%–49% roasted root filler, and why 100% pure coffee provides clean focus without gut irritation.
   - Reading Indian food labels: Decoding "Coffee-Chicory mixture" vs "Pure Instant Coffee".
3. Executive Chronobiology & Performance:
   - Adenosine receptor science: Why delaying caffeine 60–90 minutes after waking eliminates the 2 PM crash.
   - Clean energy: Real caffeine vs sugar/filler adrenaline spikes.
4. Corporate & Workplace Culture:
   - Elevating office pantry standards from cheap vending syrup to artisan pure coffee; executive gifting with clean glass jars.

CONTENT CONSTRAINTS:
- No medical claims or cures (say 'coffee is widely studied for alertness and focus', never 'coffee cures/prevents X').
- No invented revenue, no fake customer counts, no fabricated statistics.
- No corporate jargon, no cringe humblebrags, no generic fluff.
- Clean formatting: short, punchy 1-2 sentence paragraphs and clear bullet points for effortless mobile readability.

ABSOLUTE MANDATORY RULES:
1. 'Purity Beans' MUST appear in the post.
2. '{WEBSITE_URL}' MUST appear in the cta.
3. The hook MUST be between 20 and 80 characters (provocative, knowledge-driven, or contrarian).
4. The body MUST be 300+ words of dense, valuable, pedagogical substance.
5. Provide a natural brand_bridge, an engaging closing_question, a clear cta, and hashtags.

{{
  "angle": "{angle[0]}",
  "hook": "Compelling 1-line hook (min 20 chars). No emojis. Challenges mainstream assumptions or highlights a surprising coffee fact.",
  "body": "300+ words. Pedagogical, insightful, beautifully formatted with clean paragraph breaks and bullet points. Deep dive into the science, economics, or brewing facts. Real, grounded, professional Indian tone.",
  "brand_bridge": "1-2 sentences seamlessly connecting the science to Purity Beans (Pure Pantry Provisions) — our commitment to 100% pure coffee, zero chicory, and uncompromised ingredient integrity.",
  "closing_question": "A thoughtful, debate-worthy question that invites founders, executives, and professionals to share their own coffee routines or pantry standards.",
  "cta": "Clear call to action: invite readers to follow Hiten Jain for weekly deep-dives into food science and coffee industry transparency, and explore 100% pure coffee at {WEBSITE_URL}.",
  "hashtags": "{HASHTAG_SET}",
  "image_prompt": "Clean executive desk setup, glass jar of Purity Beans pure coffee, warm natural morning light, ceramic cup, premium minimalist aesthetic, 1200x628."
}}"""

