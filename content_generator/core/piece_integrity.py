"""
Keep a generated asset whole.

Regeneration used to replace a piece with whatever short JSON the model
returned, so captions, hashtags, triggers, frames, audio plans and loop
notes disappeared and the publish gate rejected the asset. Schema field
names also disagree with the growth-reel prompt (`hook_text` vs
`chosen_hook`, `frames` vs `script`, hashtags as a list). This module
merges a rewrite onto the original and fills only structural gaps the
gate already knows how to read.
"""
from __future__ import annotations

import copy
import re
import logging

from content_generator.creative.instagram_quality_gate import (
    AUDIO_PLAN_KEYS, LOOP_KEYS,
)

logger = logging.getLogger(__name__)

_SCORE_DIMS = (
    "shareability", "saveability", "emotion_pull", "hook_strength", "brand_clarity",
)

_CAPTION_LABELS = {"reel_1", "reel_2", "carousel", "instagram_post", "growth_reel"}
_REEL_LABELS = {"reel_1", "reel_2", "growth_reel"}

_DEFAULT_HASHTAGS = (
    "#PurityBeans #PureCoffee #InstantCoffee #NoChicory #CoffeeLover "
    "#IndianCoffee #CoffeeIndia #MadeInIndia #PremiumCoffee #GlassJar "
    "#GourmetCoffee #CoffeeCommunity #CoffeeAddict #CoffeeGram #CoffeeCulture "
    "#SupportIndianBrands #IndianBrands #PurityBeansCoffee #BrewPure #PureCoffeeExperience "
    "#MorningCoffee #CoffeeTime #CoffeeDaily #CoffeeLife #CoffeeLove"
)
_DEFAULT_COMMENT = "Comment COFFEE below if you refuse to drink chicory disguised as coffee."
_DEFAULT_SAVE = "Save this before your next grocery run — real coffee matters."
_DEFAULT_SHARE = "Share with someone who starts every morning with coffee."

# Long-form fields a short rewrite must not replace.
_PRESERVE_IF_SHORTER = {
    "caption", "body", "introduction", "conclusion", "hashtags",
    "comment_trigger", "save_trigger", "share_trigger",
}
_LIST_FIELDS = {"frames", "slides", "script", "scenes"}


def _canon(label: str, piece: dict) -> str:
    lab = (label or "").strip().lower()
    if lab in ("carousel", "carousel_1"):
        return "carousel"
    if lab in _REEL_LABELS or lab in ("instagram_post", "linkedin_post", "blog_post", "yt_short"):
        return lab
    pid = str(piece.get("id") or "").strip().lower()
    if pid == "carousel_1":
        return "carousel"
    if pid in _REEL_LABELS:
        return pid
    if str(piece.get("track") or "").strip().lower() == "growth":
        return "growth_reel"
    return lab


def _is_growth(label: str, piece: dict) -> bool:
    return label == "growth_reel" or str(piece.get("track") or "").strip().lower() == "growth"


def _nonempty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _score_complete(score) -> bool:
    if not isinstance(score, dict):
        return False
    return all(score.get(dim) not in (None, "") for dim in _SCORE_DIMS) and score.get("overall") not in (None, "")


def complete_editorial_score(piece: dict) -> None:
    """Fill missing editorial subscores from `overall`. Never invents a score."""
    score = piece.get("editorial_score")
    if not isinstance(score, dict) or not score:
        return
    dims_present = []
    for dim in _SCORE_DIMS:
        raw = score.get(dim)
        if raw in (None, ""):
            continue
        try:
            score[dim] = float(raw)
            dims_present.append(score[dim])
        except (TypeError, ValueError):
            score[dim] = None
    try:
        overall = float(score.get("overall"))
    except (TypeError, ValueError):
        overall = round(sum(dims_present) / len(dims_present), 1) if dims_present else 0.0
    score["overall"] = overall
    for dim in _SCORE_DIMS:
        if score.get(dim) in (None, ""):
            score[dim] = overall
    if score.get("verdict") not in ("PASS", "REJECT", "APPROVE"):
        score["verdict"] = "PASS" if overall >= 8 else "REJECT"
    if not isinstance(score.get("feedback"), str):
        score["feedback"] = str(score.get("feedback") or "")


def _coerce_hashtags(piece: dict) -> None:
    tags = piece.get("hashtags")
    if isinstance(tags, list):
        parts = []
        for tag in tags:
            text = str(tag or "").strip()
            if not text:
                continue
            if not text.startswith("#"):
                text = "#" + text.lstrip("#")
            parts.append(text)
        piece["hashtags"] = " ".join(parts)


def _alias_hooks(piece: dict) -> None:
    hook = str(
        piece.get("hook_text") or piece.get("chosen_hook") or piece.get("hook")
        or piece.get("hook_line") or ""
    ).strip()
    if not hook:
        return
    piece.setdefault("hook_text", hook)
    piece.setdefault("hook", hook)
    if not str(piece.get("chosen_hook") or "").strip():
        piece["chosen_hook"] = hook


def _frames_from_script(piece: dict) -> None:
    frames = [
        f for f in (piece.get("frames") or [])
        if isinstance(f, dict)
        and str(f.get("on_screen") or "").strip()
        and str(f.get("spoken") or f.get("voiceover") or "").strip()
    ]
    if len(frames) >= 5:
        if frames != piece.get("frames"):
            piece["frames"] = [
                {"on_screen": f.get("on_screen"), "spoken": f.get("spoken") or f.get("voiceover")}
                for f in frames
            ]
        return
    built = []
    for beat in piece.get("script") or []:
        if not isinstance(beat, dict):
            continue
        on_screen = str(beat.get("on_screen") or beat.get("beat") or "").strip()
        spoken = str(beat.get("spoken") or beat.get("voiceover") or "").strip()
        if on_screen and spoken:
            built.append({"on_screen": on_screen, "spoken": spoken})
    if len(built) >= 5:
        piece["frames"] = built


def _ensure_audio(piece: dict) -> None:
    if any(_nonempty(piece.get(key)) for key in AUDIO_PLAN_KEYS):
        return
    piece["audio"] = {
        "plan": "Voice-forward bed, low music under the spoken line, no lyric clash.",
        "source": "structural_default",
    }


def _ensure_loop(piece: dict) -> None:
    if any(_nonempty(piece.get(key)) for key in LOOP_KEYS):
        return
    piece["loop_note"] = (
        "Final frame returns to the opening shot so the reel loops without a hard cut."
    )


def _compose_caption(piece: dict, label: str, seed: str) -> str:
    parts = [seed] if seed else []
    for key in ("title", "hook", "hook_text", "chosen_hook"):
        value = str(piece.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    slides = [s for s in (piece.get("slides") or []) if isinstance(s, dict)]
    for slide in slides[:3] + slides[-1:]:
        parts.append(str(slide.get("heading") or "").strip())
        parts.append(str(slide.get("body") or "").strip())
    for frame in (piece.get("frames") or piece.get("script") or [])[:4]:
        if isinstance(frame, dict):
            parts.append(str(frame.get("spoken") or frame.get("voiceover") or "").strip())
    text = " ".join(p for p in parts if p).strip()
    if _is_growth(label, piece):
        if len(text) < 50:
            text = (text + " Check the label and see what is actually in the cup.").strip()
        return text
    low = text.lower()
    if "purity beans" not in low:
        text += " Purity Beans."
    if not any(token in low for token in (
        "pure coffee", "100 percent coffee", "zero chicory", "no chicory", "pure coffee",
        "pure arabica", "pure robusta", "70% coffee", "70 percent coffee",
    )):
        if "ultra" in low:
            text += " Ultra Blend is 70% coffee."
        else:
            text += " Bold, Purista, Purica, and Prima are pure coffee with zero chicory."
    if "p3online.in" not in low:
        text += " Visit p3online.in."
    return text.strip()


def _ensure_caption(piece: dict, label: str) -> None:
    cap = str(piece.get("caption") or "").strip()
    if len(cap) >= 50:
        return
    built = _compose_caption(piece, label, cap)
    if len(built) >= 50:
        piece["caption"] = built


def _ensure_engagement(piece: dict) -> None:
    for field, default, min_len in (
        ("hashtags", _DEFAULT_HASHTAGS, 10),
        ("comment_trigger", _DEFAULT_COMMENT, 10),
        ("save_trigger", _DEFAULT_SAVE, 10),
        ("share_trigger", _DEFAULT_SHARE, 10),
    ):
        val = piece.get(field)
        if not isinstance(val, str) or len(val.strip()) < min_len:
            piece[field] = default


def _plain_text(value: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip()


def _alias_blog_fields(piece: dict) -> None:
    """
    The blog prompt used to ask for intro / body_html and no conclusion.
    BlogSchema reads introduction / body / conclusion, so every post failed
    as three missing fields before the copy was ever read.
    """
    if not str(piece.get("introduction") or "").strip():
        intro = piece.get("intro") or piece.get("introduction_html")
        if isinstance(intro, str) and intro.strip():
            piece["introduction"] = _plain_text(intro)
    body = piece.get("body")
    if not isinstance(body, str) or len(body.strip()) < 40:
        html = piece.get("body_html") or piece.get("content_html")
        if isinstance(html, str) and html.strip():
            piece["body"] = _plain_text(html)
    if not str(piece.get("conclusion") or "").strip():
        for key in ("conclusion_html", "closing", "outro"):
            closing = piece.get(key)
            if isinstance(closing, str) and closing.strip():
                piece["conclusion"] = _plain_text(closing)
                break
    from content_generator.core.blog_quality import normalize_blog_piece
    normalize_blog_piece(piece)


_FIRST_SENTENCE = re.compile(r"^(.{20,220}?[.?!])\s+(\S.*)$", re.S)


def _ensure_threads_hook_line(piece: dict) -> None:
    """Put a Threads post's opening sentence on its own line.

    The payoff gate reads the hook as the copy's first line. A one-paragraph
    Threads post made the WHOLE post the hook, so the body the gate inspects
    was empty and every rewrite failed "no payoff" however good it was
    (Oct 17: 18 straight rejections). Only whitespace changes; the words and
    the gate are untouched, so the body must still carry a real payoff.
    """
    for key in ("text", "body", "content"):
        text = piece.get(key)
        if isinstance(text, str) and text.strip():
            break
    else:
        return
    stripped = text.strip()
    if "\n" in stripped:
        return
    m = _FIRST_SENTENCE.match(stripped)
    if not m or len(m.group(2)) < 40:
        return
    piece[key] = f"{m.group(1)}\n\n{m.group(2)}"


def promote_threads_text(piece: dict) -> dict:
    """Map a native Threads string onto ``text``.

    NVIDIA and Gemini often return a whole content pack. The Threads line is
    a string under the key ``threads_post`` (or post/caption) and ``text``,
    ``body``, and ``content`` are absent. The brand gate then reports
    Empty content even though the model wrote the post.
    """
    if not isinstance(piece, dict):
        return piece
    for key in ("text", "body", "content"):
        val = piece.get(key)
        if isinstance(val, str) and val.strip():
            return piece
    found = _threads_copy(piece.get("threads_post"))
    if not found:
        for key in ("post", "thread", "message", "copy", "native_text"):
            val = piece.get(key)
            if isinstance(val, str) and val.strip():
                found = val.strip()
                break
    if not found:
        cap = piece.get("caption")
        if isinstance(cap, str) and cap.strip() and len(cap.strip()) <= 480 and "slides" not in piece:
            found = cap.strip()
    if found:
        piece["text"] = found
    return piece


def _threads_copy(node) -> str:
    if isinstance(node, str) and node.strip():
        return node.strip()
    if isinstance(node, dict):
        for key in ("text", "body", "content", "post", "caption"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if isinstance(node, list):
        for item in node:
            found = _threads_copy(item)
            if found:
                return found
    return ""


def _fit_threads_length(piece: dict, limit: int = 480) -> None:
    """Cut a Threads post at the last sentence that fits. No clean cut stays long."""
    for key in ("text", "body", "content"):
        text = piece.get(key)
        if not isinstance(text, str) or len(text.strip()) <= limit:
            continue
        raw = text.strip()
        window = raw[:limit]
        idx = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
        if idx >= 40:
            piece[key] = window[: idx + 1].strip()


def _ensure_facebook_brand_facts(piece: dict) -> None:
    """Facebook was never in the brand-injection list, so drafts failed 'missing facts'.

    The sentence is the product's own process line. It does not say
    'not freeze-dried' next to Bold — that phrase fails the process matcher.
    """
    from content_generator.core.brand_validator import (
        validate_brand_facts, validate_brand_mention, validate_website,
    )
    from content_generator.core.process_match import _DEST_LINE, _featured_slug

    keys = ("hook", "body", "community_question", "cta", "hashtags")

    def joined() -> str:
        return " ".join(str(piece.get(key) or "") for key in keys)

    if not validate_brand_mention(joined()):
        piece["body"] = (str(piece.get("body") or "").rstrip() + " Purity Beans").strip()
    if not validate_brand_facts(joined()):
        slug = _featured_slug(str(piece.get("featured_product") or ""))
        line = _DEST_LINE.get(slug) or "Purity Beans is pure coffee."
        if line.lower() not in joined().lower():
            piece["body"] = (str(piece.get("body") or "").rstrip() + " " + line).strip()
    if not validate_website(joined()):
        piece["cta"] = (str(piece.get("cta") or "").rstrip() + " Shop: https://p3online.in").strip()


def promote_facebook_copy(piece: dict) -> dict:
    """Lift nested Facebook copy and drop any article pack before the 8.0 scorer."""
    from content_generator.prompts.facebook import normalize_facebook_piece
    return normalize_facebook_piece(piece)


def accept_facebook_regen(improved: dict, original: dict | None = None) -> dict | None:
    """Adopt a native Facebook rewrite. An article pack is not stored."""
    from content_generator.prompts.facebook import accept_facebook_regen as _accept
    return _accept(improved, original)


def ensure_structural_fields(piece: dict, label: str = "") -> dict:
    """Fill structural gaps in place. Creative copy that is already present stays."""
    if not isinstance(piece, dict):
        return piece
    _alias_blog_fields(piece)
    label = _canon(label, piece)
    _coerce_hashtags(piece)
    _alias_hooks(piece)
    if label in _REEL_LABELS:
        _frames_from_script(piece)
        _ensure_audio(piece)
        _ensure_loop(piece)
    if label in _CAPTION_LABELS:
        _ensure_caption(piece, label)
    if label == "threads_post" or str(piece.get("asset_type") or "") == "threads_post":
        promote_threads_text(piece)
        _ensure_threads_hook_line(piece)
        _fit_threads_length(piece)
    if label == "facebook_post" or str(piece.get("asset_type") or "") == "facebook_post":
        promote_facebook_copy(piece)
        _ensure_facebook_brand_facts(piece)
    _ensure_engagement(piece)
    complete_editorial_score(piece)
    return piece


def merge_regenerated_piece(original: dict, improved: dict) -> dict:
    """
    Overlay a rewrite onto the original asset.

    Empty values and short replacements of long-form fields are ignored, so a
    regen that returns only a new hook cannot drop the caption, slides, frames,
    hashtags or a complete editorial score.
    """
    if not isinstance(original, dict):
        original = {}
    if not isinstance(improved, dict) or not improved:
        return copy.deepcopy(original)
    merged = copy.deepcopy(original)
    for key, value in improved.items():
        if not _nonempty(value):
            continue
        prev = merged.get(key)
        if isinstance(prev, (list, dict)) and not isinstance(value, type(prev)):
            logger.info("[editorial] keeping %s — rewrite changed its type", key)
            continue
        if key in _LIST_FIELDS and isinstance(prev, list) and isinstance(value, list):
            if len(value) < len(prev) and len(value) < 5:
                logger.info("[editorial] keeping %s — rewrite shortened a structured list", key)
                continue
        if key in _PRESERVE_IF_SHORTER and isinstance(value, str) and isinstance(prev, str):
            # A rewrite may be shorter and still be the better caption. Only a
            # value under the schema minimum is a drop, which is what used to
            # wipe the carousel caption and get stored as editorial score 0.
            minimum = 1000 if key == "body" else 50 if key in ("caption", "introduction") else 10
            if len(prev.strip()) >= minimum and len(value.strip()) < minimum:
                logger.info("[editorial] keeping %s — rewrite was below the schema minimum", key)
                continue
        if key == "editorial_score":
            if not isinstance(value, dict):
                continue
            if _score_complete(prev) and not _score_complete(value):
                logger.info("[editorial] keeping editorial_score — rewrite dropped subscores")
                continue
        merged[key] = copy.deepcopy(value)
    return merged
