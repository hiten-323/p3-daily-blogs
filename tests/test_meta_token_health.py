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
