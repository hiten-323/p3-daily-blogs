import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_generator.ops import meta_token_health as health


def test_page_id_resolves_to_linked_instagram_business_account(monkeypatch):
    responses = [
        {"data": {"type": "PAGE", "expires_at": 0, "scopes": ["instagram_basic", "instagram_content_publish"], "is_valid": True}},
        {"id": "page-123"},
        {"id": "page-123", "instagram_business_account": {"id": "ig-456", "username": "puritybeans"}},
    ]
    calls = []

    def fake_fetch(url, headers, timeout=15):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(health, "_fetch", fake_fetch)
    report = health.inspect_instagram("page-123", "test-token", now=100)
    assert report["ok"] is True
    assert report["username"] == "puritybeans"
    assert report["resolved_account_id"] == "ig-456"
    assert "instagram_business_account" in calls[-1]


def test_page_id_without_linked_instagram_account_fails_closed(monkeypatch):
    responses = [
        {"data": {"type": "PAGE", "expires_at": 0, "scopes": ["instagram_basic", "instagram_content_publish"], "is_valid": True}},
        {"id": "page-123"},
        {"id": "page-123"},
    ]

    def fake_fetch(url, headers, timeout=15):
        return responses.pop(0)

    monkeypatch.setattr(health, "_fetch", fake_fetch)
    report = health.inspect_instagram("page-123", "test-token", now=100)
    assert report["ok"] is False
    assert any("Facebook Page ID" in problem for problem in report["problems"])


def test_facebook_page_token_resolution(monkeypatch):
    from content_generator.publisher import facebook
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "12345")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "user_token")

    class DummyResponse:
        status_code = 200
        def json(self):
            return {"access_token": "resolved_page_token_abc"}

    monkeypatch.setattr("requests.get", lambda url, **kwargs: DummyResponse())
    token = facebook.resolve_page_access_token("12345", "user_token")
    assert token == "resolved_page_token_abc"


def test_meta_cdn_upload_fallback(monkeypatch, tmp_path):
    from content_generator.publisher import instagram
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"dummy")

    monkeypatch.setenv("FACEBOOK_PAGE_ID", "12345")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "fb_token")
    monkeypatch.delenv("IMGBB_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)

    class DummyPost:
        status_code = 200
        def json(self):
            return {"id": "photo_999"}

    class DummyGet:
        status_code = 200
        def json(self):
            return {"images": [{"source": "https://scontent.xx.fbcdn.net/v/photo.jpg"}]}

    monkeypatch.setattr("requests.post", lambda url, **kwargs: DummyPost())
    monkeypatch.setattr("requests.get", lambda url, **kwargs: DummyGet())

    url = instagram._upload_to_public_url(str(test_file))
    assert url == "https://scontent.xx.fbcdn.net/v/photo.jpg"

