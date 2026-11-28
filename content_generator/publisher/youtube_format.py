"""YouTube Shorts copy contract: hook, brand, UTM, no IG-handle CTAs, no placeholders."""
from __future__ import annotations

import re

from content_generator.core.utm import dated_campaign, site_link, tag_store_links

IG_HANDLE = re.compile(r"(?:follow\s+)?@purepantryprovisions|https?://(?:www\.)?instagram\.com/\S*", re.I)
HASHTAG = re.compile(r"#\w+")
PLACEHOLDER_PATTERNS = (
    re.compile(r"high-tension\s+1\.5s\s+opening", re.I),
    re.compile(r"punchy youtube seo search title", re.I),
    re.compile(r"50-100 words including search keywords", re.I),
    re.compile(r"opening spoken hook line", re.I),
    re.compile(r"the opening hook line", re.I),
    re.compile(r"high-retention subscriber cta", re.I),
    re.compile(r"pure coffee truths without commercial fluff", re.I),
)
FOOD_SCIENCE_CTA = re.compile(r"what'?s really in your food", re.I)

DEFAULT_TITLE = "Purity Beans — Pure Instant Coffee #Shorts"
DEFAULT_CTA = "Subscribe for the next coffee truth."


def is_placeholder(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    return any(pattern.search(t) for pattern in PLACEHOLDER_PATTERNS)


def shop_url(date: str | None = None) -> str:
    campaign = dated_campaign("youtube", date=date)
    return site_link("youtube", medium="organic_social", campaign=campaign)


def sanitize_title(title: str, hook: str = "") -> str:
    text = str(title or "").strip()
    if is_placeholder(text):
        text = str(hook or "").strip()
    if is_placeholder(text) or not text:
        text = DEFAULT_TITLE
    text = IG_HANDLE.sub("", text).strip()
    if "#short" not in text.lower():
        # Keep titles searchable and clearly marked as Shorts; cap at 100.
        trimmed = text[:88].rstrip(" -|")
        text = f"{trimmed} #Shorts"
    return text[:100].strip()


def sanitize_description(
    description: str,
    *,
    hook: str = "",
    cta: str = "",
    date: str | None = None,
) -> str:
    text = str(description or "").strip()
    if is_placeholder(text):
        text = ""
    text = IG_HANDLE.sub("", text)
    text = FOOD_SCIENCE_CTA.sub("the next coffee truth", text)
    text = tag_store_links(
        text,
        "youtube",
        medium="organic_social",
        campaign=dated_campaign("youtube", date=date),
    )
    if "purity beans" not in text.lower():
        text = ("Purity Beans. " + text).strip()
    url = shop_url(date=date)
    if "p3online.in" not in text.lower():
        spoken_cta = str(cta or "").strip()
        if is_placeholder(spoken_cta) or IG_HANDLE.search(spoken_cta) or FOOD_SCIENCE_CTA.search(spoken_cta):
            spoken_cta = DEFAULT_CTA
        text = f"{text}\n\n{spoken_cta}\nShop: {url}".strip()
    # Cap on-description hashtags: keep at most 3 plus #Shorts / #PurityBeans.
    tags = HASHTAG.findall(text)
    keep = []
    for tag in tags:
        low = tag.lower()
        if low in {"#shorts", "#puritybeans"} or (len(keep) < 3 and low not in {t.lower() for t in keep}):
            if low not in {t.lower() for t in keep}:
                keep.append(tag)
    # Rebuild trailing hashtag run
    body = HASHTAG.sub("", text).strip()
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if "#PurityBeans" not in keep and "#puritybeans" not in {t.lower() for t in keep}:
        keep.append("#PurityBeans")
    if "#Shorts" not in keep and "#shorts" not in {t.lower() for t in keep}:
        keep.append("#Shorts")
    return (body + "\n\n" + " ".join(keep)).strip()[:5000]


def sanitize_cta(cta: str) -> str:
    raw = str(cta or "")
    had_ig = bool(IG_HANDLE.search(raw))
    text = IG_HANDLE.sub("", raw)
    text = FOOD_SCIENCE_CTA.sub("the next coffee truth", text)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    if is_placeholder(text) or not text or had_ig:
        return DEFAULT_CTA
    return text


def hook_is_weak(hook: str) -> bool:
    text = str(hook or "").strip()
    if is_placeholder(text) or len(text) < 8:
        return True
    lowered = text.lower()
    hedged = (
        lowered.startswith("most people"),
        lowered.startswith("did you know"),
        lowered.startswith("what if i told you"),
        lowered.startswith("in this video"),
    )
    return any(hedged)
