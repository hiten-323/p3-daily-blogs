"""UTM tagging for every store link the generator writes.

Every customer-facing p3online.in link carries utm_source, utm_medium and
utm_campaign (founder rule). The product-truth gate rejects untagged store
links; these helpers make sure links the pipeline itself adds are tagged.
"""
from __future__ import annotations

import re
from datetime import date as _date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SITE = "https://p3online.in"
DEFAULT_MEDIUM = "post"
DEFAULT_CAMPAIGN = "202610"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign")

# Piece label -> utm_source.
_SOURCE = {
    "instagram_post": "instagram", "carousel": "instagram", "reel_1": "instagram",
    "growth_reel": "instagram", "stories": "instagram", "story": "instagram",
    "instagram_story": "instagram", "instagram": "instagram",
    "facebook_post": "facebook", "facebook": "facebook",
    "threads_post": "threads", "threads": "threads",
    "linkedin_post": "linkedin", "linkedin": "linkedin",
    "yt_short": "youtube", "youtube": "youtube",
    "blog_post": "blog", "blog": "blog",
}



_PLATFORM_PREFIX = {
    "linkedin": "li", "linkedin_post": "li",
    "instagram": "ig", "instagram_post": "ig", "carousel": "ig",
    "facebook": "fb", "facebook_post": "fb",
    "threads": "th", "threads_post": "th",
    "youtube": "yt", "yt_short": "yt",
    "blog": "blog", "blog_post": "blog",
}


def dated_campaign(platform: str, date: str | None = None, angle: str = "",
                   content_id: str = "") -> str:
    """Platform + IST date + optional angle slug, e.g. li_20261128_pantry."""
    raw = str(date or "").strip()
    if not raw:
        try:
            from content_generator.core.ist_dates import today_ist
            raw = today_ist().isoformat()
        except Exception:
            raw = _date.today().isoformat()
    day = raw.replace("-", "")[:8]
    prefix = _PLATFORM_PREFIX.get(str(platform or "").strip().lower(), "soc")
    slug_src = str(angle or content_id or "").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug_src).strip("_")[:32]
    return f"{prefix}_{day}_{slug}" if slug else f"{prefix}_{day}"


STORE_LINK = re.compile(r"https?://(?:www\.)?p3online\.in(?:[/?#][^\s)\]\"'<>]*)?", re.I)


def source_for(label: str) -> str:
    return _SOURCE.get(str(label or "").strip().lower(), "social")


def tag_url(url: str, source: str, medium: str = DEFAULT_MEDIUM,
            campaign: str = DEFAULT_CAMPAIGN) -> str:
    """`url` with any missing utm_source/utm_medium/utm_campaign added."""
    url = str(url or "").strip()
    if not url:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    present = {key for key, value in query if value}
    wanted = {"utm_source": source, "utm_medium": medium, "utm_campaign": campaign}
    query += [(key, wanted[key]) for key in UTM_KEYS if key not in present]
    path = parts.path or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def site_link(label_or_source: str, medium: str = DEFAULT_MEDIUM,
              campaign: str = DEFAULT_CAMPAIGN) -> str:
    """Tagged home-page link for a piece label (or a utm_source)."""
    source = _SOURCE.get(str(label_or_source or "").lower(), label_or_source or "social")
    return tag_url(SITE + "/", source, medium, campaign)


def tag_store_links(text: str, label_or_source: str, medium: str = DEFAULT_MEDIUM,
                    campaign: str = DEFAULT_CAMPAIGN) -> str:
    """Tag every p3online.in link in `text` that is missing a UTM parameter."""
    if not isinstance(text, str) or "p3online.in" not in text.lower():
        return text
    source = _SOURCE.get(str(label_or_source or "").lower(), label_or_source or "social")

    def _fix(match: re.Match) -> str:
        raw = match.group(0)
        core = raw.rstrip(".,;:!?")
        tail = raw[len(core):]
        params = dict(parse_qsl(urlsplit(core).query))
        if all(params.get(key) for key in UTM_KEYS):
            return raw
        return tag_url(core, source, medium, campaign) + tail

    return STORE_LINK.sub(_fix, text)
