"""
Trend detection module.

Source priority:
  1. pytrends (Google Trends)  — pip install pytrends
  2. PRAW (Reddit)             — pip install praw  + REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET
  3. DB cache (< 24 h old)
  4. Static baseline trends    — always available, never fails

Results are cached in metrics.db for 24 hours to avoid hammering APIs.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Coffee-specific keywords tracked on Google Trends (India)
_COFFEE_KEYWORDS = [
    "instant coffee India",
    "pure coffee India",
    "coffee vs chai",
    "cold coffee recipe",
    "best coffee brand India",
]

# Evergreen fallback — updated periodically in code; no API required
_BASELINE_TRENDS = [
    {"trend": "instant coffee India",          "velocity": 72, "source": "baseline"},
    {"trend": "cold coffee recipe India",      "velocity": 68, "source": "baseline"},
    {"trend": "pure coffee no chicory",        "velocity": 64, "source": "baseline"},
    {"trend": "coffee for work focus",         "velocity": 60, "source": "baseline"},
    {"trend": "coffee vs chai India debate",   "velocity": 55, "source": "baseline"},
    {"trend": "best affordable coffee India",  "velocity": 52, "source": "baseline"},
    {"trend": "protein coffee recipe",         "velocity": 48, "source": "baseline"},
]


def fetch_google_trends(keywords: list[str] = None) -> list[dict]:
    """Fetch 7-day trending interest from Google Trends (India)."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.debug("[trends] pytrends not installed — skip Google Trends")
        return []

    kws = keywords or _COFFEE_KEYWORDS
    try:
        pt = TrendReq(hl="en-IN", tz=330, timeout=(10, 25))  # IST = UTC+5:30
        pt.build_payload(kws, cat=0, timeframe="now 7-d", geo="IN")
        data = pt.interest_over_time()
        if data.empty:
            return []
        results = []
        for kw in kws:
            if kw in data.columns:
                avg = float(data[kw].mean())
                results.append({"trend": kw, "velocity": round(avg, 1), "source": "google_trends"})
        return sorted(results, key=lambda x: x["velocity"], reverse=True)
    except Exception as e:
        logger.warning("[trends] Google Trends error: %s", e)
        return []


def fetch_reddit_trends() -> list[dict]:
    """Fetch hot coffee/India posts from Reddit."""
    try:
        import praw
    except ImportError:
        logger.debug("[trends] praw not installed — skip Reddit")
        return []

    cid    = os.getenv("REDDIT_CLIENT_ID")
    secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        return []

    try:
        reddit = praw.Reddit(
            client_id=cid,
            client_secret=secret,
            user_agent="PurityBeans_ContentEngine/1.0",
        )
        results = []
        coffee_terms = {"coffee", "cafe", "caffeine", "espresso", "latte", "chicory"}
        for sub in ("coffee", "india", "IndianFood", "IndianStartups"):
            for post in reddit.subreddit(sub).hot(limit=15):
                if any(t in post.title.lower() for t in coffee_terms):
                    results.append({
                        "trend":    post.title[:80],
                        "velocity": round(min(post.score / 100, 100), 1),
                        "source":   f"reddit/r/{sub}",
                    })
        return sorted(results, key=lambda x: x["velocity"], reverse=True)[:6]
    except Exception as e:
        logger.warning("[trends] Reddit error: %s", e)
        return []


def get_todays_trends(force_refresh: bool = False) -> list[dict]:
    """
    Return today's trend list.
    Uses DB cache when fresh (< 24 h); otherwise fetches and caches.
    Always returns at least the baseline trends.
    """
    # Try cache first
    if not force_refresh:
        try:
            from content_generator.analytics.metrics_store import get_cached_trends
            cached = get_cached_trends(max_age_hours=24)
            if cached:
                logger.debug("[trends] %d cached trends", len(cached))
                return cached
        except Exception as _e:
            logger.debug("[trends] optional step failed: %s", _e)

    # Live fetch
    trends: list[dict] = []
    trends.extend(fetch_google_trends())
    trends.extend(fetch_reddit_trends())

    if not trends:
        logger.info("[trends] No live data — using baseline")
        trends = _BASELINE_TRENDS.copy()

    # Deduplicate by trend text
    seen: set[str] = set()
    unique: list[dict] = []
    for t in trends:
        key = t["trend"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    try:
        from content_generator.analytics.metrics_store import store_trends
        store_trends(unique)
    except Exception as e:
        logger.warning("[trends] Cache write failed: %s", e)

    return unique[:8]


def format_trends_for_prompt(trends: list[dict]) -> str:
    """Format as a compact prompt injection block."""
    if not trends:
        return ""
    lines = ["TODAY'S TRENDING TOPICS IN INDIA (weave in naturally if relevant):"]
    for t in trends[:5]:
        lines.append(f"  • {t['trend']} (velocity {t['velocity']:.0f}/100)")
    return "\n".join(lines)
