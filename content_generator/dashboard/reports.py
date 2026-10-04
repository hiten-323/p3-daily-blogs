"""
Report generator — formats dashboard metrics into human-readable reports.

Outputs:
  • Plain-text console report (always available)
  • JSON report (always available)
  • HTML report (if jinja2 installed)

Usage:
    from content_generator.dashboard.reports import print_report, save_report
    print_report(days=7)
    save_report(days=7, output_path="output/report_2026-W23.json")
"""
from content_generator.core.ist_dates import today_ist
import json
import logging
import os
import datetime

logger = logging.getLogger(__name__)


def get_report(days: int = 7) -> dict:
    """Return the full metrics report as a dict."""
    from content_generator.dashboard.metrics import get_all_metrics
    return get_all_metrics(days=days)


def print_report(days: int = 7) -> None:
    """Print a formatted KPI report to stdout."""
    report = get_report(days=days)
    _print_text_report(report)


def save_report(days: int = 7, output_path: str = None) -> str:
    """Save JSON report to file. Returns file path."""
    report  = get_report(days=days)
    if output_path is None:
        date_str     = today_ist().isoformat()
        os.makedirs("output", exist_ok=True)
        output_path  = os.path.join("output", f"report_{date_str}_days{days}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    logger.info("[reports] Saved → %s", output_path)
    return output_path


def _print_text_report(report: dict) -> None:
    """Format and print the report to console."""
    SEP   = "=" * 60
    SEP2  = "-" * 60
    BOLD  = "\033[1m"
    END   = "\033[0m"
    GREEN = "\033[32m"
    AMBER = "\033[33m"

    def _h(title):
        print(f"\n{SEP2}\n  {BOLD}{title}{END}\n{SEP2}")

    def _row(label, value, colour=""):
        print(f"  {label:<35} {colour}{value}{END}")

    print(f"\n{SEP}")
    print(f"  {BOLD}PURITY BEANS — CONTENT ENGINE KPI REPORT{END}")
    print(f"  {report.get('period', '')}")
    print(f"{SEP}")

    # Content
    _h("CONTENT PERFORMANCE")
    c = report.get("content", {})
    _row("Pieces tracked",       c.get("pieces", 0))
    _row("Avg viral score",      f"{c.get('avg_viral_score', 0):.1f} / 100")
    for p in c.get("top_pieces", []):
        _row(
            f"  {p['content_id']}",
            f"score={p['viral_score']:.0f}  views={p.get('views',0):,}  hook={p.get('hook','')}",
        )

    # Revenue
    _h("REVENUE & ROAS")
    r = report.get("revenue", {})
    _row("Total revenue",        f"Rs {r.get('total_revenue', 0):,.0f}")
    _row("Total orders",         r.get("total_orders", 0))
    _row("ROAS",                 f"{r.get('roas', 0):.1f}x")
    _row("Avg order value",      f"Rs {r.get('avg_order_value', 0):,.0f}")
    wow = r.get("week_over_week", {})
    if wow:
        trend_arrow = "UP" if wow.get("trend") == "up" else ("DOWN" if wow.get("trend") == "down" else "FLAT")
        colour = GREEN if wow.get("trend") == "up" else AMBER
        _row("Week-over-week",   f"{wow.get('change_pct', 0):+.1f}%  ({trend_arrow})", colour)

    # Funnel
    _h("CONVERSION FUNNEL")
    f = report.get("funnel", {})
    if f:
        _row("Total visits",     f.get("total_visits", 0))
        _row("Add-to-cart",      f.get("total_carts", 0))
        _row("Purchases",        f.get("total_purchases", 0))
        _row("Visit → Purchase", f"{f.get('overall_cvr_pct', 0):.2f}%")
        _row("Revenue per visit", f"Rs {f.get('revenue_per_visit', 0):.2f}")

    # Top hooks
    _h("TOP PERFORMING HOOKS")
    for h in report.get("hooks", {}).get("ranked", [])[:5]:
        _row(
            f"  {h['hook']:<25}",
            f"viral={h.get('avg_viral_score',0):.0f}  views={h.get('avg_views',0):,}  rev=Rs{h.get('total_revenue',0):,.0f}",
        )

    # Audience
    _h("AUDIENCE BREAKDOWN")
    for a in report.get("audience", {}).get("revenue_breakdown", []):
        _row(
            f"  {a.get('audience','?'):<15}",
            f"Rs {a.get('total_revenue',0):,.0f}  orders={a.get('total_orders',0)}",
        )

    # System health
    _h("SYSTEM HEALTH")
    health = report.get("system_health", {})
    _row("Status",              health.get("status", "unknown"))
    _row("Memory engine",       report.get("memory", {}).get("similarity_engine", "?"))
    _row("Pieces in memory",    report.get("memory", {}).get("total_stored", 0))

    print(f"\n{SEP}\n")
