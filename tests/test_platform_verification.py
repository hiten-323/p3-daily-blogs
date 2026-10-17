import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_threads_readback_uses_threads_api_base(monkeypatch):
    from config.api_versions import THREADS_BASE_URL
    from content_generator.publisher import platform_verification as verify

    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "test-token")
    captured = {}
    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200, {"id": "thread-123", "permalink": "https://threads.net/t/123"})

    monkeypatch.setattr(verify.requests, "get", fake_get)
    result = verify.verify_remote_post("threads", {"remote_id": "thread-123"})
    assert result["state"] == "found"
    assert captured["url"].startswith(THREADS_BASE_URL + "/")
    assert captured["params"]["access_token"] == "test-token"


def test_shopify_readback_uses_configured_api_version(monkeypatch):
    from config.api_versions import SHOPIFY_API_VERSION
    from content_generator.publisher import platform_verification as verify

    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("SHOPIFY_BLOG_ID", "77")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200, {"article": {"id": 123, "published_at": "2026-10-09T10:00:00Z"}})

    monkeypatch.setattr(verify.requests, "get", fake_get)
    result = verify.verify_remote_post("blog", {"remote_id": "123"})
    assert result["state"] == "found"
    assert f"/admin/api/{SHOPIFY_API_VERSION}/" in captured["url"]
    assert captured["headers"]["X-Shopify-Access-Token"] == "test-token"



def test_youtube_verification_falls_back_to_public_oembed_on_api_403(monkeypatch):
    from google.oauth2.credentials import Credentials
    from content_generator.publisher import platform_verification as verify

    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client-secret")

    def fake_refresh(self, request):
        self.token = "access-token"

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if "googleapis.com/youtube/v3/videos" in url:
            return FakeResponse(403, {"error": {"message": "insufficient scope"}})
        return FakeResponse(200, {"title": "Purity Beans Short", "author_name": "PURITY BEANS"})

    monkeypatch.setattr(verify.requests, "get", fake_get)
    result = verify.verify_remote_post("youtube", {"remote_id": "video-123"})

    assert result["state"] == "found"
    assert result["method"] == "youtube_oembed"
    assert len(calls) == 2
    assert calls[1][0] == "https://www.youtube.com/oembed"
    assert calls[1][1]["params"]["url"] == "https://www.youtube.com/watch?v=video-123"


def test_youtube_oembed_negative_result_stays_unknown(monkeypatch):
    from google.oauth2.credentials import Credentials
    from content_generator.publisher import platform_verification as verify

    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(Credentials, "refresh", lambda self, request: setattr(self, "token", "access-token"))

    def fake_get(url, **kwargs):
        if "googleapis.com/youtube/v3/videos" in url:
            return FakeResponse(403, {})
        return FakeResponse(404, {})

    monkeypatch.setattr(verify.requests, "get", fake_get)
    result = verify.verify_remote_post("youtube", {"remote_id": "video-123"})

    assert result["state"] == "unknown"
    assert result["method"] == "youtube_oembed"
