"""
WhatsApp morning report — daily founder briefing.

Sent after every successful pipeline run. Gives the founder a clean,
actionable summary without requiring them to check logs or dashboards.

Sample message:
  PURITY BEANS — Day 47 Complete

  Content Generated:
    2 Reels
    1 Carousel
    1 LinkedIn Post
    1 Blog Post
    1 Story Sequence

  Today's Objective: Distributor Leads
  Today's Audience:  LinkedIn Professionals

  Top Trend:  Cold Coffee Protein
  Top Hook:   EXPOSE (avg viral score 71)

  Pipeline:
    Hot Leads:     3
    Pipeline EV:   Rs 27,00,000
    Stalling:      1 lead needs follow-up

  Health: All systems operational

  Next run: Tomorrow 06:00 IST

Requires:
  WHATSAPP_TOKEN, WHATSAPP_PHONE_ID — Meta Cloud API credentials
  FOUNDER_PHONE — your WhatsApp number in E.164 format (+91XXXXXXXXXX)

If WhatsApp is not configured, the report is printed to the console
and sent via the watchdog alert channel (Slack/Discord webhook).
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_FOUNDER_PHONE = os.getenv("FOUNDER_PHONE", "")


def send_founder_report(content: dict, pipeline_result: dict = None) -> bool:
    """
    Send the daily founder WhatsApp report.

    Args:
        content:         The generated content dict from run_full_pipeline()
        pipeline_result: Optional dict with nurture/lead stats

    Returns True if the message was sent successfully.
    """
    report = _build_report(content, pipeline_result or {})
    logger.info("[founder_report]\n%s", report)

    # Try WhatsApp first
    if _FOUNDER_PHONE and _try_whatsapp(report):
        return True

    # Fallback: watchdog alert channel (Slack/Discord webhook + email)
    _try_watchdog(report)
    return False


def _build_report(content: dict, pipeline_result: dict) -> str:
    """Compose the full founder report message."""
    today    = today_ist().strftime("%d %b %Y")
    day_num  = content.get("day_number", "?")
    source   = content.get("_source", "")
    recycled = content.get("_recycled", False)

    # ── Content counts ────────────────────────────────────────────────────────
    reels      = len(content.get("reels", []))
    has_car    = bool(content.get("carousel"))
    has_li     = bool(content.get("linkedin_post"))
    has_blog   = bool(content.get("blog_post"))
    has_story  = bool(content.get("story_sequence") or content.get("instagram_stories"))
    has_yt     = bool(content.get("yt_short"))

    content_lines = []
    if reels:       content_lines.append(f"  {reels} Reel{'s' if reels > 1 else ''}")
    if has_car:     content_lines.append("  1 Carousel")
    if has_li:      content_lines.append("  1 LinkedIn Post")
    if has_blog:    content_lines.append("  1 Blog Post")
    if has_story:   content_lines.append("  1 Story Sequence")
    if has_yt:      content_lines.append("  1 YouTube Short")

    # ── Objective + audience ──────────────────────────────────────────────────
    objective = _extract_objective(content)
    audience  = _extract_audience(content)

    # ── Trend + hook ──────────────────────────────────────────────────────────
    top_trend = _get_top_trend()
    top_hook  = _get_top_hook()

    # ── Pipeline KPIs ─────────────────────────────────────────────────────────
    pipeline_lines = _pipeline_summary()

    # ── Health ────────────────────────────────────────────────────────────────
    health_str = _get_health_status()

    # ── Assemble ──────────────────────────────────────────────────────────────
    lines = [
        f"PURITY BEANS | Day {day_num} | {today}",
        "",
    ]

    if recycled:
        lines += [f"NOTE: Fallback content used ({source})", ""]

    lines += ["Content Generated:"]
    lines += content_lines or ["  (none)"]
    lines += [
        "",
        f"Today's Objective: {objective}",
        f"Today's Audience:  {audience}",
        "",
    ]

    if top_trend:
        lines.append(f"Top Trend:  {top_trend}")
    if top_hook:
        lines.append(f"Top Hook:   {top_hook}")

    if pipeline_lines:
        lines += ["", "Pipeline:"] + pipeline_lines

    # ── Publishing results ────────────────────────────────────────────────────
    pub = pipeline_result.get("publish", {})
    if pub:
        published = pub.get("published_platforms", [])
        if published:
            lines += ["", f"Published: {', '.join(p.title() for p in published)}"]
            # Include post URLs
            url_map = {
                "linkedin":  pub.get("linkedin", {}).get("url", ""),
                "instagram": pub.get("instagram", {}).get("permalink", ""),
                "facebook":  pub.get("facebook", {}).get("url", ""),
                "youtube":   pub.get("youtube", {}).get("url", ""),
            }
            for platform, url in url_map.items():
                if url:
                    lines.append(f"  {platform.title()}: {url}")
        else:
            not_conf = [p for p, r in pub.items()
                        if isinstance(r, dict) and r.get("error") == "not_configured"]
            if not_conf:
                lines += ["", f"Social: Not configured ({', '.join(p.title() for p in not_conf)})"]

    lines += [
        "",
        f"Health: {health_str}",
        "",
        "Next run: Tomorrow 06:00 IST",
    ]

    # Nurture dispatch result
    if pipeline_result.get("dispatched", 0) > 0:
        lines += [f"Nurture: {pipeline_result['dispatched']} message(s) sent to stalling leads"]

    return "\n".join(lines)


# ── Data collectors ───────────────────────────────────────────────────────────

def _extract_objective(content: dict) -> str:
    try:
        obj = content.get("objective") or content.get("business_objective", {})
        if isinstance(obj, dict):
            return obj.get("primary", "Brand Awareness").replace("_", " ").title()
        return str(obj).replace("_", " ").title() if obj else "Brand Awareness"
    except Exception:
        return "Brand Awareness"


def _extract_audience(content: dict) -> str:
    try:
        for piece in [content.get("linkedin_post"), *(content.get("reels") or [])]:
            if isinstance(piece, dict) and piece.get("audience"):
                return str(piece["audience"]).replace("_", " ").title()
        return "General"
    except Exception:
        return "General"


def _get_top_trend() -> str:
    try:
        from content_generator.analytics.metrics_store import get_cached_trends
        trends = get_cached_trends(max_age_hours=48)
        if trends:
            t = trends[0]
            return t.get("trend") or t.get("keyword", "")
    except Exception as _e:
        logger.debug("[founder_report] optional step failed: %s", _e)
    return ""


def _get_top_hook() -> str:
    try:
        from content_generator.strategy.hook_optimizer import get_hook_performance_table
        table = get_hook_performance_table()
        if table:
            h = table[0]
            score = h.get("avg_viral_score", 0)
            return f"{h.get('hook','')} (avg viral {score:.0f})"
    except Exception as _e:
        logger.debug("[founder_report] optional step failed: %s", _e)
    return ""


def _pipeline_summary() -> list[str]:
    try:
        from content_generator.dashboard.metrics import _lead_metrics
        pm = _lead_metrics()
        lines = []
        if pm.get("hot_leads", 0) > 0:
            lines.append(f"  Hot Leads:     {pm['hot_leads']}")
        ev = pm.get("total_pipeline_ev", 0)
        if ev > 0:
            lines.append(f"  Pipeline EV:   Rs {ev:,.0f}")
        stalling = pm.get("stalling_leads", 0)
        if stalling > 0:
            lines.append(f"  Stalling:      {stalling} lead(s) need follow-up")
        return lines
    except Exception:
        return []


def _get_health_status() -> str:
    try:
        from content_generator.scheduler.health_monitor import get_health_report
        report = get_health_report()
        status = report.get("status", "unknown")
        if status == "healthy":
            return "All systems operational"
        elif status == "degraded":
            issues = [c["name"] for c in report.get("checks", []) if c.get("status") == "warn"]
            return f"Degraded — {', '.join(issues[:2])}"
        else:
            return f"CRITICAL — check logs"
    except Exception:
        return "Unknown"


# ── Send channels ─────────────────────────────────────────────────────────────

def _try_whatsapp(text: str) -> bool:
    """Attempt to send via WhatsApp Business API. Returns True on success."""
    try:
        from content_generator.nurture.whatsapp import send_message
        result = send_message(
            contact=_FOUNDER_PHONE,
            text=text,
            lead_id="founder",
            segment="founder",
            stage="report",
        )
        if result.get("success"):
            logger.info("[founder_report] Sent via WhatsApp to %s", _FOUNDER_PHONE)
            return True
        logger.debug("[founder_report] WhatsApp failed: %s", result.get("error"))
        return False
    except Exception as e:
        logger.debug("[founder_report] WhatsApp exception: %s", e)
        return False


def _try_watchdog(text: str) -> None:
    """Send via watchdog alert channel (webhook/email fallback)."""
    try:
        from content_generator.scheduler.watchdog import _alert
        _alert(f"FOUNDER REPORT\n{text}")
    except Exception as e:
        logger.debug("[founder_report] Watchdog fallback failed: %s", e)
