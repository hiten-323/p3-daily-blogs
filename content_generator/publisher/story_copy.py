"""
Daily Instagram story copy.

Stories were shipping the same two hardcoded lines every day
("REAL COFFEE. ZERO CHICORY." / "Reply and tell me how you take your coffee")
because:

  - story generation is an extended-content LLM task
  - evergreen fallback never emitted a stories key
  - post_story treated missing story_1 as a brand slogan

This module resolves a headline + reply line from today's approved copy
(or a day-rotated label-safe bank) so the jar can change AND the words can.
"""
from __future__ import annotations

STORY_COPY_BANK: list[tuple[str, str]] = [
    ("READ THE BACK", "Commercial jars often hide root fillers. Demand 100% pure bean."),
    ("ONE INGREDIENT", "100% Pure Coffee. Zero fillers, zero compromise."),
    ("TURN THE JAR", "The real truth is on the back panel. Check yours tonight."),
    ("STOP DRINKING ROOT", "Real coffee lovers drink 100% pure beans. Taste the difference."),
    ("FRONT IS MARKETING", "Flip your jar around. Is it pure coffee or cheap root filler?"),
    ("CLEAN MORNING ENERGY", "No heavy crash. Pure Arabica & Robusta craft in every cup."),
    ("YOUR KITCHEN TEST", "Does your coffee leave muddy residue? Demand 100% pure."),
    ("BREW PURE", "Join real coffee lovers switching to 100% pure coffee."),
]

# The pair that printed identically for weeks. Tests ban it as a default.
_BANNED_DEFAULT_HEADLINE = "REAL COFFEE. ZERO CHICORY."
_BANNED_DEFAULT_SUB = "Reply and tell me how you take your coffee"


def _clean_line(value, max_words: int = 12) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if not text:
        return ""
    lower = text.lower()
    if lower.startswith("slide ") or lower.startswith("frame "):
        return ""
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    return text.strip(" -–—")


def _primary_piece(content: dict) -> tuple[dict, str]:
    reels = content.get("reels") or []
    if isinstance(reels, list) and reels and isinstance(reels[0], dict):
        return reels[0], "reel"
    carousel = content.get("carousel")
    if isinstance(carousel, dict) and (carousel.get("hook") or carousel.get("title")):
        return carousel, "carousel"
    post = content.get("instagram_post")
    if isinstance(post, dict) and (post.get("hook") or post.get("caption")):
        return post, "instagram_post"
    return {}, ""


def resolve_story_copy(content: dict | None, day: int = 0) -> dict:
    """
    Return {headline, sub, source} for the daily 9:16 story frame.

    Priority:
      1. Generated stories.story_1 headline / subtext / poll
      2. Today's reel overlay, then hook + comment trigger
      3. Today's carousel / feed hook + comment trigger
      4. Day-rotated STORY_COPY_BANK (label-safe, no offers, no stats)
    """
    content = content if isinstance(content, dict) else {}
    stories = content.get("stories") if isinstance(content.get("stories"), dict) else {}
    s1 = stories.get("story_1") if isinstance(stories.get("story_1"), dict) else {}

    headline = _clean_line(s1.get("headline"), max_words=6)
    sub = _clean_line(s1.get("subtext") or "", max_words=12)
    if not sub:
        poll = _clean_line(s1.get("poll_question"), max_words=12)
        if poll and poll.lower() != headline.lower():
            sub = poll
    source = "stories.story_1"

    # Recycled days take the bank, ahead of "today's" overlay.
    #
    # Evergreen fallback content is IDENTICAL every day — same reel, same
    # overlay, same comment trigger. Deriving story copy from it therefore
    # reprints one line forever: the same defect the hardcoded slogan had,
    # moved one tier up. Measured on this tree before this change, nine
    # consecutive fallback days all produced
    #   READ THE BACK / What does the label on your jar actually say?
    # because tier 2 always won, _attach_stories then wrote that into tier 1,
    # and the 8-line bank was unreachable on exactly the days it exists for —
    # which is every day, since no day has ever produced real generation.
    #
    # "Today's content" is only worth preferring when today's content is
    # actually today's. Genuinely generated days are untouched below.
    if not headline and _is_recycled(content):
        bank_h, bank_s = STORY_COPY_BANK[int(day or 0) % len(STORY_COPY_BANK)]
        return {"headline": bank_h, "sub": bank_s, "source": "story_bank.recycled"}

    if not headline:
        piece, origin = _primary_piece(content)
        overlay = _clean_line(piece.get("hook_text_overlay"), max_words=5)
        hook = _clean_line(
            piece.get("hook") or piece.get("hook_text") or piece.get("title"),
            max_words=8,
        )
        comment = _clean_line(piece.get("comment_trigger"), max_words=12)
        bank_h, bank_s = STORY_COPY_BANK[int(day or 0) % len(STORY_COPY_BANK)]
        if overlay:
            headline = overlay
            sub = comment or hook or bank_s
            source = f"{origin}.overlay"
        elif hook:
            headline = hook
            sub = comment or bank_s
            source = f"{origin}.hook"
        else:
            headline, sub, source = bank_h, bank_s, "story_bank"
    elif not sub:
        sub = STORY_COPY_BANK[int(day or 0) % len(STORY_COPY_BANK)][1]

    # Last-ditch only — still not the banned slogan pair.
    if not headline:
        headline, sub = STORY_COPY_BANK[int(day or 0) % len(STORY_COPY_BANK)]
        source = "story_bank"

    return {"headline": headline, "sub": sub, "source": source}



def _is_recycled(content: dict) -> bool:
    """True for emergency-fallback / recycled days, whose own copy is a constant."""
    if not isinstance(content, dict):
        return False
    if content.get("_recycled"):
        return True
    return str(content.get("_source") or "").startswith("emergency_fallback")


def stories_block_from_content(content: dict, day: int = 0) -> dict:
    """Attach a stories object so fallback days have the same shape as LLM days."""
    copy = resolve_story_copy(content, day=day)
    return {
        "story_1": {
            "type": "poll",
            "headline": copy["headline"],
            "subtext": copy["sub"],
            "poll_question": copy["sub"],
            "option_a": "Haven't checked",
            "option_b": "Read the back",
        }
    }
