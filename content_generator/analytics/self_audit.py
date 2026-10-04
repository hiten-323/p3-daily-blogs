"""
Engine Self-Audit — an operational assurance layer, not business logic.

Runs automatically at the end of every pipeline execution and prints a single
health block. Its job is to make REGRESSIONS immediately visible after any
future change, so a silent breakage is caught on the next run instead of weeks
later.

Never raises: an audit must never be able to break the run it is auditing.
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import logging

logger = logging.getLogger(__name__)


def _check(name: str, fn) -> tuple[str, bool, str]:
    try:
        ok, detail = fn()
        return name, bool(ok), str(detail)
    except Exception as e:
        logger.debug("[self_audit] check %s errored: %s", name, e)
        return name, False, f"check errored: {e}"


def run_self_audit(content: dict | None = None, publish_result: dict | None = None) -> dict:
    """Return {checks, score, healthy} and log a compact health block."""
    content = content or {}
    publish_result = publish_result or {}
    checks: list[tuple[str, bool, str]] = []

    def _gen():
        n = sum(1 for k in ("carousel", "instagram_post", "linkedin_post", "blog_post",
                            "yt_short", "stories", "growth_reel")
                if isinstance(content.get(k), dict) and content.get(k))
        n += sum(1 for r in (content.get("reels") or []) if isinstance(r, dict) and r)
        return n >= 2, f"{n} assets"
    checks.append(_check("Generation", _gen))

    def _editorial():
        from content_generator.core.editorial_engine import get_valid_assets, get_current_pass_score
        valid = get_valid_assets(content) if content else []
        return (len(valid) >= 1 if content else True,
                f"{len(valid)} valid @ threshold {get_current_pass_score()}")
    checks.append(_check("Editorial", _editorial))

    def _brand():
        from content_generator.scheduler.daily import _BRAND_TAGLINES
        from content_generator.core.brand_validator import validate_brand_facts
        bad = [t for t in _BRAND_TAGLINES if not validate_brand_facts(t)]
        return not bad, f"{len(_BRAND_TAGLINES) - len(bad)}/{len(_BRAND_TAGLINES)} taglines valid"
    checks.append(_check("Brand", _brand))

    def _publish():
        if not publish_result:
            return True, "not run in this context"
        pub = [k for k, v in publish_result.items()
               if isinstance(v, dict) and v.get("success")]
        held = [k for k, v in publish_result.items()
                if isinstance(v, dict) and v.get("held")]
        return bool(pub or held), f"{len(pub)} published, {len(held)} held"
    checks.append(_check("Publishing", _publish))

    def _learning():
        from content_generator.core.learning_engine import _load_log, _is_measurable
        rows = _load_log()
        # Measurement truth comes from observed metric presence, not truthiness.
        # A real reach=0 measurement is valid and must not be treated as missing.
        measured = [e for e in rows if _is_measurable(e)]
        settled = 0
        try:
            from content_generator.analytics.insights_fetcher import _load_posts
            settled = len([p for p in _load_posts() if p.get("insights_recorded")])
        except Exception as e:
            logger.debug("[audit] tracked-post count unavailable: %s", e)

        if settled >= 3 and not measured:
            return False, (f"{settled} posts settled but 0 measurable records — "
                           f"insights are not landing; the loop is training on nothing")
        n = len(measured)
        return True, f"{n} measurable posts" + (" (cold start)" if n < 3 else "")
    checks.append(_check("Learning", _learning))

    def _reward():
        from content_generator.core.reward import get_active_kpi, get_weights, score
        kpi = get_active_kpi()
        w = get_weights(kpi)
        engagement = {"views": 200_000, "follows_gained": 10_000}
        commercial = {"views": 1_000, "revenue": 1}
        hierarchy_ok = score(commercial, kpi) > score(engagement, kpi)
        return bool(w) and hierarchy_ok, f"KPI={kpi}, commercial hierarchy={'OK' if hierarchy_ok else 'BROKEN'}"
    checks.append(_check("Reward", _reward))

    def _memory():
        from content_generator.core.learning_engine import _recency_factor
        import datetime
        old = {"posted_at": (today_ist() - datetime.timedelta(days=180)).isoformat()}
        fresh = {"posted_at": today_ist().isoformat()}
        return _recency_factor(old) < _recency_factor(fresh), "decay active"
    checks.append(_check("Memory", _memory))

    def _drift():
        from content_generator.core.editorial_engine import get_current_pass_score
        from content_generator.core.founder_policy import policy
        live, pol = get_current_pass_score(), policy().get("minimum_score")
        return float(live) == float(pol), f"threshold {live} == policy {pol}"
    checks.append(_check("Drift", _drift))

    def _forecast():
        from content_generator.intelligence.decision_layer import build_recommendation
        r = build_recommendation(int(content.get("day_number") or 0))
        return "confidence" in r, f"EVPOI {r.get('expected_evpoi')} @ conf {r.get('confidence')}"
    checks.append(_check("Forecast", _forecast))

    passed = sum(1 for _, ok, _ in checks if ok)
    score = round(100 * passed / max(len(checks), 1))
    healthy = score >= 80

    lines = ["================= ENGINE SELF-AUDIT ================="]
    for name, ok, detail in checks:
        lines.append(f"  {'OK  ' if ok else 'FAIL'}  {name:<11} {detail}")
    lines.append(f"  Overall health: {score}/100" + ("" if healthy else "   ** DEGRADED **"))
    lines.append("=" * 53)
    (logger.info if healthy else logger.error)("\n".join(lines))

    return {"checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
            "score": score, "healthy": healthy}
