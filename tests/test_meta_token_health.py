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
        # Every fallback route (/{page}, /me, /me/accounts, retry) finds no link.
        return responses.pop(0) if responses else ({"data": []} if "/me/accounts" in url else {"id": "page-123"})

    monkeypatch.setattr(health, "_fetch", fake_fetch)
    monkeypatch.setattr(health.time, "sleep", lambda s: None)
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




def test_strict_meta_preflight_fails_when_facebook_publish_scope_missing(monkeypatch, capsys):
    monkeypatch.setenv("META_TOKEN_MODE", "strict")
    monkeypatch.setenv("META_PUBLISH_PREFLIGHT", "true")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "ig-123")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "fb-123")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "fb-token")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "threads-token")
    monkeypatch.setenv("THREADS_USER_ID", "threads-123")
    monkeypatch.delenv("LI_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("LI_CLIENT_ID", raising=False)
    monkeypatch.delenv("LI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LI_API_ACCESS", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)

    monkeypatch.setattr(health, "inspect_instagram", lambda *a, **k: {
        "ok": True, "problems": [], "scopes": list(health.IG_SCOPES),
        "type": "USER", "expires": "never", "username": "puritybeans",
        "resolved_account_id": "",
    })
    monkeypatch.setattr(health, "inspect_token", lambda token, **k: {
        "type": "PAGE", "expires": "never", "scopes": [], "expired": False,
    } if token == "fb-token" else {
        "type": "USER", "expires": "never", "scopes": list(health.IG_SCOPES), "expired": False,
    })
    monkeypatch.setattr(health, "_fetch", lambda *a, **k: {"id": "threads-123", "username": "puritybeans"})

    assert health.run_checks(now=100) == 1
    out = capsys.readouterr().out
    assert "::error::Facebook page token: missing pages_manage_posts" in out


def test_strict_meta_preflight_fails_when_facebook_token_missing(monkeypatch, capsys):
    monkeypatch.setenv("META_TOKEN_MODE", "strict")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "fb-123")
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "ig-123")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-token")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "threads-token")
    monkeypatch.setenv("THREADS_USER_ID", "threads-123")
    monkeypatch.delenv("LI_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("LI_CLIENT_ID", raising=False)
    monkeypatch.delenv("LI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LI_API_ACCESS", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)

    monkeypatch.setattr(health, "inspect_instagram", lambda *a, **k: {
        "ok": True, "problems": [], "scopes": list(health.IG_SCOPES),
        "type": "USER", "expires": "never", "username": "puritybeans",
        "resolved_account_id": "",
    })
    monkeypatch.setattr(health, "_fetch", lambda *a, **k: {"id": "threads-123", "username": "puritybeans"})

    assert health.run_checks(now=100) == 1
    out = capsys.readouterr().out
    assert "::error::Facebook publishing credentials unavailable" in out


def test_strict_meta_preflight_fails_when_threads_identity_mismatches(monkeypatch, capsys):
    monkeypatch.setenv("META_TOKEN_MODE", "strict")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "ig-123")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "fb-123")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "fb-token")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "threads-token")
    monkeypatch.setenv("THREADS_USER_ID", "threads-expected")
    monkeypatch.delenv("LI_REFRESH_TOKEN", raising=False)
    monkeypatch.delenv("LI_CLIENT_ID", raising=False)
    monkeypatch.delenv("LI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LI_API_ACCESS", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)

    monkeypatch.setattr(health, "inspect_instagram", lambda *a, **k: {
        "ok": True, "problems": [], "scopes": list(health.IG_SCOPES),
        "type": "USER", "expires": "never", "username": "puritybeans",
        "resolved_account_id": "",
    })
    monkeypatch.setattr(health, "inspect_token", lambda token, **k: {
        "type": "PAGE", "expires": "never", "scopes": list(health.FB_SCOPES), "expired": False,
    })
    monkeypatch.setattr(health, "_fetch", lambda *a, **k: {"id": "threads-other", "username": "someone-else"})

    assert health.run_checks(now=100) == 1
    out = capsys.readouterr().out
    assert "::error::Threads account identity mismatch" in out
