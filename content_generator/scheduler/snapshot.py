"""
Daily snapshot — archives every run's outputs for future learning.

After each successful pipeline run, this module:
  1. Creates output/archive/YYYY-MM-DD/
  2. Writes content.json, analytics.json, strategy.json, trends.json
  3. Keeps the last 90 days (older archives auto-pruned)

Why this matters:
  - Content regeneration uses historical snapshots to avoid repeating ideas
  - Trend data accumulates -> better seasonal pattern detection
  - Analytics snapshots let you debug "why did day 42 underperform?"
  - Future ML models can train on the full historical record

Usage:
    from content_generator.scheduler.snapshot import save_daily_snapshot

    save_daily_snapshot(content=content, day_number=42)
"""
from __future__ import annotations
import datetime
import json
import logging
import os
import shutil

from content_generator.core.ist_dates import today_ist

logger = logging.getLogger(__name__)

_ARCHIVE_ROOT = os.path.join("output", "archive")
_KEEP_DAYS    = int(os.getenv("SNAPSHOT_KEEP_DAYS", "90"))


def save_daily_snapshot(content: dict, day_number: int = 0) -> str:
    """
    Save a complete daily snapshot to output/archive/YYYY-MM-DD/.

    Returns the archive directory path.
    """
    today    = today_ist().isoformat()
    arch_dir = os.path.join(_ARCHIVE_ROOT, today)
    os.makedirs(arch_dir, exist_ok=True)

    # 1. Content snapshot
    _write_json(arch_dir, "content.json", content)

    # 2. Analytics snapshot (current DB metrics)
    analytics = _collect_analytics()
    _write_json(arch_dir, "analytics.json", analytics)

    # 3. Strategy snapshot (today's mix + hook rankings)
    strategy = _collect_strategy()
    _write_json(arch_dir, "strategy.json", strategy)

    # 4. Trends snapshot
    trends = _collect_trends()
    _write_json(arch_dir, "trends.json", trends)

    # 5. Metadata
    meta = {
        "date":       today,
        "day_number": day_number,
        "archived_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "files":      ["content.json", "analytics.json", "strategy.json", "trends.json"],
    }
    # 5b. Human-readable report
    _write_report(arch_dir, today, day_number, content, analytics, strategy, trends)

    _write_json(arch_dir, "meta.json", meta)

    logger.info("[snapshot] Archived day %d -> %s", day_number, arch_dir)

    # 6. Prune old archives
    _prune_old_archives()

    return arch_dir


def load_snapshot(date_str: str = None) -> dict:
    """
    Load a snapshot for a given date (default: today).
    Returns {} if no snapshot exists for that date.
    """
    date_str = date_str or today_ist().isoformat()
    arch_dir = os.path.join(_ARCHIVE_ROOT, date_str)

    if not os.path.isdir(arch_dir):
        return {}

    result = {"date": date_str}
    for fname in ("content.json", "analytics.json", "strategy.json", "trends.json", "meta.json"):
        path = os.path.join(arch_dir, fname)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    result[fname.replace(".json", "")] = json.load(f)
            except Exception as _e:
                logger.debug("[snapshot] optional step failed: %s", _e)
    return result


def load_yesterday_snapshot() -> dict:
    """Load yesterday's snapshot — used by the emergency fallback."""
    yesterday = (today_ist() - datetime.timedelta(days=1)).isoformat()
    snap      = load_snapshot(yesterday)
    if snap:
        logger.info("[snapshot] Loaded yesterday's snapshot (%s)", yesterday)
    else:
        logger.warning("[snapshot] No snapshot found for %s", yesterday)
    return snap


def list_snapshots(limit: int = 30) -> list[str]:
    """Return sorted list of snapshot dates (newest first)."""
    if not os.path.isdir(_ARCHIVE_ROOT):
        return []
    dates = sorted(
        [d for d in os.listdir(_ARCHIVE_ROOT) if os.path.isdir(os.path.join(_ARCHIVE_ROOT, d))],
        reverse=True,
    )
    return dates[:limit]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _write_report(
    directory: str, date_str: str, day_number: int,
    content: dict, analytics: dict, strategy: dict, trends: dict,
) -> None:
    """Write a human-readable report.txt for this day's archive."""
    path = os.path.join(directory, "report.txt")
    try:
        lines = [
            f"PURITY BEANS DAILY REPORT",
            f"Date: {date_str}  |  Day: {day_number}",
            f"Generated: {datetime.datetime.now().strftime('%H:%M:%S')}",
            "=" * 50,
            "",
            "CONTENT GENERATED",
        ]

        reels = content.get("reels", [])
        if reels:
            lines.append(f"  Reels:          {len(reels)}")
        if content.get("carousel"):
            lines.append("  Carousel:       1")
        if content.get("linkedin_post"):
            lines.append("  LinkedIn Post:  1")
        if content.get("blog_post"):
            lines.append("  Blog Post:      1")
        if content.get("story_sequence") or content.get("instagram_stories"):
            lines.append("  Story Sequence: 1")
        if content.get("yt_short"):
            lines.append("  YouTube Short:  1")
        if content.get("_recycled"):
            lines.append(f"  NOTE: Fallback content ({content.get('_source', 'unknown')})")

        # Strategy
        mix = strategy.get("todays_mix", {})
        if mix:
            lines += [
                "",
                "STRATEGY",
                f"  Top priority: {mix.get('top_priority', 'unknown').replace('_', ' ').title()}",
                f"  Data-driven:  {mix.get('data_driven', False)}",
            ]

        # Revenue
        rev = analytics.get("revenue", {})
        if rev.get("total_revenue", 0) > 0:
            lines += [
                "",
                "REVENUE (last 7 days)",
                f"  Total:  Rs {rev.get('total_revenue', 0):,.0f}",
                f"  Orders: {rev.get('total_orders', 0)}",
                f"  ROAS:   {rev.get('roas', 0):.1f}x",
            ]

        # Pipeline
        pipeline = analytics.get("pipeline", {})
        if pipeline.get("total_leads", 0) > 0:
            lines += [
                "",
                "PIPELINE",
                f"  Total leads:   {pipeline.get('total_leads', 0)}",
                f"  Hot leads:     {pipeline.get('hot_leads', 0)}",
                f"  Pipeline EV:   Rs {pipeline.get('total_pipeline_ev', 0):,.0f}",
            ]

        # Top trend
        top_trends = trends.get("trends", [])
        if top_trends:
            t = top_trends[0]
            trend_kw = t.get("trend") or t.get("keyword", "")
            if trend_kw:
                lines += ["", f"TOP TREND: {trend_kw}"]

        # Hooks
        hooks = analytics.get("hooks", {}).get("ranked", [])
        if hooks:
            lines += ["", f"TOP HOOK: {hooks[0].get('hook', '')}"]

        # Health
        health = analytics.get("system_health", {})
        lines += ["", f"HEALTH: {health.get('status', 'unknown').upper()}"]

        lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        logger.debug("[snapshot] report.txt write failed: %s", e)


def _write_json(directory: str, filename: str, data: dict) -> None:
    path = os.path.join(directory, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("[snapshot] Could not write %s: %s", path, e)


def _collect_analytics() -> dict:
    try:
        from content_generator.dashboard.metrics import get_all_metrics
        return get_all_metrics(days=7)
    except Exception as e:
        logger.debug("[snapshot] analytics collection failed: %s", e)
        return {}


def _collect_strategy() -> dict:
    try:
        from content_generator.strategy.content_mix_optimizer import get_todays_mix
        from content_generator.strategy.hook_optimizer import get_hook_performance_table
        return {
            "todays_mix":   get_todays_mix(),
            "hook_ranking": get_hook_performance_table()[:10],
        }
    except Exception as e:
        logger.debug("[snapshot] strategy collection failed: %s", e)
        return {}


def _collect_trends() -> dict:
    try:
        from content_generator.analytics.metrics_store import get_cached_trends
        return {"trends": get_cached_trends(max_age_hours=48)}
    except Exception as e:
        logger.debug("[snapshot] trends collection failed: %s", e)
        return {}


def _prune_old_archives() -> None:
    """Delete archives older than SNAPSHOT_KEEP_DAYS."""
    if not os.path.isdir(_ARCHIVE_ROOT):
        return
    cutoff = today_ist() - datetime.timedelta(days=_KEEP_DAYS)
    try:
        for name in os.listdir(_ARCHIVE_ROOT):
            try:
                arc_date = datetime.date.fromisoformat(name)
            except ValueError:
                continue
            if arc_date < cutoff:
                shutil.rmtree(os.path.join(_ARCHIVE_ROOT, name), ignore_errors=True)
                logger.info("[snapshot] Pruned old archive: %s", name)
    except Exception as e:
        logger.debug("[snapshot] prune failed: %s", e)
