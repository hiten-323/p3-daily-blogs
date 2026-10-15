import pytest

from content_generator.publisher.blog_safety import assert_blog_disabled


def test_blog_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="Blogs bot"):
        assert_blog_disabled()


def test_blog_requires_explicit_enable(monkeypatch):
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    monkeypatch.setenv("BLOG_ENABLED", "false")
    with pytest.raises(RuntimeError):
        assert_blog_disabled()

    monkeypatch.setenv("BLOG_ENABLED", "true")
    assert_blog_disabled()
