"""LinkedIn copy and posting-window helpers (no network I/O)."""
from __future__ import annotations

import datetime as dt
import os
import re
from content_generator.core.utm import SITE, dated_campaign, tag_url

MAX_HASHTAGS = 3
# Weekdays 08:00–10:30 IST inclusive.
WINDOW_START = (8, 0)
WINDOW_END = (10, 30)
IG_HANDLE = re.compile(r"(?i)\bfollow\s+@purepantryprovisions\b|@purepantryprovisions")
GROCERY_CTA = re.compile(
    r"(?i)save this before your next grocery run\.?|before your next grocery run|"
    r"your next grocery run|shop p3online\.in — purity beans"
)
URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.I)
HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_]+)")
BANNED = re.compile(
    r"(?i)\b100%\b|\bfresh(?:ly|ness|er|est)?\b|\blab[\s-]?tested\b|\bsingle[\s-]origin\b|\bbeans?\b"
)

_B2B_CTA = "Comment DISTRIBUTION and I'll share the trade sheet."


def posting_window_open(now_ist: dt.datetime | None = None) -> bool:
    """True during Mon–Fri 08:00–10:30 IST, or when the window is explicitly bypassed."""
    if os.getenv("LINKEDIN_POSTING_WINDOW", "").strip().lower() in {"off", "0", "bypass"}:
        return True
    if now_ist is None:
        from content_generator.core.ist_dates import IST
        now_ist = dt.datetime.now(IST)
    if now_ist.tzinfo is None:
        now_ist = now_ist.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    if now_ist.weekday() >= 5:
        return False
    minutes = now_ist.hour * 60 + now_ist.minute
    start = WINDOW_START[0] * 60 + WINDOW_START[1]
    end = WINDOW_END[0] * 60 + WINDOW_END[1]
    return start <= minutes <= end


def _norm_product(product: str | None) -> str | None:
    try:
        from content_generator.creative.approved_photos import _norm_sku
        return _norm_sku(product)
    except Exception:
        if not product:
            return None
        p = str(product).lower().replace("-", "_").replace(" ", "_")
        for sku in ("ultra_blend", "purista", "purica", "prima", "bold"):
            if sku in p or (sku == "ultra_blend" and "ultra" in p):
                return sku
        return None


def real_product_photo(content: dict) -> str | None:
    """Return a real jar photo path for the featured SKU, never a random date render."""
    try:
        from content_generator.core.product_truth import featured_product_name
        product = featured_product_name(content) or (content or {}).get("featured_product")
    except Exception:
        product = (content or {}).get("featured_product")
    sku = _norm_product(product)
    day = int((content or {}).get("day_number") or 0)
    try:
        from content_generator.creative.real_jar_composer import pick_jar_photo
        return pick_jar_photo(day, idx=0, product=sku, overlay_safe=True, prefer_front=True)
    except Exception:
        return None


def _collect_urls(*parts: str) -> list[str]:
    found: list[str] = []
    for part in parts:
        for match in URL_RE.findall(str(part or "")):
            url = match.rstrip(".,;:!?")
            if url not in found:
                found.append(url)
    return found


def _strip_urls(text: str) -> str:
    cleaned = URL_RE.sub("", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(" -\n\t")


def _cap_hashtags(raw: str) -> str:
    tags = []
    for match in HASHTAG_RE.finditer(str(raw or "")):
        tag = "#" + match.group(1)
        if tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    if not any(t.lower() == "#puritybeans" for t in tags):
        tags.insert(0, "#PurityBeans")
    return " ".join(tags[:MAX_HASHTAGS])


def _one_b2b_cta(cta: str, body: str) -> str:
    text = IG_HANDLE.sub("", str(cta or ""))
    text = GROCERY_CTA.sub("", text)
    text = _strip_urls(text)
    text = re.sub(r"(?i)\bfollow\s+hiten jain\b.*", "", text).strip(" -—,\n")
    # Drop consumer shop-line leftovers; keep a Comment/DM B2B ask if present.
    lines = [ln.strip() for ln in re.split(r"(?<=[.!?])\s+", text) if ln.strip()]
    preferred = [
        ln for ln in lines
        if re.search(r"(?i)\b(comment|dm)\b", ln)
        and re.search(r"(?i)distribut|horeca|office|gift|trade|distro", ln)
    ]
    if preferred:
        return preferred[0]
    if re.search(r"(?i)\b(comment|dm)\b", text) and not re.search(r"(?i)grocery|follow @", text):
        return text.strip()
    if re.search(r"(?i)\b(comment|dm)\b.+(distribut|horeca|office|gift|trade|distro)", body or ""):
        return ""
    return _B2B_CTA


def comment_link(content: dict, day: int = 0) -> str:
    """Single UTM-tagged store link intended for the first comment."""
    piece = (content or {}).get("linkedin_post") or {}
    date = str((content or {}).get("date") or "")[:10]
    if not date:
        try:
            from content_generator.core.ist_dates import today_ist
            date = today_ist().isoformat()
        except Exception:
            date = dt.date.today().isoformat()
    angle = str(piece.get("angle") or piece.get("featured_product") or "post")
    content_id = ""
    meta = (content or {}).get("_asset_metadata") or []
    if isinstance(meta, list) and meta and isinstance(meta[0], dict):
        content_id = str(meta[0].get("content_id") or "")
    content_id = content_id or str((content or {}).get("generation_id") or "")
    campaign = dated_campaign("linkedin", date, angle=angle, content_id=content_id)
    slug = ""
    try:
        from content_generator.publisher.product_links import product_slug
        slug = product_slug(content, day) or ""
    except Exception:
        slug = ""
    if slug:
        core = f"{SITE}/products/{slug}"
    else:
        core = SITE + "/"
    return tag_url(core, "linkedin", "organic_social", campaign)


def build_payload(content: dict, day: int = 0) -> dict:
    """Build the LinkedIn commentary, first-comment link, and real product photo."""
    li = (content or {}).get("linkedin_post") or {}
    if isinstance(li, str):
        li = {"body": li}
    hook = str(li.get("hook") or "").strip()
    body = str(li.get("body") or "").strip()
    bridge = str(li.get("brand_bridge") or "").strip()
    question = str(li.get("closing_question") or "").strip()
    cta = _one_b2b_cta(str(li.get("cta") or ""), body)
    hashtags = _cap_hashtags(str(li.get("hashtags") or ""))

    # Links leave the body; they go in the first comment (or, on comment failure, once at the end).
    _collect_urls(hook, body, bridge, question, str(li.get("cta") or ""))
    hook, body, bridge, question = (_strip_urls(IG_HANDLE.sub("", GROCERY_CTA.sub("", p)))
                                    for p in (hook, body, bridge, question))
    parts = [p for p in (hook, body, bridge, question, cta, hashtags) if p and p not in (body, hook)]
    # Keep hook first even if it also appears in body.
    ordered = []
    if hook:
        ordered.append(hook)
    if body and body != hook:
        ordered.append(body)
    for part in (bridge, question, cta, hashtags):
        if part and part not in ordered and (not body or part not in body):
            ordered.append(part)
    commentary = "\n\n".join(ordered).strip()
    link = comment_link(content, day)
    image_path = real_product_photo(content)
    return {
        "commentary": commentary[:3000],
        "comment": link,
        "image_path": image_path,
        "hook": hook,
        "hashtags": hashtags,
        "cta": cta,
        "campaign": (link.split("utm_campaign=")[-1].split("&")[0] if "utm_campaign=" in link else ""),
    }
