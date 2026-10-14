from unittest.mock import patch

from content_generator.publisher.prepublish_gate import authorize_publish


def test_missing_native_asset_fails_closed():
    with patch("content_generator.core.editorial_engine.approved_assets", return_value={}):
        result = authorize_publish({"instagram_post": {"caption": "some copy"}}, "facebook")
    assert result["allowed"] is False
    assert result["reason"] == "missing_native_asset"


def test_facebook_native_asset_without_measured_editorial_score_fails_closed():
    with patch("content_generator.core.editorial_engine.approved_assets", return_value={}):
        result = authorize_publish(
            {"facebook_post": {"hook": "Why coffee labels matter", "body": "Check the ingredient list."}},
            "facebook",
        )
    assert result["allowed"] is False
    assert result["reason"] == "native_asset_missing_passing_editorial_score"


def test_threads_over_limit_fails_closed_even_with_score(monkeypatch):
    from content_generator.core import editorial_engine
    monkeypatch.setattr(editorial_engine, "approved_assets", lambda content: {})
    monkeypatch.setattr(editorial_engine, "get_current_pass_score", lambda: 8.0)
    piece = {
        "text": "Why coffee labels matter. Check the ingredient list. " + ("x" * 490),
        "hook": "Why coffee labels matter",
        "body": "Check the ingredient list.",
        "editorial_score": {"overall": 9.0},
    }
    result = authorize_publish({"threads_post": piece}, "threads")
    assert result["allowed"] is False
    assert result["reason"] in {
        "platform_contract_failed", "viral_readiness_failed", "shareability_failed", "threads_text_over_500_characters"
    }


def test_unknown_platform_fails_closed():
    result = authorize_publish({}, "unknown")
    assert result["allowed"] is False
    assert result["reason"] == "unknown_platform"


def _passing_native_gates(monkeypatch):
    from content_generator.core import editorial_engine
    monkeypatch.setattr(editorial_engine, "approved_assets", lambda content: {})
    monkeypatch.setattr(editorial_engine, "get_current_pass_score", lambda: 8.0)
    monkeypatch.setattr(
        "content_generator.core.growth_contract.audit_asset",
        lambda platform, asset, objective: {"errors": []},
    )
    monkeypatch.setattr(
        "content_generator.core.viral_readiness.evaluate_viral_readiness",
        lambda asset, platform="", objective="": {"passes": True, "score": 90},
    )
    monkeypatch.setattr(
        "content_generator.core.content_contract.shareability",
        lambda asset: {"passes": True, "score": 80},
    )


def test_ultra_blend_zero_chicory_fails_product_truth(monkeypatch):
    _passing_native_gates(monkeypatch)
    piece = {
        "hook": "Why this jar is different",
        "body": "Ultra Blend is zero chicory and pure coffee.",
        "editorial_score": {"overall": 9.0},
    }
    result = authorize_publish({"facebook_post": piece}, "facebook")
    assert result["allowed"] is False
    assert result["reason"] == "product_truth_failed"


def test_featured_ultra_blend_roasted_root_cta_fails_product_truth(monkeypatch):
    _passing_native_gates(monkeypatch)
    piece = {
        "hook": "Cafe prices, home jar",
        "body": "A smooth milk coffee for the everyday cup.",
        "primary_cta": "Follow @puritybeans so you never drink roasted root again",
        "editorial_score": {"overall": 9.0},
    }
    result = authorize_publish(
        {"facebook_post": piece, "featured_product": "Ultra Blend", "day_number": 284},
        "facebook",
    )
    assert result["allowed"] is False
    assert result["reason"] == "product_truth_failed"


def test_bold_zero_chicory_is_not_a_product_truth_failure(monkeypatch):
    _passing_native_gates(monkeypatch)
    piece = {
        "hook": "Why the label matters",
        "body": "Bold is pure coffee with zero chicory.",
        "cta": "Send this to someone who reads the jar.",
        "editorial_score": {"overall": 9.0},
    }
    result = authorize_publish({"facebook_post": piece}, "facebook")
    assert result["reason"] != "product_truth_failed"
    assert result["allowed"] is True
