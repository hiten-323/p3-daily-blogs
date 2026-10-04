"""
Conversion analyzer — funnel analysis and ROI reports.

Answers:
  • Where does the funnel leak? (visit → cart → purchase drop-offs)
  • Which content type converts best?
  • Which hook archetype drives the most purchases?
  • Is distributor content undervalued by views but overvalued by revenue?
"""
from content_generator.core.ist_dates import today_ist
import datetime
import logging

logger = logging.getLogger(__name__)


def get_funnel_report(days: int = 30) -> dict:
    """
    Return an aggregated conversion funnel for all content.

    Output:
    {
        "total_visits":         1240,
        "total_carts":          320,
        "total_purchases":      62,
        "visit_to_cart_pct":    25.8,
        "cart_to_purchase_pct": 19.4,
        "overall_cvr_pct":      5.0,
        "total_revenue":        15420,
        "revenue_per_visit":    12.4,
    }
    """
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()

    with _conn() as con:
        rows = con.execute("""
            SELECT event_type, COUNT(*) AS cnt, SUM(revenue) AS rev
            FROM revenue_attribution
            WHERE date >= ?
            GROUP BY event_type
        """, (cutoff,)).fetchall()

    data = {r["event_type"]: {"count": r["cnt"], "revenue": r["rev"] or 0} for r in rows}
    visits    = data.get("visit",    {}).get("count", 0)
    carts     = data.get("cart",     {}).get("count", 0)
    purchases = data.get("purchase", {}).get("count", 0)
    revenue   = data.get("purchase", {}).get("revenue", 0.0)

    return {
        "period_days":          days,
        "total_visits":         visits,
        "total_carts":          carts,
        "total_purchases":      purchases,
        "visit_to_cart_pct":    round(carts    / max(visits, 1) * 100, 1),
        "cart_to_purchase_pct": round(purchases / max(carts, 1)  * 100, 1),
        "overall_cvr_pct":      round(purchases / max(visits, 1) * 100, 2),
        "total_revenue":        round(revenue, 2),
        "revenue_per_visit":    round(revenue / max(visits, 1), 2),
    }


def get_content_type_roi(days: int = 30) -> list[dict]:
    """
    Break down revenue by content type (reel vs carousel vs linkedin vs blog).
    Infers type from content_id prefix convention:
      reel_*  | carousel_* | linkedin_* | blog_* | insta_* | yt_*
    """
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()

    with _conn() as con:
        rows = con.execute("""
            SELECT content_id, SUM(revenue) AS revenue, SUM(orders) AS orders
            FROM revenue_attribution
            WHERE date >= ? AND event_type='purchase'
            GROUP BY content_id
        """, (cutoff,)).fetchall()

    type_agg: dict[str, dict] = {}
    for r in rows:
        cid   = r["content_id"]
        ctype = cid.split("_")[0] if "_" in cid else "other"
        if ctype not in type_agg:
            type_agg[ctype] = {"content_type": ctype, "pieces": 0, "revenue": 0.0, "orders": 0}
        type_agg[ctype]["pieces"]  += 1
        type_agg[ctype]["revenue"] += r["revenue"] or 0
        type_agg[ctype]["orders"]  += r["orders"] or 0

    for v in type_agg.values():
        v["avg_revenue_per_piece"] = round(v["revenue"] / max(v["pieces"], 1), 2)

    return sorted(type_agg.values(), key=lambda x: x["revenue"], reverse=True)


def get_hook_roi(days: int = 30) -> list[dict]:
    """
    Join hook_performance with revenue_attribution to rank hooks by actual revenue.
    This surface the hooks that both go viral AND convert to sales.
    """
    from content_generator.analytics.metrics_store import _ensure_init, _conn
    _ensure_init()
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()

    with _conn() as con:
        rows = con.execute("""
            SELECT
                cm.hook_archetype,
                COUNT(cm.id)          AS pieces,
                AVG(cm.viral_score)   AS avg_viral_score,
                AVG(cm.views)         AS avg_views,
                COALESCE(SUM(ra.revenue), 0) AS total_revenue
            FROM content_metrics cm
            LEFT JOIN revenue_attribution ra
                ON cm.content_id = ra.content_id AND ra.event_type = 'purchase'
            WHERE cm.date >= ? AND cm.hook_archetype != ''
            GROUP BY cm.hook_archetype
            ORDER BY total_revenue DESC
        """, (cutoff,)).fetchall()

    return [dict(r) for r in rows]


def get_roi_report(days: int = 30) -> dict:
    """
    Return a single comprehensive ROI report dict.
    Used by dashboard/weekly_summary.py.
    """
    return {
        "funnel":            get_funnel_report(days=days),
        "by_content_type":   get_content_type_roi(days=days),
        "by_hook":           get_hook_roi(days=days),
        "generated_at":      datetime.datetime.now().isoformat(timespec="seconds"),
    }
