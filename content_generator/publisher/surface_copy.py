"""Truth-safe, platform-native copy. Rendering and posting call this. It does not publish."""
from __future__ import annotations

import re

def _shop_line() -> str:
    from config.brand_config import platform_handle
    handle = platform_handle("instagram")
    follow = f"Follow {handle}. " if handle else ""
    return f"{follow}Shop at https://p3online.in"


SHOP_LINE = _shop_line()
LINKEDIN_TAGS = "#PurityBeans #InstantCoffee #IndianStartups"

_LIMITS = {
    "instagram": (2200, 5, 15),
    "reel": (2200, 5, 15),
    "facebook": (2000, 0, 5),
    "linkedin": (3000, 3, 5),
    "threads": (500, 0, 1),
}
_BAD = re.compile(
    r"roasted[\s-]+root|roasted filler|burnt root|chicory root|muddy|sits heavy|filler-heavy|"
    r"low-grade|masquerading|chicory infusion|self-defense against|heavily diluted|"
    r"grind consistency|extraction temperature|chronobiology|glycemic|adrenal|"
    r"30%\s*to\s*49%|49%\s*chicory",
    re.I,
)
_MONEY_HOOK = re.compile(
    r"(?:₹|rs\.?\s*)\s*\d|\bwaste\b|\bevery\s+week\b",
    re.I,
)
_UNFIT = re.compile(
    r"chronobiology|glycemic|adrenal|jittery|boiling water|antioxidant|tanking your|"
    r"100\s*°|80\s*°|80c|100c",
    re.I,
)


def hashtags(text: str) -> list[str]:
    return re.findall(r"#\w+", text or "")


def audit_copy(platform: str, text: str, featured: str | None = None) -> dict:
    """Fail when a caption breaks truth, length, hashtags, the hook, or the shop CTA."""
    from content_generator.core.product_truth import product_truth_findings

    text = text or ""
    limit, low, high = _LIMITS.get(platform, (2200, 0, 15))
    issues: list[str] = []
    findings = product_truth_findings(text, featured=featured)
    if findings:
        issues.append("product_truth")
    if _BAD.search(text):
        issues.append("distasteful_claim")
    if "p3online.in" not in text.lower():
        issues.append("missing_shop")
    if "follow" not in text.lower():
        issues.append("missing_follow")
    first = text.strip().splitlines()[0] if text.strip() else ""
    if len(first.split()) < 3:
        issues.append("weak_hook")
    count = len(hashtags(text))
    if count < low or count > high:
        issues.append("hashtag_count")
    if len(text) > limit:
        issues.append("too_long")
    return {
        "ok": not issues,
        "issues": issues,
        "hashtags": count,
        "chars": len(text),
        "findings": findings,
    }


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip() for part in parts if part.strip()]


def disclose_ratio(text: str) -> str:
    """Ultra Blend named as 70% coffee also names the 30% chicory on the label."""
    if not text or not re.search(r"ultra\s*blend", text, re.I) or re.search(r"30\s*%\s*chicory", text, re.I):
        return text
    return re.sub(
        r"(Ultra Blend is 70%\s*coffee)(?!\s*and\s*30%)",
        r"\1 and 30% chicory",
        text,
        count=1,
        flags=re.I,
    )


def _cap_hashtags(text: str, maximum: int) -> str:
    seen = 0

    def _keep(match: re.Match) -> str:
        nonlocal seen
        seen += 1
        return match.group(0) if seen <= maximum else ""

    text = re.sub(r"#\w+", _keep, text or "")
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _fit(text: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].strip()


def _ensure_cta(text: str, limit: int) -> str:
    if "p3online.in" in text.lower() and "follow" in text.lower():
        return _fit(text, limit)
    extra = "\n\n" + SHOP_LINE
    body = _fit(text, max(40, limit - len(extra)))
    return _fit(body.rstrip() + extra, limit)


def _benefit_line(featured: str | None) -> str:
    from content_generator.creative.jar_frame import conversion_copy

    copy = conversion_copy(featured or "Bold")
    return " ".join(part for part in (copy["benefit"], copy["offer"]) if part).strip()


def polish(text: str, featured: str | None, platform: str) -> str:
    """Drop attacks and unsupported health claims, then enforce the platform limits."""
    from content_generator.core.product_truth import product_truth_findings

    limit, low, high = _LIMITS.get(platform, (2200, 0, 15))
    kept = []
    for sentence in _sentences(disclose_ratio(text)):
        if _BAD.search(sentence):
            continue
        if product_truth_findings(sentence, featured=featured):
            continue
        kept.append(sentence)
    cleaned = "\n\n".join(kept).strip()
    if len(cleaned) < 40 or not _names_featured(cleaned, featured):
        cleaned = f"{cleaned}\n\n{_benefit_line(featured)}".strip()
    if platform == "linkedin" and low and len(hashtags(cleaned)) < low:
        cleaned = f"{cleaned}\n\n{LINKEDIN_TAGS}"
    cleaned = _cap_hashtags(cleaned, high)
    cleaned = _ensure_cta(cleaned, limit)
    if product_truth_findings(cleaned, featured=featured) or _BAD.search(cleaned):
        cleaned = _ensure_cta(_benefit_line(featured), limit)
        if platform == "linkedin":
            cleaned = _cap_hashtags(f"{cleaned}\n\n{LINKEDIN_TAGS}", high)
    return _fit(cleaned, limit)


def _piece_text(piece: dict, keys: tuple[str, ...]) -> str:
    if not isinstance(piece, dict):
        return ""
    return "\n\n".join(str(piece.get(key) or "").strip() for key in keys if str(piece.get(key) or "").strip())


def _names_featured(text: str, featured: str | None) -> bool:
    from content_generator.creative.jar_frame import product_slug
    slug = product_slug(featured) or ""
    hay = (text or "").lower().replace("-", " ").replace("_", " ")
    if not slug:
        return True
    if slug.replace("_", " ") in hay:
        return True
    benefit = _benefit_line(featured).split(".")[0].strip().lower()
    return bool(benefit) and benefit in hay


def finalize_linkedin(content: dict) -> str:
    piece = content.get("linkedin_post") if isinstance(content.get("linkedin_post"), dict) else {}
    featured = str(piece.get("featured_product") or content.get("featured_product") or "Bold")
    raw = _piece_text(piece, ("hook", "body", "brand_bridge", "closing_question", "cta", "hashtags"))
    if _UNFIT.search(raw) or _BAD.search(raw):
        from content_generator.core.product_truth import product_truth_findings
        hook = str(piece.get("hook") or "").strip()
        growth = content.get("growth_reel") if isinstance(content.get("growth_reel"), dict) else {}
        if not hook or product_truth_findings(hook, featured=featured) or _BAD.search(hook) or _UNFIT.search(hook):
            hook = str(growth.get("hook_text") or growth.get("hook") or "").strip()
        if not hook or product_truth_findings(hook, featured=featured) or _BAD.search(hook) or _UNFIT.search(hook):
            hook = "The label is the product."
        ratio = "Ultra Blend is 70% coffee and 30% chicory." if re.search(r"ultra", raw, re.I) else ""
        raw = "\n\n".join(part for part in (
            hook,
            "I build Purity Beans so the label matches the cup.",
            _benefit_line(featured),
            ratio,
            SHOP_LINE,
            LINKEDIN_TAGS,
        ) if part)
    text = polish(raw, featured, "linkedin")
    if not re.search(r"\b(I|I'm|Hiten)\b", text):
        text = polish("I build Purity Beans so the label matches the cup.\n\n" + text, featured, "linkedin")
    return text


def finalize_threads(content: dict) -> str:
    piece = content.get("threads_post") if isinstance(content.get("threads_post"), dict) else {}
    featured = str(piece.get("featured_product") or content.get("featured_product") or "Bold")
    raw = str(piece.get("text") or piece.get("body") or "").strip()
    if not raw:
        raw = f"Read the jar before the next cup.\n\n{_benefit_line(featured)}"
    return polish(raw, featured, "threads")


def finalize_facebook(content: dict, message: str | None = None) -> str:
    from content_generator.publisher.facebook import _build_message

    featured = ""
    piece = content.get("facebook_post") if isinstance(content.get("facebook_post"), dict) else {}
    featured = str(piece.get("featured_product") or content.get("featured_product") or "Bold")
    raw = message if message else _build_message(content)
    return polish(raw or _benefit_line(featured), featured, "facebook")


def finalize_instagram(body: str, piece: dict, day: int, featured: str | None) -> str:
    from content_generator.publisher.instagram import _assemble_caption

    cleaned = polish(body or "", featured, "instagram")
    # polish already added the shop line and stripped tags down. Assemble restores
    # a capped tag block from the piece without putting the raw attack copy back.
    text = _assemble_caption(cleaned, piece or {}, day)
    limit, _low, high = _LIMITS["instagram"]
    text = _cap_hashtags(text, high)
    if "p3online.in" not in text.lower():
        text = _ensure_cta(text, limit)
    from content_generator.core.product_truth import product_truth_findings
    if product_truth_findings(text, featured=featured) or _BAD.search(text):
        text = _assemble_caption(_benefit_line(featured) + "\n\n" + SHOP_LINE, {}, day)
    return _fit(text, limit)


def clean_slide_copy(heading: str, body: str, product: str | None) -> tuple[str, str]:
    from content_generator.core.product_truth import product_truth_findings

    kept = [sentence for sentence in _sentences(body or "") if not _BAD.search(sentence)]
    body = disclose_ratio(" ".join(kept))
    heading = disclose_ratio(heading or "")
    blob = f"{heading}. {body}"
    if product_truth_findings(blob, featured=product):
        safe = _benefit_line(product)
        return "READ THE LABEL", safe
    return heading, body


def clean_reel_beats(reel: dict) -> list[dict]:
    """On-screen lines must agree with the voiceover and the jar."""
    from content_generator.creative.reel_video import _beats_from_reel
    from content_generator.core.product_truth import product_truth_findings

    featured = str((reel or {}).get("product") or (reel or {}).get("featured_product") or "")
    cleaned = []
    for beat in _beats_from_reel(reel or {}):
        on = str(beat.get("on") or "")
        sub = str(beat.get("sub") or "")
        on = on.replace("AGGOMERATED", "AGGLOMERATED").replace("Aggomerated", "Agglomerated")
        if re.search(r"every\s+day", on, re.I) and re.search(r"every\s+week", sub, re.I):
            on = re.sub(r"every\s+day", "EVERY WEEK", on, flags=re.I)
        if product_truth_findings(f"{on} {sub}", featured=featured) or _BAD.search(f"{on} {sub}"):
            sub = ""
        if product_truth_findings(on, featured=featured) or _BAD.search(on):
            on = "READ THE LABEL"
        cleaned.append({"on": on, "sub": sub})
    return cleaned


def story_frame_copy(content: dict, day: int = 0) -> dict:
    """Stories do not draw poll stickers. The frame uses today's featured jar."""
    from content_generator.core.product_truth import product_truth_findings
    from content_generator.publisher.story_copy import resolve_story_copy

    featured = str(content.get("featured_product") or "Bold")
    stories = content.get("stories") if isinstance(content.get("stories"), dict) else {}
    story = stories.get("story_1") if isinstance(stories.get("story_1"), dict) else {}
    benefit = _benefit_line(featured)
    if str(story.get("type") or "").lower() == "poll":
        hook = ""
        growth = content.get("growth_reel") if isinstance(content.get("growth_reel"), dict) else {}
        for candidate in (growth.get("hook_text"), growth.get("hook"), story.get("headline")):
            candidate = str(candidate or "").strip()
            if candidate and not product_truth_findings(candidate, featured=featured) and not _BAD.search(candidate) and not _MONEY_HOOK.search(candidate):
                hook = candidate
                break
        return {"headline": hook or "READ THE LABEL", "sub": benefit, "product": featured}
    resolved = resolve_story_copy(content, day=day)
    return {"headline": resolved["headline"], "sub": resolved["sub"] or benefit, "product": featured}


def on_image_hook(content: dict, platform: str) -> str:
    """Short truth-safe line for the first frame."""
    from content_generator.core.product_truth import product_truth_findings

    featured = str(content.get("featured_product") or "Bold")
    piece = content.get(f"{platform}_post") if isinstance(content.get(f"{platform}_post"), dict) else {}
    if platform == "reel":
        piece = content.get("growth_reel") if isinstance(content.get("growth_reel"), dict) else {}
    candidates = [piece.get(key) for key in ("hook", "hook_text", "headline", "text")]
    growth = content.get("growth_reel") if isinstance(content.get("growth_reel"), dict) else {}
    candidates.extend((growth.get("hook_text"), growth.get("hook")))
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if candidate and not product_truth_findings(candidate, featured=featured) and not _BAD.search(candidate) and not _UNFIT.search(candidate) and not _MONEY_HOOK.search(candidate):
            return candidate
    return "READ THE LABEL"
