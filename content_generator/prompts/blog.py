"""Blog post prompt."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL


def build(topic: str) -> str:
    return f"""{brand_block()}

Generate ONE blog post for Purity Beans. Return a single JSON object.

TOPIC: {topic}
AUDIENCE: Indians searching Google for coffee information.

{{
  "title": "50-60 chars — include instant coffee India or pure coffee. Must earn the click over 9 competitors.",
  "slug": "lowercase-hyphens-max-6-words",
  "meta_description": "150-160 chars — lead with the benefit or surprising fact. Include Purity Beans and India.",
  "focus_keyword": "Primary keyword used 3-5x naturally in body",
  "introduction": "2-3 sentences — fact, scenario, or question that makes the reader feel understood. Indian voice. Never say In today's world. Use the key introduction, not intro.",
  "body": "Plain text, at least 800 words (the schema rejects anything shorter). 5-7 sections. Arc: hook scenario → how to read an Indian instant-coffee label → which Purity Beans jar matches the question → brew tips → CTA. Name the jar. Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica. Prima / Premium Agglomerate is 100% Arabica and is not freeze-dried. Ultra Blend is 70% coffee and may be called lower caffeine; never call Ultra Blend 100% coffee or zero chicory. Mention Purity Beans and {WEBSITE_URL}. Use the key body, not body_html. Do not invent statistics, health outcomes, or certificates.",
  "conclusion": "Closing paragraph with the same brand facts and a link to {WEBSITE_URL}. This key is required. Do not omit it.",
  "tags": ["instant coffee", "pure coffee", "coffee benefits", "chicory free", "purity beans", "india coffee"],
  "image_alt": "Product + keyword + India context — under 125 chars"
}}"""
