
"""
Brand Signals — automates the three Brand Equity components that were manual.

1. branded_search_index  — Google Trends interest for "purity beans" (pytrends,
                           unofficial API; optional dependency, skips cleanly)
2. ugc_creation_rate     — #puritybeans hashtag volume via Instagram hashtag
                           search (same Graph API token as publishing)
3. review_sentiment      — keyword sentiment over recent comments on our own
                           posts (comments fetched via Graph API, zero LLM cost)

update_brand_equity_inputs() runs weekly before the Founder Brief. Each
component only overwrites the stored value when its fetch SUCCEEDS — a failed
source preserves the previous (or manually entered) value, so automation
degrades to the manual workflow instead of zeroing scores.
"""
from __future__ import annotations
from config.api_versions import META_GRAPH_BASE
import datetime
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_LEARNING_DIR  = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_EQUITY_INPUTS = os.path.join(_LEARNING_DIR, "brand_equity_inputs.json")
_POSTS_PATH    = os.path.join(_LEARNING_DIR, "published_posts.json")
_GRAPH_API     = META_GRAPH_BASE
_TIMEOUT       = 30

_BRAND_TERM    = "purity beans"
_BRAND_HASHTAG = "puritybeans"


def _graph_get(path: str, params: dict) -> dict | None:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return None
    url = f"{_GRAPH_API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "PurityBeans/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("[signals] Graph API failed (%s): %s", path, e)
        return None


# ── 1. Branded search index (Google Trends via pytrends) ─────────────────────

def fetch_branded_search_index() -> float | None:
    """
    Mean Google Trends interest (0-100) for the brand term over 90 days,
    scaled to 0-10. Returns None if pytrends is unavailable or rate-limited.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.info("[signals] pytrends not installed — branded search skipped")
        return None
    try:
        pt = TrendReq(hl="en-IN", tz=330, timeout=(10, 25))
        pt.build_payload([_BRAND_TERM], timeframe="today 3-m", geo="IN")
        df = pt.interest_over_time()
        if df is None or df.empty:
            return 0.0
        mean_interest = float(df[_BRAND_TERM].mean())   # 0-100
        return round(min(10.0, mean_interest / 10.0), 1)
    except Exception as e:
        logger.warning("[signals] Google Trends fetch failed: %s", e)
        return None


# ── 2. UGC creation rate (#puritybeans hashtag volume) ───────────────────────

def fetch_ugc_rate() -> float | None:
    """
    Count recent public posts under #puritybeans via IG hashtag search.
    Scale: 0 posts = 0, 20+ recent posts = 10. None on API failure.
    """
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not account_id:
        return None

    found = _graph_get("ig_hashtag_search", {"user_id": account_id, "q": _BRAND_HASHTAG})
    if not found or not found.get("data"):
        return None if found is None else 0.0
    hashtag_id = found["data"][0].get("id")
    if not hashtag_id:
        return 0.0

    media = _graph_get(f"{hashtag_id}/recent_media",
                       {"user_id": account_id, "fields": "id", "limit": 50})
    if media is None:
        return None
    count = len(media.get("data") or [])
    return round(min(10.0, count / 2.0), 1)


# ── 3. Review sentiment (comments on our own recent posts) ───────────────────

_POSITIVE = [
    "love", "amazing", "best", "great", "tasty", "awesome", "favourite", "favorite",
    "super", "nice", "wow", "pure", "fresh", "excellent", "perfect", "yum",
    "must try", "ordered", "recommend", "❤", "😍", "🔥", "👌", "☕",
]
_NEGATIVE = [
    "bad", "worst", "fake", "hate", "scam", "poor", "disappointed", "refund",
    "never again", "waste", "overpriced", "stale", "cheap quality",
]


def fetch_review_sentiment() -> float | None:
    """
    Keyword sentiment across comments on our last 10 published posts.
    5.0 = neutral/no comments; scale 0-10. None if API unreachable.
    """
    if not os.path.exists(_POSTS_PATH):
        return None
    try:
        with open(_POSTS_PATH, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except Exception:
        return None

    media_ids = [p["media_id"] for p in posts[-10:] if p.get("media_id")]
    if not media_ids:
        return None

    pos = neg = total = 0
    api_reached = False
    for mid in media_ids:
        data = _graph_get(f"{mid}/comments", {"fields": "text", "limit": 50})
        if data is None:
            continue
        api_reached = True
        for c in data.get("data") or []:
            text = str(c.get("text", "")).lower()
            if not text:
                continue
            total += 1
            if any(w in text for w in _POSITIVE):
                pos += 1
            elif any(w in text for w in _NEGATIVE):
                neg += 1

    if not api_reached:
        return None
    if total == 0 or (pos + neg) == 0:
        return 5.0  # comments exist but neutral, or no comments yet
    return round(max(0.0, min(10.0, 5.0 + 5.0 * (pos - neg) / (pos + neg))), 1)


# ── Weekly updater ────────────────────────────────────────────────────────────

def update_brand_equity_inputs() -> dict:
    """
    Refresh brand_equity_inputs.json with whatever sources succeeded.
    Failed sources preserve the existing (possibly manual) value.
    """
    existing = {}
    if os.path.exists(_EQUITY_INPUTS):
        try:
            with open(_EQUITY_INPUTS, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    results = {
        "branded_search_index": fetch_branded_search_index(),
        "ugc_creation_rate":    fetch_ugc_rate(),
        "review_sentiment":     fetch_review_sentiment(),
    }

    updated, sources = dict(existing), {}
    for key, value in results.items():
        if value is not None:
            updated[key] = value
            sources[key] = "auto"
        else:
            sources[key] = "kept_existing" if key in existing else "missing"

    updated["_last_auto_update"] = datetime.datetime.now().isoformat(timespec="seconds")
    updated["_sources"] = sources

    os.makedirs(_LEARNING_DIR, exist_ok=True)
    with open(_EQUITY_INPUTS, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)

    logger.info("[signals] Brand equity inputs updated: %s", sources)
    return updated
