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

import re

STORY_COPY_BANK: list[tuple[str, str]] = [
    ("READ THE BACK", "Commercial jars often hide root fillers. Demand pure bean."),
    ("ONE INGREDIENT", "Pure Coffee. Zero fillers, zero compromise."),
    ("TURN THE JAR", "The real truth is on the back panel. Check yours tonight."),
    ("STOP DRINKING ROOT", "Real coffee lovers drink pure beans. Taste the difference."),
    ("FRONT IS MARKETING", "Flip your jar around. Is it pure coffee or cheap root filler?"),
    ("CLEAN MORNING ENERGY", "No heavy crash. Pure Arabica & Robusta craft in every cup."),
    ("YOUR KITCHEN TEST", "Does your coffee leave muddy residue? Demand pure coffee."),
    ("BREW PURE", "Join real coffee lovers switching to pure coffee."),
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


_BRAND = re.compile(r"purity\s+beans", re.I)
_BEAN = re.compile(r"\bbeans?\b", re.I)
_SINGLE_ORIGIN = re.compile(r"single[\s-]?origin", re.I)
_FRESH = re.compile(r"\bfresh\b", re.I)
_FREE_SAMPLE = re.compile(r"\bfree\s+(?:samples?|cups?|trials?)\b", re.I)
_KNOCK = re.compile(
    r"\bcompetitors?\b|\brival\s+brands?\b|commercial jars|root filler|stop drinking",
    re.I,
)
_PRIMA = re.compile(r"\bprima\b|premium\s+agglomerate", re.I)


def record_story_claim_lesson(reason: str) -> None:
    """Remember a process-match block so the next Story is not the same claim."""
    text = " ".join(str(reason or "").split())
    if not text:
        return
    try:
        from content_generator.core.obstacle_lessons import platform_for, record

        record(
            platform_for("stories"),
            "stories",
            "publish",
            "process_match",
            text,
            "Replace a process-match block with a compliant Story variant. Do not republish the same claim.",
        )
    except Exception:
        return


def _story_measured(piece: dict) -> bool:
    """True when this frame is already under the editorial / viral bar."""
    if not isinstance(piece, dict):
        return False
    if piece.get("ladder_exhausted"):
        return True
    return isinstance(piece.get("editorial_score"), dict) or isinstance(piece.get("viral_potential"), dict)


def _story_copy_allowed(headline: str, sub: str) -> bool:
    """Content rules for a replacement line. The brand name is not bean-wording."""
    text = f"{headline}\n{sub}"
    if _SINGLE_ORIGIN.search(text) or _FRESH.search(text) or _FREE_SAMPLE.search(text):
        return False
    if _KNOCK.search(text) or _PRIMA.search(text):
        return False
    return _BEAN.search(_BRAND.sub("", text)) is None


def _frame_copy(piece: dict) -> tuple[str, str]:
    """A story_1 line is capped at 6 words. Do not chop a longer frame into a fragment."""
    raw = " ".join(str(piece.get("headline") or piece.get("badge") or "").replace("\n", " ").split())
    if not raw or len(raw.split()) > 6:
        return "", ""
    headline = _clean_line(raw, max_words=6)
    sub = _clean_line(
        piece.get("subtext") or piece.get("body") or piece.get("fact") or piece.get("offer") or "",
        max_words=12,
    )
    return headline, sub


def _replacement_candidates(content: dict, day: int) -> list[tuple[str, str, str]]:
    stories = content.get("stories") if isinstance(content.get("stories"), dict) else {}
    found: list[tuple[str, str, str]] = []
    for key in ("story_2", "story_3", "story_4"):
        piece = stories.get(key)
        if not isinstance(piece, dict):
            continue
        headline, sub = _frame_copy(piece)
        if headline and sub:
            found.append((headline, sub, f"stories.{key}"))
    start = int(day or 0) % len(STORY_COPY_BANK)
    for offset in range(len(STORY_COPY_BANK)):
        headline, sub = STORY_COPY_BANK[(start + offset) % len(STORY_COPY_BANK)]
        found.append((headline, sub, "story_bank"))
    return found


def recover_claim_blocked_story(content: dict, day: int = 0) -> dict | None:
    """Swap a process-match-blocked story_1 for another line that passes the same check.

    Returns the installed copy, or None when the current line is already clear,
    when no compliant variant exists, or when story_1 is already scored. A scored
    frame is not replaced with an unscored line: that would skip the 8.0 bar.
    The process-match check is not modified.
    """
    if not isinstance(content, dict):
        return None
    from content_generator.core.process_match import process_match_findings
    from content_generator.core.product_truth import featured_product_name
    from content_generator.publisher.product_links import story_link_line

    featured = featured_product_name(content)
    current = resolve_story_copy(content, day)
    blocked = f"{current['headline']}\n{story_link_line(current['sub'])}"
    hits = process_match_findings(blocked, featured=featured)
    if not hits:
        return None
    record_story_claim_lesson(str(hits[0].get("reason") or "process match"))
    stories = content.get("stories") if isinstance(content.get("stories"), dict) else {}
    story_1 = stories.get("story_1") if isinstance(stories.get("story_1"), dict) else {}
    if _story_measured(story_1):
        return None
    blocked_headline = _clean_line(current.get("headline"), max_words=6).upper()
    for headline, sub, source in _replacement_candidates(content, day):
        if headline.upper() == blocked_headline:
            continue
        if not _story_copy_allowed(headline, sub):
            continue
        published = f"{headline}\n{story_link_line(sub)}"
        if process_match_findings(published, featured=featured):
            continue
        installed = dict(story_1)
        installed.pop("editorial_score", None)
        installed.pop("viral_potential", None)
        installed.pop("editorial_error", None)
        installed["headline"] = headline
        installed["subtext"] = sub
        installed["poll_question"] = sub
        installed["claim_recovered_from"] = source
        if not isinstance(content.get("stories"), dict):
            content["stories"] = {}
        content["stories"]["story_1"] = installed
        return {"headline": headline, "sub": sub, "source": source}
    return None


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
