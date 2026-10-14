"""The growth engine is enforced: plans, claims, the 15 scores, and publish confirmation."""
from __future__ import annotations

import json

from content_generator.core.growth_engine import (
    DIMENSIONS,
    confirmed_published,
    enforce_portfolio,
    learning_block,
    performance_hypothesis,
    review_asset,
    review_portfolio,
    whatsapp_enabled,
)
from content_generator.prompts.growth_engine.plans import BANNED_OPENERS, OBJECTIVES, asset_plan
from content_generator.prompts.growth_engine.platforms import generation_preface, prompt_block, ultra_positive_story


def _bold_post():
    return {
        "hook": "Why the label matters",
        "body": "Bold is pure coffee with zero chicory.",
        "cta": "Send this to someone who reads the jar.",
        "editorial_score": {"overall": 9.0},
    }


def test_prompt_modules_are_native_and_keep_the_journey():
    preface = generation_preface("Bold", 285)
    assert "STOP, CURIOSITY, VALUE, TRUST, FOLLOW, BUY" in preface
    assert "hello everyone" in preface.lower()
    assert ultra_positive_story("Bold") == ""
    story = ultra_positive_story("Ultra Blend")
    assert "70% coffee and 30% chicory" in story
    assert "zero chicory" in story.lower()
    block = prompt_block("threads_post", "Bold", 285)
    assert "PLATFORM MODULE (threads)" in block
    assert "Primary objective:" in block
    reel = prompt_block("reel_1", "Ultra Blend", 285)
    assert "70% coffee" in reel
    assert prompt_block("reel_2", "Bold", 285) != prompt_block("reel_1", "Bold", 285)


def test_plans_use_one_objective_and_do_not_share_angles():
    angles, promises = set(), set()
    for platform in ("reel", "carousel", "ig_single", "stories", "facebook", "threads", "linkedin", "yt_short", "blog"):
        plan = asset_plan(platform, 285, "Bold")
        assert plan["primary_objective"] in OBJECTIVES
        assert plan["secondary_objective"] in OBJECTIVES or plan["secondary_objective"] is None
        assert plan["secondary_objective"] != plan["primary_objective"]
        assert plan["angle"] not in angles
        assert plan["follow_promise"] not in promises
        angles.add(plan["angle"])
        promises.add(plan["follow_promise"])
    assert not whatsapp_enabled()


def test_banned_opener_is_a_hard_fail_and_retries_end_blocked():
    piece = _bold_post()
    piece["hook"] = BANNED_OPENERS[0].title() + ", look at this jar"
    review = review_asset("facebook", piece, {"facebook_post": piece, "featured_product": "Bold"}, label="facebook_post", max_retries=1)
    assert review["decision"] == "REGENERATE"
    assert any(item.startswith("banned_opener") for item in review["hard_fails"])
    content = {"featured_product": "Bold", "facebook_post": piece}
    summary = enforce_portfolio(content, regenerate=lambda *_args: None, max_retries=1)
    assert summary["assets"][0]["decision"] == "BLOCKED"
    assert content["facebook_post"]["growth_review"]["decision"] == "BLOCKED"


def test_ultra_day_requires_the_ratio_on_every_scanned_field():
    piece = {
        "hook": "Why this jar is different",
        "body": "Ultra Blend is zero chicory and pure coffee.",
        "cta": "Shop the jar.",
        "comment_trigger": "What is in your jar?",
    }
    review = review_asset("facebook", piece, {"facebook_post": piece, "featured_product": "Ultra Blend"}, label="facebook_post")
    assert review["decision"] != "PASS"
    assert any("ultra_ratio" in item or "claim_or_brand" in item for item in review["hard_fails"])
    honest = {
        "hook": "Why the 70/30 cup is a milk coffee",
        "body": "Ultra Blend is 70% coffee and 30% chicory, a smooth milk coffee.",
        "cta": "Follow @purepantryprovisions for the next blend check.",
        "comment_trigger": "Do you read the chicory line?",
    }
    passed = review_asset("facebook", honest, {"facebook_post": honest, "featured_product": "Ultra Blend"}, label="facebook_post")
    assert passed["hard_fails"] == [] or not any("ultra_ratio" in item or "claim_or_brand" in item for item in passed["hard_fails"])


def test_fifteen_dimensions_have_evidence_and_threshold_holds():
    content = {"featured_product": "Bold", "facebook_post": _bold_post()}
    summary = review_portfolio(content)
    asset = summary["assets"][0]
    assert asset["decision"] == "PASS"
    assert asset["overall"] >= asset["threshold"] == 8.0
    assert [item["name"] for item in asset["dimensions"]] == list(DIMENSIONS)
    assert all(item["evidence"] for item in asset["dimensions"])
    assert asset["published"] is False
    assert "Reel discovers" in summary["complement"]


def test_duplicate_hook_fails_the_later_platform_only():
    hook = "Why the label matters more than the lid colour"
    content = {
        "featured_product": "Bold",
        "facebook_post": {**_bold_post(), "hook": hook},
        "threads_post": {"hook": hook, "text": "Bold is pure coffee with zero chicory. Follow for the label check.", "cta": "Reply with the first ingredient."},
    }
    summary = review_portfolio(content)
    by_label = {asset["label"]: asset for asset in summary["assets"]}
    assert by_label["facebook_post"]["decision"] == "PASS"
    assert any(item.startswith("duplicate_hook") for item in by_label["threads_post"]["hard_fails"])
    assert by_label["threads_post"]["decision"] != "PASS"


def test_schema_failure_cannot_pass_on_a_high_average():
    piece = {"hook": "Why four frames are not a reel", "body": "Bold is pure coffee with zero chicory.", "cta": "Follow @purepantryprovisions.", "frames": [{"on_screen": "READ", "spoken": "Read the label."}]}
    review = review_asset("reel", piece, {"featured_product": "Bold", "reels": [piece]}, label="reel_1")
    assert any(item.startswith("schema") for item in review["hard_fails"])
    assert review["decision"] != "PASS"


def test_verified_metrics_become_a_hypothesis_and_likes_do_not():
    assert performance_hypothesis("instagram", {"metrics": {"likes": 9000}})["used"] is False
    note = performance_hypothesis("instagram", {
        "metrics_verified": True,
        "platform_confirmed": True,
        "metrics": {"reach": 1000, "shares": 40, "likes": 9000},
    })
    assert note["used"] is True
    assert note["viral_claim"] is False
    assert "likes" not in note["metrics"]
    assert learning_block([{"track": "instagram", "metrics": {"reach": 10}}]) == ""
    block = learning_block([{"track": "instagram", "metrics_verified": True, "platform_confirmed": True, "metrics": {"reach": 1000, "saves": 30}}])
    assert "VERIFIED PERFORMANCE ONLY" in block


def test_published_requires_platform_confirmation():
    assert confirmed_published({"status": "PUBLISHED_UNVERIFIED", "published": False}) is False
    assert confirmed_published({"status": "VERIFIED_LIVE", "published": False}) is False
    assert confirmed_published({"status": "VERIFIED_LIVE", "published": True}) is True


def test_authorize_publish_still_passes_a_truthful_bold_post(monkeypatch):
    from tests.test_universal_pre_publish_gate import _passing_native_gates
    from content_generator.publisher.prepublish_gate import authorize_publish
    _passing_native_gates(monkeypatch)
    result = authorize_publish({"facebook_post": _bold_post(), "featured_product": "Bold"}, "facebook")
    assert result["reason"] != "product_truth_failed"
    assert result["allowed"] is True
    assert result["checks"]["growth_engine"]["decision"] == "PASS"


def test_day_pack_portfolio_is_serializable():
    from pathlib import Path
    path = Path("output/content_2026-10-13.json")
    if not path.exists():
        return
    content = json.loads(path.read_text(encoding="utf-8"))
    summary = review_portfolio(content)
    json.dumps(summary)
    assert summary["sku"] == "Bold"
    assert summary["assets"]
    assert set(summary["counts"]) == {"PASS", "REGENERATE", "BLOCKED"}


def test_new_brand_rules_hard_fail():
    from content_generator.core.product_truth import product_truth_findings
    assert product_truth_findings("Ultra Blend is pure comfort in a jar.")
    assert any("FSSAI" in f["reason"] for f in product_truth_findings("Purica is 100% Arabica."))
    assert any("Bold" in f["reason"] for f in product_truth_findings("Bold is a Robusta coffee."))
    assert not product_truth_findings("Bold is pure coffee in a lead-free glass jar.")


def test_wrong_handle_is_a_hard_fail():
    from content_generator.core.growth_engine import review_asset
    piece = {"hook": "What the jar label tells you before you buy", "caption": "Bold is pure coffee. Follow @puritybeans for label checks. Shop p3online.in",
             "cta": "Follow @puritybeans", "image_prompt": "jar"}
    out = review_asset("instagram", piece, {"featured_product": "Bold"}, label="instagram_post")
    assert out["decision"] != "PASS"
    assert any("wrong_handle" in h for h in out.get("hard_fails", out.get("hard", [])))


def test_threshold_never_lowered():
    from content_generator.core import growth_engine as ge
    assert ge.PASS_THRESHOLD == 8.0
    import content_generator.core.editorial_engine as ee
    orig = ee.get_current_pass_score
    ee.get_current_pass_score = lambda: 6.5
    try:
        assert ge._threshold() == 8.0
    finally:
        ee.get_current_pass_score = orig
