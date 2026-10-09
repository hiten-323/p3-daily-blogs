"""Tests for platform-native follower-growth diagnostics."""
from content_generator.core.growth_contract import audit_asset, audit_portfolio


def test_youtube_requires_native_short_asset_and_complete_plan_warning():
    result = audit_asset("youtube", {"title": "Coffee truth", "scenes": [{"spoken": "Hook"}]})
    assert result["passes"]
    assert any("3+ beat" in warning for warning in result["warnings"])


def test_threads_warns_against_link_first_copy():
    result = audit_asset("threads", {"text": "Coffee opinion. https://p3online.in"})
    assert any("website link" in warning for warning in result["warnings"])


def test_fabricated_social_proof_is_a_hard_failure():
    result = audit_asset("instagram", {"caption": "10,000 customers love us"})
    assert not result["passes"]
    assert any("fabricated social proof" in error for error in result["errors"])


def test_empty_threads_is_a_hard_failure():
    result = audit_asset("threads", None)
    assert not result["passes"]


def test_portfolio_reports_missing_native_assets_without_inventing_them():
    result = audit_portfolio({"linkedin_post": {"hook": "Founder lesson"}})
    assert not result["results"]["threads"]["passes"]
    assert not result["results"]["youtube"]["passes"]
