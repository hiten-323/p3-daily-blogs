"""
Revenue Attribution Engine.

Generates UTM-tagged tracking URLs for every content piece so website analytics
can link a purchase back to the exact content_id that drove it.

Then records those conversions back into metrics.db so the optimizer learns
which content drives actual rupees — not just views.

UTM structure:
  utm_source   = platform  (instagram | linkedin | youtube | whatsapp)
  utm_medium   = social
  utm_campaign = content_engine
  utm_content  = content_id  (e.g. reel_1_day42)

Usage:
    from content_generator.analytics.attribution import (
        generate_tracking_url,
        record_conversion,
        get_content_roas,
    )

    # When creating content
    url = generate_tracking_url("reel_1_day42", platform="instagram")
    # → https://p3online.in?utm_source=instagram&utm_medium=social&...

    # When Shopify webhook fires (or manual entry)
    record_conversion("reel_1_day42", revenue=4230, orders=17, spend=750)
"""
import logging
import os
from urllib.parse import urlencode, urljoin

logger = logging.getLogger(__name__)

_WEBSITE = os.getenv("WEBSITE_URL", "https://p3online.in")
_CAMPAIGN = os.getenv("UTM_CAMPAIGN", "202610")


# ── UTM link generation ───────────────────────────────────────────────────────

def generate_tracking_url(
    content_id: str,
    platform: str    = "instagram",
    path: str        = "/",
    extra_params: dict = None,
) -> str:
    """
    Generate a UTM-tagged tracking URL for a content piece.

    Args:
        content_id:   e.g. "reel_1_day42" or "carousel_day15"
        platform:     "instagram" | "linkedin" | "youtube" | "whatsapp"
        path:         URL path relative to website root  (default "/")
        extra_params: any additional query params to include

    Returns:
        Full tracking URL as a string.
    """
    params = {
        "utm_source":   platform,
        "utm_medium":   "post",
        "utm_campaign": _CAMPAIGN,
        "utm_content":  content_id,
    }
    if extra_params:
        params.update(extra_params)

    base = urljoin(_WEBSITE.rstrip("/") + "/", path.lstrip("/"))
    return f"{base}?{urlencode(params)}"


def generate_all_tracking_urls(content_id: str) -> dict[str, str]:
    """
    Generate tracking URLs for all active platforms at once.
    Returns dict keyed by platform name.
    """
    platforms = ["instagram", "linkedin", "youtube", "whatsapp", "facebook"]
    return {p: generate_tracking_url(content_id, platform=p) for p in platforms}


# ── Conversion recording ──────────────────────────────────────────────────────

def record_conversion(
    content_id: str,
    revenue: float,
    orders: int    = 1,
    spend: float   = 0.0,
    platform: str  = "instagram",
    audience: str  = "consumer",
) -> dict:
    """
    Record a completed purchase attributed to a content piece.

    Call this when:
      • Shopify webhook fires with utm_content matching a content_id
      • Manual daily entry from analytics dashboard
      • Automated attribution via Google Analytics API

    Args:
        content_id: matches the content_id in generate_tracking_url()
        revenue:    gross revenue in INR (e.g. 4230.0)
        orders:     number of orders (default 1)
        spend:      ad spend for this content (0 if organic)
        platform:   traffic source platform
        audience:   who bought — consumer | retailer | distributor

    Returns:
        dict with revenue, orders, roas
    """
    from content_generator.analytics.metrics_store import record_revenue, get_revenue_by_content
    record_revenue(
        content_id=content_id,
        revenue=revenue,
        orders=orders,
        spend=spend,
        platform=platform,
        audience=audience,
        event_type="purchase",
    )
    result = get_revenue_by_content(content_id)
    logger.info(
        "[attribution] %s → Rs %.0f total | %d orders | ROAS %.1fx",
        content_id, result["total_revenue"], result["total_orders"], result["roas"],
    )
    return result


def record_visit(content_id: str, platform: str = "instagram") -> None:
    """Record a website visit attributed to content (top of funnel)."""
    from content_generator.analytics.metrics_store import record_revenue
    record_revenue(content_id, revenue=0, orders=0, platform=platform, event_type="visit")


def record_add_to_cart(content_id: str, platform: str = "instagram") -> None:
    """Record an add-to-cart event (mid-funnel)."""
    from content_generator.analytics.metrics_store import record_revenue
    record_revenue(content_id, revenue=0, orders=0, platform=platform, event_type="cart")


# ── ROAS retrieval ────────────────────────────────────────────────────────────

def get_content_roas(content_id: str) -> dict:
    """
    Return ROAS and revenue stats for a specific content piece.

    ROAS = Total Revenue / Total Spend
    A ROAS of 5.8 means Rs 5.80 returned for every Rs 1 spent.
    """
    from content_generator.analytics.metrics_store import get_revenue_by_content
    return get_revenue_by_content(content_id)


def record_lead_attribution(lead_id: str, content_id: str) -> None:
    """
    Explicitly link a lead to the content that generated it.

    Call this when a lead is captured from a trackable content piece.
    Closes the content → lead → revenue attribution loop so you can query:
      "Which Reel generated the most distributor leads this month?"

    This is stored as a revenue_attribution event with event_type='lead_captured'
    so it flows through the same funnel reporting pipeline.
    """
    if not lead_id or not content_id:
        return
    try:
        from content_generator.analytics.metrics_store import record_revenue
        record_revenue(
            content_id=content_id,
            revenue=0.0,
            orders=0,
            platform="",
            event_type="lead_captured",
            audience=lead_id,   # store lead_id in audience column for traceability
        )
        logger.info("[attribution] Lead %s attributed to content %s", lead_id, content_id)
    except Exception as e:
        logger.warning("[attribution] record_lead_attribution failed: %s", e)


def get_content_lead_count(content_id: str) -> int:
    """Return the number of leads generated by a specific content piece."""
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    with _conn() as con:
        row = con.execute("""
            SELECT COUNT(*) AS cnt FROM revenue_attribution
            WHERE content_id=? AND event_type='lead_captured'
        """, (content_id,)).fetchone()
    return int(row["cnt"]) if row else 0


def get_conversion_funnel(content_id: str) -> dict:
    """
    Return funnel breakdown: visits → carts → purchases.
    """
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    with _conn() as con:
        rows = con.execute("""
            SELECT event_type, COUNT(*) AS count, SUM(revenue) AS revenue
            FROM revenue_attribution
            WHERE content_id=?
            GROUP BY event_type
        """, (content_id,)).fetchall()

    funnel = {"visit": 0, "cart": 0, "purchase": 0, "revenue": 0.0}
    for r in rows:
        et = r["event_type"]
        if et in funnel:
            funnel[et] = r["count"]
        if et == "purchase":
            funnel["revenue"] = r["revenue"] or 0.0

    # Conversion rates
    funnel["visit_to_cart_pct"] = (
        round(funnel["cart"] / funnel["visit"] * 100, 1)
        if funnel["visit"] else 0.0
    )
    funnel["cart_to_purchase_pct"] = (
        round(funnel["purchase"] / funnel["cart"] * 100, 1)
        if funnel["cart"] else 0.0
    )
    return funnel
