"""
THE reward function — the single definition of "success" for this engine.

The engine has a business hierarchy, not a flat engagement contest:

    revenue -> orders -> conversion intent -> audience growth -> engagement

Revenue and orders therefore receive deterministic hierarchy prefixes before
KPI-specific optimization. This prevents a large follower/view count from
outscoring a smaller but real commercial outcome.

Missing-data contract: absent or None metrics are UNKNOWN, never zero. Real
numeric zeroes remain measured zeroes.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "followers": {
        "revenue": 1.0, "orders": 25.0, "follows_gained": 40.0,
        "shares": 12.0, "profile_visits": 8.0, "website_clicks": 6.0,
        "saves": 4.0, "comments": 4.0, "avg_view_duration_s": 0.8,
        "reach": 0.02, "likes": 0.5, "views": 0.01,
    },
    "engagement": {
        "revenue": 1.0, "orders": 25.0, "comments": 20.0, "shares": 15.0,
        "saves": 12.0, "follows_gained": 10.0, "profile_visits": 4.0,
        "website_clicks": 4.0, "avg_view_duration_s": 1.0,
        "reach": 0.02, "likes": 1.0, "views": 0.01,
    },
    "revenue": {
        "revenue": 2.0, "orders": 50.0, "website_clicks": 8.0,
        "profile_visits": 5.0, "follows_gained": 5.0, "shares": 4.0,
        "saves": 4.0, "comments": 3.0, "avg_view_duration_s": 0.5,
        "reach": 0.01, "likes": 0.5, "views": 0.01,
    },
}

# Lexicographic business hierarchy encoded as score prefixes.
#
# ORDERS get the prefix; ATTRIBUTED REVENUE does not. They are different kinds
# of evidence and the repo's own tests encode the distinction:
#
#   test_learning_evidence_guard  1 order must outrank 10,000 follows,
#       and Rs 1 of attributed revenue must not
#   test_reward_objective_integrity  100 follows must outrank Rs 1 of revenue
#
# Both hold once you notice what each number means. An order is a discrete,
# completed conversion — a real person bought coffee, and that outranks any
# amount of engagement. Attributed revenue is not discrete: attribution is
# day-level and splits a day's takings across that day's posts, so a post can
# be credited Rs 0.33. Letting a fractional accounting artefact outrank a
# genuine audience gain is what GOAL_HIERARCHY.md blocks by name — "selling
# harder at 105 followers would raise short-term revenue but kill reach ->
# blocked (L2 growth staging > naive L1)".
#
# Revenue keeps its per-profile weight, so it always contributes and a
# revenue-KPI run still ranks it highest. It simply does not get to dominate
# the followers stage on a rounding artefact.
#
# Previously both were prefixes, and REVENUE_HIERARCHY = 1_000_000 made Rs 1
# beat 10,000 followers 2.5x. Both tests above failed; neither was wired into CI.
REVENUE_HIERARCHY = 0.0
ORDER_HIERARCHY = 1_000_000.0

DEFAULT_KPI = "followers"


def get_active_kpi() -> str:
    try:
        from content_generator.core.founder_policy import policy
        kpi = str(policy().get("target_kpi") or DEFAULT_KPI).lower()
        return kpi if kpi in WEIGHT_PROFILES else DEFAULT_KPI
    except Exception as e:
        logger.debug("[reward] policy KPI unavailable (%s) — default", e)
        return DEFAULT_KPI


def get_weights(kpi: str | None = None) -> dict[str, float]:
    return WEIGHT_PROFILES.get(kpi or get_active_kpi(), WEIGHT_PROFILES[DEFAULT_KPI])


def observed_metrics(metrics: dict, kpi: str | None = None) -> dict[str, float]:
    """Return only metrics actually observed; None/missing means UNKNOWN."""
    m = metrics or {}
    return {
        key: float(m[key])
        for key in get_weights(kpi)
        if key in m and m[key] is not None
    }


def coverage(metrics: dict, kpi: str | None = None) -> float:
    weights = get_weights(kpi)
    if not weights:
        return 0.0
    return len(observed_metrics(metrics, kpi)) / len(weights)


def _commercial_prefix(observed: dict[str, float]) -> float:
    revenue = max(0.0, observed.get("revenue", 0.0))
    orders = max(0.0, observed.get("orders", 0.0))
    return revenue * REVENUE_HIERARCHY + orders * ORDER_HIERARCHY


def score(metrics: dict, kpi: str | None = None) -> float:
    """Return the KPI reward with deterministic commercial hierarchy."""
    observed = observed_metrics(metrics, kpi)
    w = get_weights(kpi)
    base = sum(observed[key] * w[key] for key in observed)
    return float(_commercial_prefix(observed) + base)


def explain(metrics: dict, kpi: str | None = None) -> dict:
    """Score plus auditable commercial hierarchy and per-signal contributions."""
    kpi = kpi or get_active_kpi()
    w = get_weights(kpi)
    observed = observed_metrics(metrics, kpi)
    base_parts = {k: round(observed[k] * w[k], 2) for k in observed}
    commercial = _commercial_prefix(observed)
    total = score(metrics, kpi)
    parts = dict(base_parts)
    if observed.get("revenue", 0) > 0:
        parts["revenue_hierarchy"] = round(observed["revenue"] * REVENUE_HIERARCHY, 2)
    if observed.get("orders", 0) > 0:
        parts["orders_hierarchy"] = round(observed["orders"] * ORDER_HIERARCHY, 2)
    top = sorted(parts.items(), key=lambda x: x[1], reverse=True)[:3]
    missing = [k for k in w if k not in observed]
    return {
        "kpi": kpi,
        "score": total,
        "coverage": coverage(metrics, kpi),
        "observed_metrics": sorted(observed),
        "missing_metrics": missing,
        "commercial_hierarchy": {
            "revenue_prefix": round(max(0.0, observed.get("revenue", 0.0)) * REVENUE_HIERARCHY, 2),
            "orders_prefix": round(max(0.0, observed.get("orders", 0.0)) * ORDER_HIERARCHY, 2),
        },
        "contributions": parts,
        "top_drivers": [k for k, _ in top],
    }


# Spec KPIs the Instagram Graph API does not expose per post, and the honest
# reason why. Documented here so nobody "adds" them later with invented numbers.
# Removed in a refactor, which broke the import in test_growth_director_spec.
#
#   returning_viewers / repeat_engagement — Instagram exposes no per-viewer
#     identity on media insights. There is no supported way to tell a repeat
#     viewer from a new one. The closest real proxies are account-level
#     `accounts_engaged` over time and repeat commenters; neither is per-post.
#
#   website_ctr — link clicks are reported at ACCOUNT level, not per post, so
#     per-post CTR needs per-post landing URLs (a link-in-bio router).
UNAVAILABLE_KPIS = {
    "returning_viewers": "no per-viewer identity in the Graph API",
    "repeat_engagement": "no per-viewer identity in the Graph API",
    "website_ctr_per_post": "link clicks are account-level, not per-media",
}
