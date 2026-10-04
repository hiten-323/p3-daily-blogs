"""
Weekly Founder Brief — exactly three numbers, nothing else.

1. EVPOI v1     — Instagram-attributed revenue ÷ organic impressions (per 1000)
2. Brand Equity — weighted score (repeat purchases auto; other components from
                  a manual inputs file until data sources exist)
3. Learning Velocity — what the system validated and retired this week

Everything else is deliberately excluded. If a metric doesn't answer
"are we creating value per impression / is the brand healthy / are we getting
smarter", it doesn't belong here.

Runs Mondays inside the daily pipeline; writes output/reports/founder_brief_<date>.md
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_REPORTS_DIR  = os.getenv("REPORTS_DIR",  os.path.join("output", "reports"))
_EQUITY_INPUTS = os.path.join(_LEARNING_DIR, "brand_equity_inputs.json")


# ── Metric 1: EVPOI v1 ────────────────────────────────────────────────────────

def compute_evpoi(days: int = 7) -> dict:
    """IG-attributed revenue per 1000 organic impressions (reach as proxy)."""
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()

    ig_revenue = 0.0
    rev_path = os.path.join(_LEARNING_DIR, "revenue_log.json")
    if os.path.exists(rev_path):
        try:
            with open(rev_path, "r", encoding="utf-8") as f:
                ig_revenue = sum(
                    e.get("ig_revenue", 0) for e in json.load(f)
                    if e.get("date", "") >= cutoff
                )
        except Exception as _e:
            logger.debug("[founder_brief] optional step failed: %s", _e)

    impressions = 0
    perf_path = os.path.join(_LEARNING_DIR, "performance_log.json")
    if os.path.exists(perf_path):
        try:
            with open(perf_path, "r", encoding="utf-8") as f:
                for e in json.load(f):
                    if str(e.get("posted_at", ""))[:10] >= cutoff:
                        m = e.get("metrics", {})
                        impressions += m.get("views", 0) or m.get("reach", 0)
        except Exception as _e:
            logger.debug("[founder_brief] optional step failed: %s", _e)

    evpoi = (ig_revenue / impressions * 1000) if impressions else 0.0
    return {"ig_revenue": round(ig_revenue, 2), "impressions": impressions,
            "evpoi_per_1k": round(evpoi, 2)}


# ── Metric 2: Brand Equity Score ──────────────────────────────────────────────
#
# Brand Equity = repeat_purchase_rate*0.3 + branded_search_index*0.2
#              + ugc_creation_rate*0.2 + review_sentiment*0.3
# Each component scored 0-10. Repeat rate computes automatically from revenue
# snapshots; the other three come from output/learning/brand_equity_inputs.json
# (manual weekly entry until data sources exist):
#   {"branded_search_index": 0-10, "ugc_creation_rate": 0-10, "review_sentiment": 0-10}

def compute_brand_equity(days: int = 30) -> dict:
    # Repeat purchase rate (auto, from revenue snapshots)
    repeat_score = 0.0
    rev_path = os.path.join(_LEARNING_DIR, "revenue_log.json")
    if os.path.exists(rev_path):
        try:
            with open(rev_path, "r", encoding="utf-8") as f:
                entries = json.load(f)[-days:]
            orders    = sum(e.get("orders", 0) for e in entries)
            returning = sum(e.get("returning_customers", 0) for e in entries)
            if orders:
                # 25% repeat rate = 10/10 (SCALE-stage target in SUCCESS_METRICS)
                repeat_score = min(10.0, (returning / orders) / 0.25 * 10)
        except Exception as _e:
            logger.debug("[founder_brief] optional step failed: %s", _e)

    manual = {}
    if os.path.exists(_EQUITY_INPUTS):
        try:
            with open(_EQUITY_INPUTS, "r", encoding="utf-8") as f:
                manual = json.load(f)
        except Exception as _e:
            logger.debug("[founder_brief] optional step failed: %s", _e)

    components = {
        "repeat_purchase_rate": round(repeat_score, 1),
        "branded_search_index": float(manual.get("branded_search_index", 0)),
        "ugc_creation_rate":    float(manual.get("ugc_creation_rate", 0)),
        "review_sentiment":     float(manual.get("review_sentiment", 0)),
    }
    score = (components["repeat_purchase_rate"] * 0.3
             + components["branded_search_index"] * 0.2
             + components["ugc_creation_rate"]    * 0.2
             + components["review_sentiment"]     * 0.3)
    return {"score": round(score, 1), "components": components,
            "manual_inputs_present": bool(manual)}


# ── Metric 3: Learning Velocity ───────────────────────────────────────────────

def compute_learning_velocity(days: int = 7) -> dict:
    """What did the system validate / retire this week?"""
    cutoff = (today_ist() - datetime.timedelta(days=days)).isoformat()
    validated, retired = [], []
    try:
        from content_generator.core.learning_engine import analyze, _load_log
        recent_ids = {
            e.get("asset_id") for e in _load_log()
            if str(e.get("recorded_at", ""))[:10] >= cutoff
        }
        result = analyze()
        for e in result["winners"]:
            if e.get("asset_id") in recent_ids and e.get("hook"):
                validated.append(e["hook"][:80])
        for e in result["failed"]:
            if e.get("asset_id") in recent_ids and e.get("hook"):
                retired.append(e["hook"][:80])
    except Exception as ex:
        logger.debug("[brief] learning velocity unavailable: %s", ex)
    return {"validated": validated[:3], "retired": retired[:3],
            "posts_measured_this_week": len(validated) + len(retired)}


# ── The brief ─────────────────────────────────────────────────────────────────

def generate_founder_brief() -> str:
    """Write the weekly brief; returns the file path."""
    today  = today_ist()
    evpoi  = compute_evpoi()
    equity = compute_brand_equity()
    learn  = compute_learning_velocity()

    equity_note = "" if equity["manual_inputs_present"] else (
        "\n> Components marked 0 need weekly manual input in "
        "`output/learning/brand_equity_inputs.json` "
        '(`{"branded_search_index": n, "ugc_creation_rate": n, "review_sentiment": n}`, each 0-10).'
    )

    validated = "\n".join(f"- Validated: \"{h}\"" for h in learn["validated"]) or "- Nothing validated yet"
    retired   = "\n".join(f"- Retired: \"{h}\""   for h in learn["retired"])   or "- Nothing retired yet"

    body = f"""# Weekly Founder Brief — {today.isoformat()}

## 1. EVPOI (Enterprise Value Per Organic Impression)
**₹{evpoi['evpoi_per_1k']} per 1,000 impressions**
(₹{evpoi['ig_revenue']} IG-attributed revenue / {evpoi['impressions']:,} impressions, last 7 days)

## 2. Brand Equity Score
**{equity['score']} / 10**
- Repeat purchase rate: {equity['components']['repeat_purchase_rate']}/10 (auto)
- Branded search index: {equity['components']['branded_search_index']}/10
- UGC creation rate: {equity['components']['ugc_creation_rate']}/10
- Review sentiment: {equity['components']['review_sentiment']}/10{equity_note}

## 3. Learning Velocity ({learn['posts_measured_this_week']} posts measured this week)
{validated}
{retired}

---
*Three questions this brief answers: Are we creating value per impression?
Is the brand healthy? Are we getting smarter? Nothing else belongs here.*
"""
    os.makedirs(_REPORTS_DIR, exist_ok=True)
    path = os.path.join(_REPORTS_DIR, f"founder_brief_{today.isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    logger.info("[brief] Weekly founder brief -> %s", path)
    return path
