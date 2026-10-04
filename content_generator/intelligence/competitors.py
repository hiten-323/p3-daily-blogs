"""
Competitor intelligence module.

Stores and retrieves competitor post data.
Manual entry today; plug in Apify/PhantomBuster/RapidAPI scrapers
by replacing the fetch stubs with real API calls.

Data stored in: output/competitors.json  (or COMPETITOR_DATA_PATH env var)
"""
from content_generator.core.ist_dates import today_ist
import json
import os
import logging
import datetime

logger = logging.getLogger(__name__)

_DATA_PATH = os.getenv(
    "COMPETITOR_DATA_PATH",
    os.path.join("output", "competitors.json"),
)

# Tracked competitors — add or remove as needed
TRACKED_COMPETITORS = [
    "Nescafe India",
    "Bru Coffee",
    "Continental Coffee",
    "Rage Coffee",
    "Blue Tokai",
    "Sleepy Owl",
    "Third Wave Coffee",
]


# ── Storage ───────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if os.path.exists(_DATA_PATH):
        try:
            with open(_DATA_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("[competitors] Load failed: %s", e)
    return []


def _save(data: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(_DATA_PATH)), exist_ok=True)
    with open(_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data[-500:], f, indent=2, ensure_ascii=False)  # keep latest 500


# ── Public API ────────────────────────────────────────────────────────────────

def record_competitor_post(
    competitor: str,
    post_type: str,             # reel | carousel | post | story
    hook_text: str,
    views: int       = 0,
    likes: int       = 0,
    shares: int      = 0,
    saves: int       = 0,
    notes: str       = "",
    platform: str    = "instagram",
) -> None:
    """
    Manually log a competitor's high-performing post.
    Call this whenever you spot a competitor post doing well.

    Example:
        record_competitor_post(
            "Rage Coffee", "reel",
            "Nobody tells you this about your morning coffee...",
            views=250000, shares=3200
        )
    """
    data = _load()
    data.append({
        "competitor":   competitor,
        "post_type":    post_type,
        "hook_text":    hook_text,
        "views":        views,
        "likes":        likes,
        "shares":       shares,
        "saves":        saves,
        "notes":        notes,
        "platform":     platform,
        "recorded_at":  today_ist().isoformat(),
    })
    _save(data)
    logger.info("[competitors] Logged '%s' from %s (%d views)", hook_text[:40], competitor, views)


def get_top_hooks(limit: int = 5, min_views: int = 0) -> list[dict]:
    """Return top competitor hooks sorted by views."""
    data = _load()
    filtered = [d for d in data if d.get("views", 0) >= min_views]
    return sorted(filtered, key=lambda x: x.get("views", 0), reverse=True)[:limit]


def format_competitor_context(limit: int = 3) -> str:
    """Format competitor insights as a prompt injection block."""
    hooks = get_top_hooks(limit=limit)
    if not hooks:
        return ""
    lines = [
        "COMPETITOR TOP-PERFORMING HOOKS — differentiate aggressively from these:",
    ]
    for h in hooks:
        lines.append(
            f"  • {h['competitor']}: \"{h['hook_text']}\" "
            f"({h.get('views', 0):,} views on {h.get('platform', 'instagram')})"
        )
    return "\n".join(lines)


def get_summary() -> dict:
    """Return a compact summary dict for logging / dashboard use."""
    data = _load()
    if not data:
        return {"total_posts_tracked": 0}
    top = get_top_hooks(limit=1)
    return {
        "total_posts_tracked": len(data),
        "competitors_tracked": len({d["competitor"] for d in data}),
        "top_competitor":      top[0]["competitor"] if top else "",
        "top_views":           top[0].get("views", 0) if top else 0,
        "top_hook":            top[0]["hook_text"][:60] if top else "",
    }
