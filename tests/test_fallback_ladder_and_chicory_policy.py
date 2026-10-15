"""Fallback ladder + no-chicory-attack policy (Hiten, 2026-10-14)."""
import glob, re, pathlib
import pytest

from content_generator.core import fallback_ladder as L


def test_cap_default_and_ceiling(monkeypatch):
    monkeypatch.delenv("QUALITY_LADDER_MAX", raising=False)
    assert L.max_attempts() == 8
    monkeypatch.setenv("QUALITY_LADDER_MAX", "999")
    assert L.max_attempts() == L.HARD_CEILING
    monkeypatch.setenv("QUALITY_LADDER_MAX", "0")
    assert L.max_attempts() == 1


def test_rung_rotation():
    rungs = [L.rung_for(i) for i in range(1, 9)]
    assert rungs[:3] == ["feedback"] * 3
    assert rungs[3:5] == ["alt_angle"] * 2
    assert rungs[5] == "evergreen"


def test_gate_floor_never_lowered():
    assert L.PASS_FLOOR == 8.0
    assert not L.passes(7.99, False, 5.0)
    assert not L.passes(9.5, True, 8.0)
    assert L.passes(8.0, False, 8.0)


def test_stops_at_first_pass():
    calls = []
    scores = iter([6.0, 7.0, 8.4, 9.9])
    def evaluate(p):
        s = next(scores); return (s >= 8.0, f"score {s}")
    def rewrite(label, p, fb):
        calls.append(fb); return {"v": len(calls)}
    piece, rec = L.run_ladder("threads_post", {"v": 0}, evaluate, rewrite, cap=8)
    assert rec["status"] == "passed" and rec["attempts"] == 2 and piece == {"v": 2}


def test_exhaustion_is_capped_and_held():
    n = {"c": 0}
    def rewrite(label, p, fb):
        n["c"] += 1; return {"v": n["c"]}
    piece, rec = L.run_ladder("facebook_post", {"v": 0}, lambda p: (False, "6.5"), rewrite,
                              cap=8, evergreen=lambda *a: None)
    assert rec["status"] == "exhausted" and rec["attempts"] == 8 and n["c"] == 8


def test_alt_angle_and_evergreen_rungs_used():
    seen = []
    def rewrite(label, p, fb):
        seen.append(fb); return {"x": 1}
    eg = {"source": "evergreen_template"}
    out, rec = L.run_ladder("reel_1", {}, lambda p: (p is eg, "no"), rewrite, cap=8,
                            evergreen=lambda *a: eg)
    assert rec["status"] == "passed" and rec["history"][-1]["rung"] == "evergreen"
    assert any("ALTERNATIVE ANGLE" in s for s in seen)


def test_evergreen_templates_exist_for_core_types():
    for label in ("reel_1", "carousel", "instagram_post", "linkedin_post"):
        assert L.evergreen_piece(label, 286, 6)


# ── chicory policy ───────────────────────────────────────────────────────────
_SOURCES = (glob.glob("content_generator/prompts/**/*.py", recursive=True)
            + ["content_generator/rotation.py", "content_generator/scheduler/fallback.py",
               "content_generator/core/growth_director.py", "content_generator/core/coffee_psychology.py",
               "content_generator/core/blog_plan.py", "config/brand_config.py"])
_ATTACK = re.compile(
    r"chicory filler|root filler|roasted root (?:scam|filler)|adulterant|adulterat|"
    r"fooled by chicory|disguised as coffee|#(?:Zero|No)Chicory|"
    r"compare 0% chicory jars|pure coffee with zero chicory|"
    r"(?:years|after) of filler|masking burnt filler|coping with \d+% roasted chicory",
    re.I)
_NEG = re.compile(r"\b(never|do not|don't|no\b|not attack|prohibited)", re.I)


@pytest.mark.parametrize("path", _SOURCES)
def test_no_anti_chicory_copy_in_generation_sources(path):
    bad = []
    for i, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if _ATTACK.search(line) and not _NEG.search(line):
            bad.append(f"{path}:{i}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)


def test_policy_in_every_generation_preface():
    from content_generator.prompts.growth_engine.platforms import generation_preface, CHICORY_POLICY
    for sku in ("Bold", "Purista", "Purica", "Prima", "Ultra Blend"):
        pre = generation_preface(sku, 286)
        assert CHICORY_POLICY in pre
    assert "70% coffee and 30% chicory" in CHICORY_POLICY


def test_native_modules_have_follow_and_shop():
    from content_generator.prompts.growth_engine.platforms import _NATIVE
    for k in ("reel", "facebook", "threads"):
        assert "@purepantryprovisions" in _NATIVE[k] and "p3online.in" in _NATIVE[k]


def test_fallback_templates_pass_product_truth():
    from content_generator.scheduler.fallback import _EVERGREEN
    from content_generator.core.product_truth import product_truth_findings
    import json
    for t in _EVERGREEN:
        assert not product_truth_findings(json.dumps(t, ensure_ascii=False)), t.get("hook")


# ── retry-unposted ───────────────────────────────────────────────────────────
import datetime as _dt
from content_generator.scheduler import retry_unposted as RU


def _rec(slot, platform, status, **kw):
    return {"slot": slot, "platform": platform, "status": status, **kw}


def test_unposted_respects_timed_slots(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    assert RU.unposted_targets([], 8) == ["linkedin", "youtube", "threads"]
    assert "blog" not in RU.unposted_targets([], 8)
    assert "ig_reel" not in RU.unposted_targets([], 16)
    assert "ig_reel" in RU.unposted_targets([], 22)
    monkeypatch.setenv("BLOG_ENABLED", "true")
    assert "blog" in RU.unposted_targets([], 8)


def test_posted_and_uncertain_are_not_retried():
    recs = [_rec("morning", "instagram", "VERIFIED_LIVE"),
            _rec("generate", "linkedin", "PUBLISHED_UNVERIFIED"),
            _rec("evening", "instagram_video", "UNCERTAIN")]
    todo = RU.unposted_targets(recs, 23)
    assert "ig_feed" not in todo and "linkedin" not in todo and "ig_reel" not in todo
    assert "facebook" in todo


def test_failed_is_retried():
    assert "threads" in RU.unposted_targets([_rec("generate", "threads", "FAILED")], 12)


def test_rate_limit_backoff_exponential_and_capped():
    now = _dt.datetime(2026, 10, 14, 12, 0, tzinfo=_dt.timezone.utc)
    t = lambda m: (now - _dt.timedelta(minutes=m)).isoformat()
    r1 = [_rec("generate", "threads", "FAILED", error="HTTP 429 rate limit", attempt_count=1, updated_at=t(20))]
    assert not RU.backoff_ok(r1, "threads", now)
    r1[0]["updated_at"] = t(31)
    assert RU.backoff_ok(r1, "threads", now)
    r9 = [_rec("generate", "threads", "FAILED", error="429", attempt_count=9, updated_at=t(200))]
    assert not RU.backoff_ok(r9, "threads", now)
    r9[0]["updated_at"] = t(241)
    assert RU.backoff_ok(r9, "threads", now)
    other = [_rec("generate", "threads", "FAILED", error="bad caption", attempt_count=5, updated_at=t(1))]
    assert RU.backoff_ok(other, "threads", now)


def test_ledger_dedupes_across_content_ids(monkeypatch):
    from content_generator.publisher import publishing_ledger as PL
    monkeypatch.setattr(PL, "records_for_today", lambda: [
        {"ledger_key": "2026-10-14|morning|instagram|OLD", "platform": "instagram",
         "slot": "morning", "status": "VERIFIED_LIVE", "url": "https://instagram.com/p/x"}])
    assert PL.already_posted_today("instagram", "morning", "2026-10-14|morning|instagram|NEW")
    assert not PL.already_posted_today("instagram", "evening", "k")
    assert not PL.already_posted_today("facebook", "morning", "k")


@pytest.mark.skipif(not pathlib.Path(".github/workflows/retry-unposted.yml").exists(), reason="workflow file added separately (needs workflow scope)")
def test_workflow_every_30_min_and_shares_concurrency():
    y = pathlib.Path(".github/workflows/retry-unposted.yml").read_text()
    assert "7,37 * * * *" in y and "group: purity-beans-daily" in y
    assert "retry_unposted" in y


# ── per-cup price (Hiten, 2026-10-14) ────────────────────────────────────────
from content_generator.core.product_truth import product_truth_findings as _ptf


@pytest.mark.parametrize("text", [
    "Purity Beans at Rs 18 per cup.", "Just ₹18 a cup.", "Only Rs.18/cup at home.", "RS 18 PER CUP",
    "Pure coffee for eighteen rupees a cup.",
])
def test_rs18_per_cup_hard_fails(text):
    assert any("Rs 18" in f.get("rule", str(f)) or "₹18" in str(f) for f in _ptf(text)), _ptf(text)


def test_ultra_blend_per_cup_allowed_only_on_ultra():
    assert not [f for f in _ptf("Ultra Blend is about ₹5 a cup, at least 66 cups per 100g jar.") if "cup" in str(f)]
    assert any("Per-cup" in str(f) for f in _ptf("Purica is about ₹6 a cup."))


def test_no_rs18_left_in_sources():
    bad = []
    for path in glob.glob("content_generator/**/*.py", recursive=True) + glob.glob("config/*.py"):
        for i, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?:\brs\.?|₹)\s*18(?!\d)", line, re.I) and "_RS18" not in line and "never claim" not in line:
                bad.append(f"{path}:{i}")
    assert not bad, bad
