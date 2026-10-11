from unittest.mock import patch

from content_generator.publisher.prepublish_gate import authorize_publish


def test_unknown_platform_fails_closed():
    result = authorize_publish({}, "myspace")
    assert result["allowed"] is False
    assert result["reason"] == "unknown_platform"


def test_invalid_payload_fails_closed():
    result = authorize_publish(None, "instagram")
    assert result["allowed"] is False
    assert result["reason"] == "invalid_content_payload"


def test_missing_native_asset_fails_closed():
    with patch("content_generator.core.editorial_engine.approved_assets", return_value={}):
        result = authorize_publish({}, "facebook")
    assert result["allowed"] is False
    assert result["reason"] == "missing_native_asset"


def test_editorial_gate_exception_fails_closed():
    with patch("content_generator.core.editorial_engine.approved_assets", side_effect=RuntimeError("boom")):
        result = authorize_publish({"facebook_post": {"body": "some copy"}}, "facebook")
    assert result["allowed"] is False
    assert result["reason"] == "editorial_gate_error:RuntimeError"
