"""Facebook post prompt — community-driven, relatable, native Facebook engagement."""
import copy
import json
import re

from content_generator.prompts.brand import brand_block
from content_generator.rotation import WEBSITE_URL

FB_HASHTAGS = "#PurityBeans #IndianCoffee #MorningCoffee #CoffeeLovers"
NATIVE_KEYS = ("angle", "hook", "body", "community_question", "cta", "hashtags")


def native_contract() -> str:
    """Shape the model must return. Article words stay above the key list.

    The suffix after "Return ONE JSON object" is the schema the model copies.
    Naming blog, section, or carousel fields there makes the next draft an article.
    """
    return (
        "This is a Facebook post, not a blog, article, or another platform's caption. "
        "Do not write an introduction, sections, slides, or a long article. "
        "If the rejection tells you to finish an article or add headings, ignore that and write the Facebook post. "
        "Return ONE JSON object with exactly these keys: "
        + json.dumps(list(NATIVE_KEYS))
        + ". "
        "hook: one complete conversational sentence, a household question or a relatable opener. "
        "body: 150 to 250 words, warm and spoken, finished sentences, paragraph breaks, no headings. "
        "community_question: one easy question people can answer in a comment. "
        "cta: Follow @purepantryprovisions and include the website. "
        "hashtags: a short set. "
        "The body must end on a complete sentence. "
        "Name Purity Beans and include one true brand fact for the featured jar. "
        "Purista is freeze-dried pure Robusta. Purica is freeze-dried pure Arabica. "
        "Bold is agglomerated pure coffee, not freeze-dried. "
        "Ultra Blend is 70% coffee and 30% chicory. Never call that jar no chicory, and never use a percent-purity claim. "
        "Do not name a process for Ultra Blend. "
        "Use only catalog prices. Do not invent a cup count."
    )


def regeneration_prompt(piece: dict, feedback: str, threshold: float, brand: str,
                        from_scratch: bool = False) -> str:
    """Native Facebook regen. The rejected article is not the source text."""
    featured = (piece or {}).get("featured_product") or "the featured Purity Beans jar"
    reasons = re.sub(r"\s+", " ", str(feedback or ""))[:600]
    source = ""
    if not from_scratch and isinstance(piece, dict):
        slim = {
            key: piece[key] for key in NATIVE_KEYS
            if isinstance(piece.get(key), str) and piece.get(key).strip()
        }
        if piece.get("featured_product"):
            slim["featured_product"] = piece["featured_product"]
        source = (
            "ORIGINAL NATIVE COPY (rewrite it; if it reads like an article or stops mid-sentence, discard it):\n"
            + json.dumps(slim, ensure_ascii=False)[:2500]
            + "\n\n"
        )
    return (
        f"{brand}\n\n"
        f"TASK: Write a native Facebook post for {featured}. "
        f"It must pass an editorial score of {threshold} and the facebook_post format rule: "
        "conversational, relatable household angle, a question that is easy to answer.\n"
        f"{source}"
        f"REJECTION TO FIX:\n{reasons}\n"
        "Do not reuse a banned claim, a wrong price, or a sentence that was cut off. "
        "Per-cup price and cup count belong only to Ultra Blend, in a sentence that names Ultra Blend. "
        "If the featured jar is anything else, omit the figure.\n"
        f"{native_contract()}\n"
        "Do not include an editorial_score. Return ONLY the JSON object."
    )


_ARTICLE_KEYS = (
    "blog_post", "sections", "introduction", "carousel", "carousel_slides", "slides",
)
_DROP_KEYS = _ARTICLE_KEYS + (
    "instagram_post", "conclusion", "intro", "body_html", "meta_description",
    "frames", "script", "scenes", "linkedin_post", "threads_post", "reels", "yt_short", "title",
)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _kept(value) -> bool:
    if value is None or isinstance(value, str):
        return bool(_text(value))
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def sentence_complete(text: str) -> bool:
    """A trailing URL or hashtag is finished. A chopped tail is not."""
    raw = _text(text)
    if len(raw) < 40 or raw[-1] in ",:;/-–—" or not re.search(r"[.!?…]", raw):
        return False
    return bool(re.search(r"(?:[.!?…][\"')\]]*|https?://\S+|p3online\.in\S*|#\w+)\s*$", raw, re.I))


def _nested_copy(piece: dict) -> tuple[str, str]:
    nested = piece.get("facebook_post")
    if isinstance(nested, str):
        return "", nested.strip()
    if isinstance(nested, dict):
        hook = _text(nested.get("hook") or nested.get("headline"))
        body = _text(nested.get("body") or nested.get("text") or nested.get("content") or nested.get("caption"))
        return hook, body
    return "", ""


def normalize_facebook_piece(piece: dict) -> dict:
    """Drop a blog/carousel pack so the 8.0 judge scores the Facebook post."""
    if not isinstance(piece, dict):
        return piece
    body = _text(piece.get("body"))
    nested_hook, nested_body = _nested_copy(piece)
    if not sentence_complete(body):
        for candidate in (nested_body, _text(piece.get("text"))):
            if sentence_complete(candidate):
                body = candidate
                break
        else:
            if len(body) > 400:
                body = ""
    if body:
        piece["body"] = body
    hook = _text(piece.get("hook")) or nested_hook
    if not hook and sentence_complete(body):
        opening = body.split("\n", 1)[0].strip()
        end = re.search(r"[.!?]", opening)
        hook = opening[: end.end()] if end else opening[:180]
    if hook:
        piece["hook"] = hook
    question = _text(piece.get("community_question"))
    if question and len(_text(piece.get("comment_trigger"))) < 10:
        piece["comment_trigger"] = question
    if len(_text(piece.get("hashtags"))) < 10:
        piece["hashtags"] = FB_HASHTAGS
    if not sentence_complete(_text(piece.get("caption"))):
        piece.pop("caption", None)
    if isinstance(piece.get("facebook_post"), (str, dict)):
        piece.pop("facebook_post", None)
    for key in _DROP_KEYS:
        piece.pop(key, None)
    return piece


def _usable(raw: dict) -> bool:
    if not isinstance(raw, dict) or any(key in raw for key in _ARTICLE_KEYS):
        return False
    hook, body = _text(raw.get("hook")), _text(raw.get("body"))
    if len(hook) < 8 or len(body) < 40 or body[-1] in ",:;/-–—":
        return False
    return len(body) <= 400 or sentence_complete(body)


def accept_facebook_regen(improved: dict, original: dict | None = None) -> dict | None:
    """Keep a native rewrite. Reject an article pack or a mid-sentence body."""
    if not _usable(improved):
        return None
    merged: dict = {}
    if isinstance(original, dict):
        for key in ("featured_product", "objective", "primary_cta", "success_metric",
                    "day_number", "type", "regen_round"):
            if key in original and key not in improved:
                merged[key] = copy.deepcopy(original[key])
    for key, value in improved.items():
        if key in _DROP_KEYS or not _kept(value):
            continue
        merged[key] = copy.deepcopy(value)
    for key in NATIVE_KEYS:
        value = improved.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    normalize_facebook_piece(merged)
    if not _text(merged.get("hook")) or not _text(merged.get("body")):
        return None
    return merged


def build(angle: tuple, avoid: str = "", day: int = 0) -> str:
    return f"""{brand_block()}

Generate ONE original, relatable, community-engaging Facebook post for Pure Pantry Provisions / Purity Beans. Return a single JSON object.

{avoid}

COMMUNITY ANGLE: [{angle[0]}] — {angle[1]}

PLATFORM INTENT (FACEBOOK 2026):
- Audience: Indian families, professionals, and home coffee drinkers (25-50).
- Tone: Warm, relatable, authentic, conversational. Zero LinkedIn corporate jargon. Zero hard sales infomercials.
- Distribution Levers: Comments, shares with friends/family, and dwell time.
- Structure:
  1. Relatable Opening Hook: Connect with a shared Indian coffee experience or common morning habit.
  2. Insight / Story: A brewing tip, a household coffee moment, or what makes today's jar taste the way it does (never attack chicory).
  3. Conversation Starter: A question that compels people to comment their own habits or tag a family member.
  4. Follow & Explore CTA: Invite following the page for daily coffee truths, with website link.

{{
  "angle": "{angle[0]}",
  "hook": "Relatable 1-line hook that connects with everyday Indian coffee drinkers.",
  "body": "150-250 words. Warm, engaging, storytelling style. Discusses today's jar on its own merits, or brewing tips that anyone can try at home. Clear paragraph breaks.",
  "community_question": "A friendly, conversational question that asks about their morning routine, favorite mug, or family coffee debate.",
  "cta": "Follow our page for daily honest coffee tips. Discover pure coffee at {WEBSITE_URL}",
  "hashtags": "{FB_HASHTAGS}"
}}"""
