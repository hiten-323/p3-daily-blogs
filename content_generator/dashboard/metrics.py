"""
Dashboard metrics aggregator.

Single entry point for all KPI data — called by reports.py and weekly_summary.py.
Every metric degrades gracefully when data is sparse.
"""
from content_generator.core.ist_dates import today_ist
import datetime
import logging

logger = logging.getLogger(__name__)


def get_all_metrics(days: int = 7) -> dict:
    """
    Return a comprehensive metrics snapshot for the dashboard period.

    Structure:
    {
        "period":           "7 days ending 2026-06-09",
        "content":          { pieces_generated, viral scores, top pieces },
        "revenue":          { total, orders, ROAS, week-over-week },
        "audience":         { breakdown by segment },
        "hooks":            { ranked by viral score + revenue },
        "funnel":           { visit→cart→purchase conversion rates },
        "memory":           { total pieces stored, similarity engine },
        "trends":           { top trends this period },
        "competitors":      { top competitor hooks tracked },
        "system_health":    { api status, last run, errors },
    }
    """
    cutoff = today_ist() - datetime.timedelta(days=days)
    period = f"{days} days ending {today_ist().isoformat()}"

    metrics: dict = {"period": period, "days": days}

    metrics["content"]       = _content_metrics(days)
    metrics["revenue"]       = _revenue_metrics(days)
    metrics["audience"]      = _audience_metrics(days)
    metrics["hooks"]         = _hook_metrics(days)
    metrics["funnel"]        = _funnel_metrics(days)
    metrics["memory"]        = _memory_metrics()
    metrics["trends"]        = _trend_metrics()
    metrics["competitors"]   = _competitor_metrics()
    metrics["system_health"] = _health_metrics()
    metrics["pipeline"]      = _lead_metrics()

    return metrics


# ── Individual metric collectors ──────────────────────────────────────────────

def _content_metrics(days: int) -> dict:
    try:
        from content_generator.analytics.metrics_store import get_recent_metrics
        rows = get_recent_metrics(days=days)
        if not rows:
            return {"pieces": 0, "avg_viral_score": 0, "top_pieces": []}
        avg  = sum(r["viral_score"] for r in rows) / len(rows)
        top3 = rows[:3]
        return {
            "pieces":          len(rows),
            "avg_viral_score": round(avg, 1),
            "top_pieces":      [
                {"content_id": r["content_id"], "viral_score": r["viral_score"],
                 "views": r["views"], "hook": r.get("hook_archetype", "")}
                for r in top3
            ],
        }
    except Exception as e:
        logger.debug("[dashboard] content_metrics failed: %s", e)
        return {"pieces": 0, "avg_viral_score": 0, "top_pieces": []}


def _revenue_metrics(days: int) -> dict:
    try:
        from content_generator.analytics.revenue_tracker import (
            get_revenue_summary, get_week_over_week,
        )
        summary = get_revenue_summary(days=days)
        wow     = get_week_over_week() if days <= 7 else {}
        return {**summary, "week_over_week": wow}
    except Exception as e:
        logger.debug("[dashboard] revenue_metrics failed: %s", e)
        return {"total_revenue": 0, "total_orders": 0, "roas": 0}


def _audience_metrics(days: int) -> dict:
    try:
        from content_generator.analytics.revenue_tracker import get_revenue_by_audience
        from content_generator.strategy.audience_optimizer import get_audience_performance_report
        rev_by_aud  = get_revenue_by_audience(days=days)
        perf_report = get_audience_performance_report(days=days)
        return {"revenue_breakdown": rev_by_aud, "performance": perf_report}
    except Exception as e:
        logger.debug("[dashboard] audience_metrics failed: %s", e)
        return {"revenue_breakdown": [], "performance": []}


def _hook_metrics(days: int) -> dict:
    try:
        from content_generator.strategy.hook_optimizer import get_hook_performance_table
        table = get_hook_performance_table()
        return {"ranked": table[:10]}
    except Exception as e:
        logger.debug("[dashboard] hook_metrics failed: %s", e)
        return {"ranked": []}


def _funnel_metrics(days: int) -> dict:
    try:
        from content_generator.analytics.conversion_analyzer import get_funnel_report
        return get_funnel_report(days=days)
    except Exception as e:
        logger.debug("[dashboard] funnel_metrics failed: %s", e)
        return {}


def _memory_metrics() -> dict:
    try:
        from content_generator.memory.semantic import memory_stats
        return memory_stats()
    except Exception:
        return {}


def _trend_metrics() -> dict:
    try:
        from content_generator.analytics.metrics_store import get_cached_trends
        return {"top_trends": get_cached_trends(max_age_hours=48)[:5]}
    except Exception:
        return {"top_trends": []}


def _competitor_metrics() -> dict:
    try:
        from content_generator.intelligence.competitors import get_top_hooks, get_summary
        return {"top_hooks": get_top_hooks(limit=3), "summary": get_summary()}
    except Exception:
        return {"top_hooks": [], "summary": {}}


def _health_metrics() -> dict:
    try:
        from content_generator.scheduler.health_monitor import get_health_report
        return get_health_report()
    except Exception:
        return {"status": "unknown"}


def _lead_metrics() -> dict:
    """
    Pipeline KPIs — the Sales Engine view.

    Returns:
    {
        "total_leads":        52,
        "hot_leads":          4,
        "stalling_leads":     7,
        "total_pipeline_ev":  4732000,
        "by_segment": {
            "distributor":    {"leads": 8,  "pipeline_ev": 3240000},
            "retailer":       {"leads": 31, "pipeline_ev": 486000},
            "consumer":       {"leads": 13, "pipeline_ev": 6300},
        },
        "top_content_by_leads": [
            {"content_id": "reel_1_day42", "leads": 6, "total_ev": 720000},
            ...
        ],
    }
    """
    try:
        from content_generator.crm.pipeline_tracker import get_pipeline_report
        report = get_pipeline_report()

        # Flatten by_segment to simpler leads + ev summary
        by_seg_flat: dict = {}
        for seg, stages in report.get("by_segment", {}).items():
            total_leads = sum(s.get("count", 0) for s in stages.values())
            total_ev    = sum(s.get("total_ev", 0.0) for s in stages.values())
            by_seg_flat[seg] = {
                "leads":       total_leads,
                "pipeline_ev": round(total_ev, 2),
            }

        return {
            "total_leads":           report.get("total_leads", 0),
            "hot_leads":             len(report.get("hot_leads", [])),
            "stalling_leads":        len(report.get("stalling_leads", [])),
            "total_pipeline_ev":     report.get("total_pipeline_ev", 0.0),
            "by_segment":            by_seg_flat,
            "top_content_by_leads":  report.get("content_attribution", [])[:5],
        }
    except Exception as e:
        logger.debug("[dashboard] lead_metrics failed: %s", e)
        return {
            "total_leads":       0,
            "hot_leads":         0,
            "stalling_leads":    0,
            "total_pipeline_ev": 0.0,
            "by_segment":        {},
            "top_content_by_leads": [],
        }
