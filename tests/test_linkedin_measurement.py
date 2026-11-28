"""Tests for PR A: LinkedIn measurement resilience and tracking."""
import datetime as dt
import urllib.error
import pytest

from content_generator.analytics import platform_learning, insights_fetcher


def test_linkedin_default_version_fallback(monkeypatch):
    """When LINKEDIN_VERSION is unset, fallback to publisher.active_api_version()."""
    monkeypatch.delenv("LINKEDIN_VERSION", raising=False)
    monkeypatch.delenv("LI_API_VERSION", raising=False)
    monkeypatch.setenv("LI_API_ACCESS", "test_mock_token")

    called_urls = []

    def mock_request_json(url, headers=None):
        called_urls.append((url, headers))
        return {
            "likesSummary": {"totalLikes": 14},
            "commentsSummary": {"totalFirstLevelComments": 3},
        }

    monkeypatch.setattr(platform_learning, "_request_json", mock_request_json)
    metrics = platform_learning._fetch_linkedin("urn:li:share:123456")

    assert metrics == {"likes": 14, "comments": 3}
    assert len(called_urls) == 1
    req_url, req_headers = called_urls[0]
    assert "https://api.linkedin.com/rest/socialActions/" in req_url
    assert req_headers["Authorization"] == "Bearer test_mock_token"
    # Header LinkedIn-Version must be present and formatted as YYYYMM
    assert len(req_headers["LinkedIn-Version"]) == 6


def test_linkedin_organization_entity_statistics(monkeypatch):
    """When organization author URN is configured, fetch organizationalEntityShareStatistics."""
    monkeypatch.setenv("LI_API_ACCESS", "test_mock_token")
    monkeypatch.setenv("LI_AUTHOR_URN", "urn:li:organization:987654321")

    called_urls = []

    def mock_request_json(url, headers=None):
        called_urls.append((url, headers))
        if "organizationalEntityShareStatistics" in url:
            return {
                "elements": [
                    {
                        "totalShareStatistics": {
                            "uniqueImpressionsCount": 1500,
                            "clickCount": 45,
                            "likeCount": 30,
                            "commentCount": 8,
                            "shareCount": 5,
                        }
                    }
                ]
            }
        return None

    monkeypatch.setattr(platform_learning, "_request_json", mock_request_json)
    metrics = platform_learning._fetch_linkedin("urn:li:share:123456")

    assert metrics == {
        "impressions": 1500,
        "clicks": 45,
        "likes": 30,
        "comments": 8,
        "shares": 5,
    }
    assert any("organizationalEntityShareStatistics" in u[0] for u in called_urls)


def test_linkedin_scope_missing_terminal_status(monkeypatch):
    """When API returns 401/403, status must be terminal linkedin_scope_missing... and not stay pending."""
    monkeypatch.setenv("LI_API_ACCESS", "test_mock_token")

    def mock_request_json(url, headers=None):
        platform_learning._LAST_HTTP_ERROR["code"] = 403
        platform_learning._LAST_HTTP_ERROR["detail"] = "Not enough permissions to access: rest/socialActions"
        return None

    monkeypatch.setattr(platform_learning, "_request_json", mock_request_json)
    metrics, status = platform_learning._fetch_platform_metrics({"platform": "linkedin", "media_id": "urn:li:share:123456"})

    assert metrics is None
    assert status == "linkedin_scope_missing_r_member_social_or_r_organization_social"


def test_linkedin_published_record_stores_hook_and_metadata(monkeypatch, tmp_path):
    """Ensure track_dispatch_results preserves hook, angle, hashtags, char_count, and timing."""
    tracker_file = tmp_path / "published_posts.json"
    monkeypatch.setattr(insights_fetcher, "_POSTS_PATH", str(tracker_file))

    dispatch_result = {
        "linkedin": {
            "success": True,
            "post_id": "urn:li:share:999888777",
            "image_urn": "urn:li:image:111",
        }
    }
    content = {
        "metadata": {"linkedin_angle": "pantry_economics", "featured_product": "Ultra Blend"},
        "linkedin_post": {
            "hook": "Why your office pantry coffee tastes like cardboard",
            "commentary": "Most office coffee is 70% filler. Here is what we do instead...",
            "hashtags": ["#PurityBeans", "#B2B", "#OfficeCoffee"],
            "cta_type": "dm_inquiry",
        }
    }

    insights_fetcher.track_dispatch_results(dispatch_result, content, day_number=335)
    posts = insights_fetcher._load_posts()

    assert len(posts) == 1
    post = posts[0]
    assert post["media_id"] == "urn:li:share:999888777"
    assert post["hook"] == "Why your office pantry coffee tastes like cardboard"
    assert "#PurityBeans #B2B #OfficeCoffee" in post["hashtags"]
    assert post["angle"] == "pantry_economics"
    assert post["featured_product"] == "Ultra Blend"
    assert post["cta_type"] == "dm_inquiry"
    assert post["has_image"] is True
    assert post["char_count"] > 10
    assert "posted_at_ist_hour" in post
