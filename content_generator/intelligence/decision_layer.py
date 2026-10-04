"""
Decision Layer — turns content generation into a DECISION with reasoning.

Composes existing intelligence (does not rebuild it — ADR-001, architecture
frozen). It answers, for today:
  - recommendation: expected EVPOI, confidence, and WHY (from growth stage +
    viral memory + revenue signal)
  - experiment: the active hypothesis + which variant this run tests
  - campaign: the active campaign context
  - playbook (Content DNA): the recurring structure of top performers, once
    enough history exists

This is the glue behind:
    get_todays_content(include_recommendations=True)

Every function degrades gracefully — thin data returns honest low-confidence
output, never fabricated precision (Honesty Rule, POLICY_ENGINE.md).
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

_MIN_DNA_SAMPLES = 12   # match optimizer — do not trust patterns before this

# Rotating experiment hypotheses. Each published day tests one; results accrue
# in Company Memory (learning log) and surface in the weekly brief.
_EXPERIMENT_BANK = [
    ("Founder-face reels outperform product-only reels", "founder_vs_product"),
    ("Reverse-qualifier hooks beat direct hooks on follows", "hook_style"),
    ("Value-unlock reels drive more comments than opinion bait", "comment_mechanic"),
    ("Shorter hooks (<7 words) improve completion rate", "hook_length"),
    ("Education carousels get more saves than myth-busting", "carousel_angle"),
    ("Talking-head beats cinematic B-roll for retention", "format"),
]

# Active campaigns (edit as real campaigns run). Deterministic by day so a
# campaign spans a block of days rather than flickering.
_CAMPAIGNS = [
    "Always-On Growth",
    "Corporate Pantry Push",
    "Festival Gifting",
    "Chicory Awareness",
]


def extract_content_dna() -> dict:
    """
    The Content DNA / Playbook: the recurring structure of top-performing posts.
    Returns {"available": bool, "playbook": str, "pattern": {...}, "samples": n}.
    Only meaningful once >= _MIN_DNA_SAMPLES posts have metrics.
    """
    try:
        from content_generator.core.learning_engine import analyze
        result = analyze()
    except Exception:
        return {"available": False, "playbook": "Baseline_v1", "samples": 0}

    if result["count"] < _MIN_DNA_SAMPLES:
        return {"available": False, "playbook": "Baseline_v1", "samples": result["count"]}

    winners = result["winners"]

    def _mode(key: str) -> str | None:
        vals = [str(w.get(key, "")).strip() for w in winners if w.get(key)]
        return max(set(vals), key=vals.count) if vals else None

    pattern = {
        "top_format": _mode("format"),
        "top_topic":  _mode("topic"),
        "track":      _mode("track"),
    }
    # Version the playbook by the winning pattern so it bumps as DNA shifts
    sig = hashlib.md5(str(pattern).encode()).hexdigest()[:4]
    return {
        "available": True,
        "playbook":  f"Playbook_{pattern.get('track') or 'mixed'}_{sig}",
        "pattern":   pattern,
        "samples":   result["count"],
    }


def build_recommendation(day: int) -> dict:
    """Expected EVPOI, confidence, and a plain-English reason for today's plan."""
    # Growth stage + funnel objectives (always available)
    reason_bits = []
    stage = {}
    try:
        from content_generator.core.growth_director import get_growth_stage, get_todays_objectives
        stage = get_growth_stage()
        objs  = get_todays_objectives(day)
        reason_bits.append(
            f"Stage {stage['name']} ({stage['viral_pct']}% viral); "
            f"today's reel objective is {objs['brand_reel'][0]}"
        )
    except Exception as _e:
        logger.debug("[decision_layer] optional step failed: %s", _e)

    # Expected EVPOI from the 7-day trend (honest: 0 until revenue data exists)
    expected_evpoi = 0.0
    try:
        from content_generator.analytics.founder_brief import compute_evpoi
        ev = compute_evpoi()
        expected_evpoi = ev.get("evpoi_per_1k", 0.0)
    except Exception as _e:
        logger.debug("[decision_layer] optional step failed: %s", _e)

    # Confidence scales with how much performance history we have
    samples = 0
    try:
        from content_generator.core.learning_engine import analyze
        samples = analyze().get("count", 0)
    except Exception as _e:
        logger.debug("[decision_layer] optional step failed: %s", _e)
    confidence = round(min(0.9, 0.3 + samples * 0.03), 2)   # 0.30 cold -> 0.90 at 20+

    # Reason enriched by Content DNA + viral memory
    dna = extract_content_dna()
    if dna["available"] and dna.get("pattern", {}).get("top_format"):
        reason_bits.append(
            f"top performers favour '{dna['pattern']['top_format']}' format "
            f"({dna['samples']} posts learned)"
        )
    else:
        reason_bits.append(f"still gathering data ({samples} posts measured) — exploring")

    return {
        "expected_evpoi": expected_evpoi,
        "confidence":     confidence,
        "reason":         "; ".join(reason_bits) + ".",
        "stage":          stage.get("name", ""),
    }


def current_experiment(day: int) -> dict:
    """The hypothesis this run tests, and which variant (A/B alternate by day)."""
    hyp, key = _EXPERIMENT_BANK[day % len(_EXPERIMENT_BANK)]
    variant  = "A" if (day // len(_EXPERIMENT_BANK)) % 2 == 0 else "B"
    return {"hypothesis": hyp, "key": key, "variant": variant}


def current_campaign(day: int) -> str:
    return _CAMPAIGNS[(day // 7) % len(_CAMPAIGNS)]   # one campaign per week block


def plan_today(day: int) -> dict:
    """The full decision bundle attached to today's content."""
    campaign = current_campaign(day)
    policies = {}
    policy_version = "1.0"
    try:
        from content_generator.core.founder_policy import policy
        p = policy()
        policy_version = p.version
        policies = {"target_kpi": p.get("target_kpi"),
                    "priority_segments": p.get("priority_segments"),
                    "auto_publish": p.get("auto_publish")}
        override = p.get("active_campaign_override", "")
        if override:
            campaign = override   # founder override wins
    except Exception as _e:
        logger.debug("[decision_layer] optional step failed: %s", _e)
    return {
        "recommendation": build_recommendation(day),
        "experiment":     current_experiment(day),
        "campaign":       campaign,
        "playbook":       extract_content_dna()["playbook"],
        "policies":       policies,
        "policy_version": policy_version,
    }


# ── Phase 1: per-asset metadata (first Company Memory record) ─────────────────

def _versions() -> dict:
    """Version stamps so any asset can be traced to the code that made it."""
    try:
        from content_generator.core.versions import all_versions
        return all_versions()
    except Exception as _e:
        logger.debug("[decision_layer] version stamps unavailable: %s", _e)
        return {}


def _content_id(day: int, channel: str, ctype: str) -> str:
    raw = f"{today_ist().isoformat()}|{day}|{channel}|{ctype}"
    return "pb_" + hashlib.md5(raw.encode()).hexdigest()[:10]


def _scroller_dimensions(piece: dict, content: dict = None,
                        platform: str = None, fmt: str = None) -> dict:
    """
    Attention-side dimensions for one asset. Never raises — metadata enrichment
    must not be able to fail a generation run.
    """
    try:
        from content_generator.core.scroller_psychology import describe
        return describe(piece, content, platform, fmt)
    except Exception as e:
        logger.debug("[decision] scroller dimensions unavailable: %s", e)
        return {}


def attach_asset_metadata(content: dict, day: int) -> list[dict]:
    """
    Build a metadata record for each publishable asset (Phase 1 of the plan).
    Returns the list and also stores it under content['_asset_metadata'].
    """
    plan = plan_today(day)
    now  = datetime.datetime.now().isoformat(timespec="seconds")

    specs = [
        ("instagram", "reel",           (content.get("reels") or [{}])[0]),
        ("instagram", "growth_reel",    content.get("growth_reel") or {}),
        ("instagram", "carousel",       content.get("carousel") or {}),
        ("instagram", "story",          content.get("stories") or {}),
        ("linkedin",  "post",           content.get("linkedin_post") or {}),
        ("youtube",   "short",          content.get("yt_short") or {}),
    ]
    records = []
    for channel, ctype, piece in specs:
        if not isinstance(piece, dict) or not piece:
            continue
        records.append({
            "content_id":   _content_id(day, channel, ctype),
            "day":          day,
            "channel":      channel,
            "type":         ctype,
            "topic":        str(piece.get("topic") or piece.get("viral_idea") or piece.get("title") or "")[:120],
            "hook":         str(piece.get("hook_text") or piece.get("chosen_hook") or piece.get("hook") or "")[:160],
            "cta":          str(piece.get("cta") or "")[:160],
            "audience":     plan["recommendation"].get("stage", ""),
            "campaign":     plan["campaign"],
            "experiment":   plan["experiment"]["key"],
            "variant":      plan["experiment"]["variant"],
            "playbook":     plan["playbook"],
            "policy_version": plan.get("policy_version", "1.0"),
            "generation_id": str(content.get("generation_id", "")),
            # Scroller decision dimensions (ADR-002 Phase 1). Recorded on every
            # asset so mechanism-level learning is possible later; today they
            # are classified from the copy, not selected before it.
            **_scroller_dimensions(piece, content, channel, ctype),
            **_versions(),
            "publish_time": now,
            "status":       "scheduled",
        })
    content["_asset_metadata"] = records
    logger.info("[decision] Attached metadata to %d assets (campaign=%s, exp=%s/%s)",
                len(records), plan["campaign"], plan["experiment"]["key"], plan["experiment"]["variant"])
    return records
