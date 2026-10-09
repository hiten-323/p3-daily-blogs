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
