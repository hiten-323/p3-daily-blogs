"""Generation must leave carousel, instagram_post, and a reel able to publish.

The fixture is tests/fixtures/day275_pre_repair.json from gen_2026-10-03_3af01357.
The daily pipeline overwrites output/content_YYYY-MM-DD.json, so this test must
not read that live file.
reel_1 had 4 frames, carousel and growth were stored as editorial 0 without a
measured review, instagram scored 7.9, and the blog used intro/body_html.
"""
import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "tests" / "fixtures" / "day275_pre_repair.json"

_DIMS = ("shareability", "saveability", "emotion_pull", "hook_strength", "brand_clarity")


def _score(overall: float) -> dict:
    return {
        "shareability": overall,
        "saveability": overall,
        "emotion_pull": overall,
        "hook_strength": overall,
        "brand_clarity": overall,
        "overall": overall,
        "verdict": "APPROVE",
        "feedback": "Measured review.",
    }


def _load():
    with CONTENT.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_day_275_shapes_and_repairs():
    from content_generator.core.editorial_engine import EditorialRejectException, _editorial_ok
    from content_generator.core.piece_integrity import ensure_structural_fields
    from content_generator.core.schema_validation import BlogSchema, ReelSchema, validate_or_fail
    from content_generator.scheduler.daily import _drop_unmeasured_score, _schema_issues

    raw = _load()
    assert raw["generation_id"] == "gen_2026-10-03_3af01357"
    reel = raw["reels"][0]
    assert len(reel["frames"]) == 4
    try:
        validate_or_fail(ReelSchema, reel)
        raise AssertionError("4-frame reel must fail ReelSchema")
    except Exception as exc:
        assert "at least 5" in str(exc)

    growth = copy.deepcopy(raw["growth_reel"])
    assert not growth.get("editorial_score")
    ensure_structural_fields(growth, "growth_reel")
    assert len(growth["frames"]) >= 5
    try:
        _editorial_ok("growth_reel", growth)
        raise AssertionError("unscored growth reel must not pass")
    except EditorialRejectException as exc:
        assert "score 0.0" not in str(exc)
        assert "no measured editorial score" in str(exc)

    carousel = copy.deepcopy(raw["carousel"])
    assert not str(carousel.get("caption") or "").strip()
    assert str(carousel["editorial_score"]["feedback"]).startswith("Brand copy validation failed")
    _drop_unmeasured_score(carousel)
    assert "editorial_score" not in carousel
    ensure_structural_fields(carousel, "carousel")
    assert len(carousel["caption"]) >= 50
    assert "purity beans" in carousel["caption"].lower()
    assert _schema_issues("carousel", carousel) == []

    blog = copy.deepcopy(raw["blog_post"])
    assert "introduction" not in blog and "body" not in blog
    ensure_structural_fields(blog, "blog_post")
    assert blog["introduction"].startswith("Wondering how to make coffee")
    assert len(blog["body"]) >= 1000
    issues = _schema_issues("blog_post", blog)
    assert issues
    assert "introduction" not in issues[0] or "Field required" not in issues[0].split("body")[0]
    try:
        validate_or_fail(BlogSchema, blog)
    except Exception as exc:
        text = str(exc)
        assert "introduction\n  Field required" not in text
        assert "body\n  Field required" not in text
        assert "conclusion" in text


def test_scoring_failure_is_retried_and_not_stored_as_zero():
    from content_generator.agents import editorial
    from content_generator.agents.editorial import EditorialScoreError, review_content
    import content_generator.providers.llm_router as router

    editorial._ENABLED = True
    try:
        editorial._validate({"overall": 0, "verdict": "REJECT", "feedback": "empty"})
        raise AssertionError("a score without dimensions must raise")
    except EditorialScoreError as exc:
        assert "missing dimensions" in str(exc)

    calls = {"n": 0}

    def fake_call(prompt, label="", max_tokens=3000):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"overall": 0, "verdict": "REJECT", "feedback": "truncated json"}
        return _score(8.4)

    original = router.call
    router.call = fake_call
    try:
        scored = review_content({"caption": "Check the label."}, label="carousel")
    finally:
        router.call = original
    assert calls["n"] == 2
    assert scored["overall"] == 8.4
    assert scored["shareability"] == 8.4


def test_editorial_pass_repairs_day_275_without_zero_scores():
    import content_generator.providers.llm_router as router
    from content_generator.core.brand_validator import validate_asset
    from content_generator.core.editorial_engine import approved_assets
    from content_generator.core.schema_validation import InstagramSchema, validate_or_fail
    from content_generator.scheduler.daily import _do_editorial

    content = _load()
    os.environ["QUALITY_MAX_REGEN"] = "2"
    state = {"ig": 0}

    def fake_call(prompt, label="", max_tokens=3000):
        if str(label).startswith("editorial_instagram"):
            state["ig"] += 1
            if state["ig"] == 1:
                scored = _score(7.9)
                scored["feedback"] = "Middle section drops attention."
                scored["verdict"] = "REJECT"
                return scored
            return _score(8.6)
        if str(label).startswith("editorial_"):
            return _score(8.6)
        if label == "regen_reel_1":
            frames = [dict(frame) for frame in content["reels"][0]["frames"]]
            while len(frames) < 6:
                frames.append({
                    "on_screen": "READ THE LABEL",
                    "spoken": "Check the jar for chicory before you brew the next cup.",
                })
            return {"frames": frames}
        return {"hook_text": "CHECK THE LABEL"}

    original_call = router.call
    original_ok = router.any_provider_available
    router.call = fake_call
    router.any_provider_available = lambda: True
    try:
        _do_editorial(content)
    finally:
        router.call = original_call
        router.any_provider_available = original_ok

    carousel = content["carousel"]
    assert carousel["editorial_score"]["overall"] == 8.6
    assert not str(carousel["editorial_score"].get("feedback") or "").startswith("Brand copy")
    assert len(carousel["caption"]) >= 50

    ig = content["instagram_post"]
    assert ig["editorial_score"]["overall"] == 8.6
    assert state["ig"] >= 2
    validate_or_fail(InstagramSchema, ig)
    ok, issues = validate_asset("instagram_post", ig)
    assert ok, issues

    assert len(content["reels"][0]["frames"]) >= 5
    assert content["reels"][0]["editorial_score"]["overall"] == 8.6
    assert content["growth_reel"]["editorial_score"]["overall"] == 8.6
    assert content["yt_short"]["editorial_score"]["overall"] >= 8

    blog = content["blog_post"]
    assert blog.get("introduction") and blog.get("body")
    assert not (isinstance(blog.get("editorial_score"), dict) and blog["editorial_score"].get("overall") == 0)

    approved = approved_assets(content)
    assert "carousel" in approved
    assert any(key in approved for key in ("reel_1", "reel_2", "growth_reel"))


def test_brand_failure_does_not_stamp_editorial_zero():
    import content_generator.providers.llm_router as router
    from content_generator.scheduler.daily import _do_editorial

    content = {
        "linkedin_post": {
            "hook": "A short line about coffee.",
            "body": "Too short to be a post.",
            "cta": "Read more.",
        }
    }
    os.environ["QUALITY_MAX_REGEN"] = "0"
    original_ok = router.any_provider_available
    router.any_provider_available = lambda: True
    try:
        _do_editorial(content)
    finally:
        router.any_provider_available = original_ok
    piece = content["linkedin_post"]
    assert piece.get("editorial_score") in (None, {})
    assert "brand" in str(piece.get("editorial_error") or "").lower()


def test_generate_workflow_rejects_unpublishable_content():
    text = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "approved_assets" in text
    assert "GENERATE saved content the morning and evening slots cannot publish" in text
    assert "cron: '30 0 * * *'" in text
