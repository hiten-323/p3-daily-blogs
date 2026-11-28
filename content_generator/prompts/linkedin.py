"""LinkedIn post prompt — B2B, founder voice, short hook before 'see more'."""
from content_generator.prompts.brand import brand_block
from content_generator.rotation import LINKEDIN_SEO_KEYWORDS

HASHTAG_SET = "#PurityBeans #FMCGIndia #D2CIndia"


def build(angle: tuple, avoid: str, day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE complete LinkedIn post for Purity Beans (Pure Pantry Provisions). Return a single JSON object.

{avoid}

KNOWLEDGE ANGLE: [{angle[0]}] — {angle[1]}

VOICE AND AUDIENCE:
Write in the authentic voice of Hiten Jain, Founder of Pure Pantry Provisions (makers of Purity Beans).
This is a B2B post. Speak to office pantry buyers, HoReCa / cafe operators, corporate gifting managers, distributors and retail buyers in India. Do not write a consumer 'grocery run' caption.

FORMAT (LinkedIn feed):
- The hook is the first 1-2 lines and MUST fit in 200 characters or fewer so the tension is visible before LinkedIn's '...see more' fold. 20-200 characters. No emojis.
- Body is 120-200 words. Short paragraphs (1-2 sentences). Mobile-readable.
- Mention at most one featured SKU in a single short fact line. If Ultra Blend is mentioned, disclose 70% coffee / 30% chicory in the same breath and never call Ultra Blend 'pure'.
- Freeze-dried applies only to Purica and Purista. Agglomerated applies only to Bold and Prima.
- Exactly ONE call to action, and it must be B2B: e.g. 'Comment OFFICE / HORECA / GIFTING / DISTRIBUTION and I'll share the trade sheet' or 'DM me DISTRIBUTION'.
- Do NOT write 'Follow @purepantryprovisions'. That is an Instagram handle and does not belong on LinkedIn.
- Do NOT write consumer CTAs ('Save this before your next grocery run', 'Shop now').
- Do NOT put any URL in hook, body, brand_bridge, closing_question, cta, or hashtags. The store link is posted as the first comment by the publisher.
- At most 3 hashtags. Always include #PurityBeans. Add at most two relevant tags such as #HoReCa #CorporateGifting #FMCGIndia #D2CIndia. No more.
- 'Purity Beans' must appear in the post.

TRUTH RULES:
- No health claims, no knocking competitors, no free samples, no fabricated prices, stock, reviews, metrics or urgency.
- No banned wording: '100%', 'fresh', 'lab tested', 'single-origin', or any 'bean' / 'beans' wording.
- Do not invent anecdotes, named people, cities, contracts, co-packers, or quotations unless they are supplied as verified founder facts in this prompt. If you need a story, frame an observation ('What we check before a SKU ships…') rather than a dramatised scene.
- Do not repeat the 'failed pilot batch / walked away from a contract / the label is the only contract' premise. Find a new idea for this angle.
- Prices and shipping lines only if a live Shopify figure is provided in this prompt; otherwise omit them.
- No medical claims. No invented revenue or customer counts.

WEAVE THESE SEARCH KEYWORDS NATURALLY (without stuffing, and without putting a URL in the post):
{LINKEDIN_SEO_KEYWORDS}

{{
  "angle": "{angle[0]}",
  "hook": "1-2 line hook, 20-200 characters, tension or insight before '...see more'. No emojis. No URL.",
  "body": "120-200 words. Short paragraphs. B2B. One featured SKU fact line if needed. No URL.",
  "brand_bridge": "Optional 1-sentence bridge to Purity Beans. No URL.",
  "closing_question": "Optional one question for pantry, HoReCa, gifting or distribution buyers. No URL.",
  "cta": "Exactly one B2B CTA (Comment or DM OFFICE/HORECA/GIFTING/DISTRIBUTION). No handle, no grocery line, no URL.",
  "hashtags": "{HASHTAG_SET}",
  "image_prompt": "Use a real Purity Beans product photograph of the featured jar; do not invent a label."
}}"""
