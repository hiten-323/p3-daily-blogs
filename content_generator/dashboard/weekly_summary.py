"""
Weekly summary — auto-generated every Monday morning.

Delivered automatically when scheduler runs on Monday.
Contains actionable insights, not just metrics.

Output:
  • JSON saved to output/weekly_summary_YYYY-WNN.json
  • Console printout
  • Optional email via SMTP (SUMMARY_EMAIL_TO env var)

Schedule: triggered from scheduler/daily.py when weekday == Monday (0).
"""
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

_EMAIL_TO   = os.getenv("SUMMARY_EMAIL_TO",   "")
_EMAIL_FROM = os.getenv("SUMMARY_EMAIL_FROM", "")
_SMTP_HOST  = os.getenv("SMTP_HOST",          "smtp.gmail.com")
_SMTP_PORT  = int(os.getenv("SMTP_PORT",      "587"))
_SMTP_PASS  = os.getenv("SMTP_PASSWORD",      "")


def generate_weekly_summary(days: int = 7) -> dict:
    """
    Generate the complete weekly summary.
    Saved to output/ and returned as a dict.
    """
    from content_generator.dashboard.metrics import get_all_metrics
    from content_generator.analytics.revenue_tracker import get_revenue_summary, get_week_over_week
    from content_generator.strategy.content_mix_optimizer import get_todays_mix, get_weekly_content_plan
    from content_generator.strategy.hook_optimizer import get_hook_performance_table

    today     = today_ist()
    week_str  = today.strftime("%Y-W%V")
    metrics   = get_all_metrics(days=days)

    pipeline = metrics.get("pipeline", {})

    summary = {
        "week":              week_str,
        "generated_at":      datetime.datetime.now().isoformat(timespec="seconds"),
        "period":            f"{days} days ending {today.isoformat()}",
        "top_hook":          _top_hook(metrics),
        "top_cta":           _top_cta(),
        "top_audience":      _top_audience(metrics),
        "revenue":           metrics.get("revenue", {}),
        "funnel":            metrics.get("funnel", {}),
        "best_content":      _best_content(metrics),
        "recommended_mix":   get_todays_mix(),
        "next_week_plan":    _build_next_week_plan(),
        # ── Sales Engine KPIs (new) ────────────────────────────────────────
        "distributor_leads_captured": _count_segment_leads(pipeline, "distributor"),
        "retailer_leads_captured":    _count_segment_leads(pipeline, "retailer"),
        "total_leads_captured":       pipeline.get("total_leads", 0),
        "hot_leads":                  pipeline.get("hot_leads", 0),
        "stalling_leads_count":       pipeline.get("stalling_leads", 0),
        "pipeline_ev_total":          pipeline.get("total_pipeline_ev", 0.0),
        "pipeline_by_segment":        pipeline.get("by_segment", {}),
        "top_content_by_leads":       pipeline.get("top_content_by_leads", []),
        # ──────────────────────────────────────────────────────────────────
        "action_items":      _generate_action_items(metrics),
        "alerts":            _generate_alerts(metrics),
    }

    path = _save_summary(summary, week_str)
    logger.info("[weekly_summary] Saved → %s", path)

    _print_summary(summary)

    if _EMAIL_TO:
        _email_summary(summary)

    return summary


def _count_segment_leads(pipeline: dict, segment: str) -> int:
    return pipeline.get("by_segment", {}).get(segment, {}).get("leads", 0)


def _top_hook(metrics: dict) -> dict:
    hooks = metrics.get("hooks", {}).get("ranked", [])
    if not hooks:
        return {"hook": "No data yet", "avg_views": 0, "avg_viral_score": 0}
    top = hooks[0]
    return {
        "hook":            top.get("hook", ""),
        "avg_views":       top.get("avg_views", 0),
        "avg_viral_score": top.get("avg_viral_score", 0),
        "total_revenue":   top.get("total_revenue", 0),
    }


def _top_cta() -> dict:
    try:
        from content_generator.analytics.metrics_store import get_cta_performance
        ctas = get_cta_performance(min_clicks=3)
        if ctas:
            return {"cta": ctas[0]["cta_text"], "conv_rate": ctas[0].get("conv_rate", 0)}
    except Exception as _e:
        logger.debug("[weekly_summary] optional step failed: %s", _e)
    return {"cta": "No data yet", "conv_rate": 0}


def _top_audience(metrics: dict) -> str:
    aud = metrics.get("audience", {}).get("revenue_breakdown", [])
    if aud:
        return aud[0].get("audience", "consumer")
    return "consumer"


def _best_content(metrics: dict) -> list[dict]:
    return metrics.get("content", {}).get("top_pieces", [])[:3]


def _build_next_week_plan() -> list[dict]:
    try:
        from content_generator.rotation import get_day_number
        from content_generator.strategy.content_mix_optimizer import get_weekly_content_plan
        dn = get_day_number()
        return get_weekly_content_plan(start_day=dn + 1)
    except Exception:
        return []


def _generate_action_items(metrics: dict) -> list[str]:
    """Generate 3-5 actionable recommendations based on the data."""
    actions = []

    # Revenue trend
    wow = metrics.get("revenue", {}).get("week_over_week", {})
    if wow.get("trend") == "down" and abs(wow.get("change_pct", 0)) > 10:
        actions.append(
            f"Revenue down {abs(wow.get('change_pct',0)):.0f}% WoW — "
            f"increase consumer_purchase content and check CTAs"
        )

    # Hook performance
    hooks = metrics.get("hooks", {}).get("ranked", [])
    if hooks:
        top  = hooks[0].get("hook", "")
        weak = [h["hook"] for h in hooks if h.get("avg_viral_score", 50) < 40]
        if top:
            actions.append(f"Double down on '{top}' hook — consistently outperforming others")
        if weak:
            actions.append(f"Retire weak hooks: {', '.join(weak[:3])}")

    # Funnel
    funnel = metrics.get("funnel", {})
    cvr    = funnel.get("overall_cvr_pct", 0)
    if cvr and cvr < 2:
        actions.append(
            f"Overall CVR only {cvr:.2f}% — test stronger CTAs and product page landing"
        )

    # Audience
    aud_data = metrics.get("audience", {}).get("revenue_breakdown", [])
    if aud_data:
        high_val = [a for a in aud_data if a.get("audience") == "distributor"]
        if not high_val:
            actions.append(
                "No distributor revenue tracked this week — "
                "ensure LinkedIn posts include distributor CTA"
            )

    # Pipeline / Sales Engine actions
    pipeline = metrics.get("pipeline", {})
    stalling = pipeline.get("stalling_leads", 0)
    if stalling > 0:
        actions.append(
            f"{stalling} lead(s) stalling — run nurture sequences or reassign"
        )
    dist_leads = pipeline.get("by_segment", {}).get("distributor", {}).get("leads", 0)
    if dist_leads == 0:
        actions.append(
            "No distributor leads captured this week — "
            "push at least 2 distributor-targeted LinkedIn posts"
        )
    pipeline_ev = pipeline.get("total_pipeline_ev", 0.0)
    if pipeline_ev > 0:
        actions.append(
            f"Pipeline EV is Rs {pipeline_ev:,.0f} — "
            f"focus nurture on hot leads to unlock near-term revenue"
        )

    if not actions:
        actions.append("All metrics healthy — maintain current content mix")

    return actions[:5]


def _generate_alerts(metrics: dict) -> list[str]:
    """Generate critical alerts that need immediate attention."""
    alerts = []

    health = metrics.get("system_health", {})
    if health.get("status") not in ("healthy", "unknown", ""):
        alerts.append(f"SYSTEM: {health.get('status', 'degraded')}")

    r = metrics.get("revenue", {})
    if r.get("total_revenue", 0) == 0 and r.get("period_days", 7) >= 7:
        alerts.append("WARNING: Zero revenue tracked this week — check attribution setup")

    return alerts


def _save_summary(summary: dict, week_str: str) -> str:
    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", f"weekly_summary_{week_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    return path


def _print_summary(summary: dict) -> None:
    SEP  = "=" * 60
    SEP2 = "-" * 60
    print(f"\n{SEP}")
    print(f"  PURITY BEANS — WEEKLY SUMMARY {summary['week']}")
    print(f"  {summary['period']}")
    print(SEP)

    r = summary.get("revenue", {})
    print(f"\n  REVENUE")
    print(f"    Total:    Rs {r.get('total_revenue', 0):,.0f}")
    print(f"    Orders:   {r.get('total_orders', 0)}")
    print(f"    ROAS:     {r.get('roas', 0):.1f}x")

    print(f"\n  TOP HOOK")
    h = summary.get("top_hook", {})
    print(f"    {h.get('hook', '?')} — viral={h.get('avg_viral_score',0):.0f}  rev=Rs{h.get('total_revenue',0):,.0f}")

    print(f"\n  TOP AUDIENCE:  {summary.get('top_audience', '?')}")

    # Pipeline / Sales Engine section
    print(f"\n  PIPELINE (Sales Engine)")
    print(f"    Total Leads:       {summary.get('total_leads_captured', 0)}")
    print(f"    Hot Leads:         {summary.get('hot_leads', 0)}")
    print(f"    Stalling Leads:    {summary.get('stalling_leads_count', 0)}")
    print(f"    Pipeline EV:       Rs {summary.get('pipeline_ev_total', 0):,.0f}")
    by_seg = summary.get("pipeline_by_segment", {})
    if by_seg:
        for seg, data in by_seg.items():
            print(f"      {seg:<15} leads={data.get('leads',0):>3}  ev=Rs {data.get('pipeline_ev',0):>12,.0f}")
    top_cl = summary.get("top_content_by_leads", [])
    if top_cl:
        print(f"\n  TOP CONTENT BY LEADS")
        for row in top_cl[:3]:
            print(f"    {row.get('content_id','?'):<25}  leads={row.get('leads',0):>3}  ev=Rs{row.get('total_ev',0):>10,.0f}")

    print(f"\n  ACTION ITEMS")
    for action in summary.get("action_items", []):
        print(f"    * {action}")

    if summary.get("alerts"):
        print(f"\n  ALERTS")
        for a in summary["alerts"]:
            print(f"    ! {a}")

    print(f"\n{SEP}\n")


def _email_summary(summary: dict) -> None:
    """Email the summary via SMTP. Silently skips if not configured."""
    if not all([_EMAIL_TO, _EMAIL_FROM, _SMTP_PASS]):
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        subject = f"Purity Beans Weekly Summary {summary['week']}"
        body    = json.dumps(summary, indent=2, ensure_ascii=False, default=str)
        msg     = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = _EMAIL_FROM
        msg["To"]      = _EMAIL_TO
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.starttls()
            server.login(_EMAIL_FROM, _SMTP_PASS)
            server.send_message(msg)
        logger.info("[weekly_summary] Email sent to %s", _EMAIL_TO)
    except Exception as e:
        logger.warning("[weekly_summary] Email failed: %s", e)
