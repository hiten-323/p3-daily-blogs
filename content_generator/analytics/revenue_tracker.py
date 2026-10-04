"""
Revenue tracker — aggregated views of monetary performance.

Answers the questions that actually matter for Purity Beans:
  • Which content pieces generated the most revenue?
  • What is the ROAS across all organic content?
  • Which audience segment (consumer / distributor / retailer) drives most value?
  • Is this week better or worse than last week in revenue terms?

All data comes from metrics_store.revenue_attribution — feed it via
attribution.record_conversion() or the Shopify webhook integration.
"""
from content_generator.core.ist_dates import today_ist
import datetime
import logging

logger = logging.getLogger(__name__)


def get_roas_leaderboard(days: int = 30, limit: int = 10) -> list[dict]:
    """
    Return content pieces ranked by ROAS (Return on Ad Spend).

    A piece with 20k views and Rs 5000 revenue ranks above
    one with 200k views and Rs 0 revenue.
    """
    from content_generator.analytics.metrics_store import get_revenue_leaders
    return get_revenue_leaders(days=days, limit=limit)


def get_revenue_summary(days: int = 30) -> dict:
    """
    Return a high-level revenue summary for the dashboard.

    Example output:
    {
        "period_days":    30,
        "total_revenue":  48230,
        "total_orders":   193,
        "avg_order_value": 250,
        "roas":            6.4,
        "best_piece":     "reel_1_day42",
        "best_revenue":   4230,
    }
    """
    from content_generator.analytics.metrics_store import get_total_revenue, get_revenue_leaders
    totals  = get_total_revenue(days=days)
    leaders = get_revenue_leaders(days=days, limit=1)

    summary = {
        "period_days":     days,
        "total_revenue":   round(totals.get("total_revenue") or 0, 2),
        "total_orders":    totals.get("total_orders") or 0,
        "total_spend":     round(totals.get("total_spend") or 0, 2),
        "roas":            totals.get("roas") or 0.0,
        "conversion_events": totals.get("conversion_events") or 0,
        "best_piece":      leaders[0]["content_id"]      if leaders else "",
        "best_revenue":    leaders[0]["total_revenue"]   if leaders else 0,
    }
    orders = summary["total_orders"]
    revenue = summary["total_revenue"]
    summary["avg_order_value"] = round(revenue / orders, 2) if orders else 0
    return summary


def get_revenue_by_audience(days: int = 30) -> list[dict]:
    """
    Return revenue breakdown by audience segment.
    Helps answer: should we produce more distributor content?
    """
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT
                audience,
                COUNT(DISTINCT content_id) AS pieces,
                SUM(revenue)               AS total_revenue,
                SUM(orders)                AS total_orders,
                AVG(revenue)               AS avg_revenue_per_piece
            FROM revenue_attribution
            WHERE date >= ? AND event_type='purchase'
            GROUP BY audience
            ORDER BY total_revenue DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def get_week_over_week() -> dict:
    """
    Compare this week's revenue to last week's.
    Returns percentage change.
    """
    from content_generator.analytics.metrics_store import get_total_revenue

    this_week = get_total_revenue(days=7)
    last_week_raw = _get_revenue_for_range(days_ago_start=14, days_ago_end=7)

    this_rev  = this_week.get("total_revenue") or 0.0
    last_rev  = last_week_raw.get("total_revenue") or 0.0
    change    = round(((this_rev - last_rev) / max(last_rev, 1)) * 100, 1)

    return {
        "this_week_revenue":  round(this_rev, 2),
        "last_week_revenue":  round(last_rev, 2),
        "change_pct":         change,
        "trend":              "up" if change > 0 else ("flat" if change == 0 else "down"),
        "this_week_orders":   this_week.get("total_orders") or 0,
    }


def _get_revenue_for_range(days_ago_start: int, days_ago_end: int) -> dict:
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    today   = today_ist()
    start   = (today - datetime.timedelta(days=days_ago_start)).isoformat()
    end     = (today - datetime.timedelta(days=days_ago_end)).isoformat()
    with _conn() as con:
        row = con.execute("""
            SELECT SUM(revenue) AS total_revenue, SUM(orders) AS total_orders
            FROM revenue_attribution
            WHERE date >= ? AND date < ? AND event_type='purchase'
        """, (start, end)).fetchone()
    return dict(row) if row else {}


def compute_content_value_score(
    viral_score: float,
    revenue: float,
    audience: str,
    business_value_weights: dict = None,
) -> float:
    """
    Compute a composite value score combining viral performance + revenue + business priority.

    This is what the strategy engine uses to decide what content to make more of.

    Formula:
        value = (viral_score × 0.3) + (revenue_score × 0.5) + (audience_weight × 0.2)

    Where revenue_score is normalised against Rs 10,000 ceiling.
    """
    _weights = business_value_weights or {
        "distributor":  10.0,
        "retailer":      5.0,
        "modern_trade":  8.0,
        "consumer":      1.0,
    }
    audience_w    = _weights.get(audience, 1.0) / 10.0   # normalise to 0-1
    revenue_score = min(revenue / 10_000, 1.0) * 100     # normalise to 0-100
    return round(
        viral_score * 0.30 + revenue_score * 0.50 + audience_w * 100 * 0.20,
        1,
    )
