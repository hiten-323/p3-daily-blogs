import os

from content_generator.core import blog_flags
from content_generator.publisher import shopify_blog


def test_blog_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    assert blog_flags.blog_enabled() is False
    assert shopify_blog.blog_enabled() is False


def test_blog_enabled_primary_flag(monkeypatch):
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    monkeypatch.setenv("BLOG_ENABLED", "false")
    assert blog_flags.blog_enabled() is False
    monkeypatch.setenv("BLOG_ENABLED", "true")
    assert blog_flags.blog_enabled() is True
    assert shopify_blog.blog_enabled() is True


def test_blog_enabled_legacy_alias(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.setenv("SHOPIFY_BLOG_ENABLED", "true")
    assert blog_flags.blog_enabled() is True
    monkeypatch.setenv("SHOPIFY_BLOG_ENABLED", "false")
    assert blog_flags.blog_enabled() is False


def test_blog_enabled_primary_overrides_legacy(monkeypatch):
    monkeypatch.setenv("BLOG_ENABLED", "false")
    monkeypatch.setenv("SHOPIFY_BLOG_ENABLED", "true")
    assert blog_flags.blog_enabled() is False


def test_disabled_blog_never_reaches_shopify_write(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "test-token")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Shopify admin API must not be called while blog publishing is disabled")

    monkeypatch.setattr(shopify_blog, "_admin", fail_if_called)
    result = shopify_blog.post_content({"blog_post": {"title": "x", "body_html": "y"}})
    assert result == {"success": False, "error": "blog_disabled"}
