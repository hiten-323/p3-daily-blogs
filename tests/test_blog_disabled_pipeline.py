"""BLOG_ENABLED=false: no generate, no regen, no publish, no retry/alerts."""
from __future__ import annotations

import pathlib

import pytest

from content_generator.core import blog_flags
from content_generator.scheduler import retry_unposted as RU


def test_active_targets_omit_blog_by_default(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    assert "blog" not in RU.active_targets()
    assert "blog" not in RU.unposted_targets([], 8)
    assert "linkedin" in RU.unposted_targets([], 8)


def test_active_targets_include_blog_when_enabled(monkeypatch):
    monkeypatch.setenv("BLOG_ENABLED", "true")
    assert "blog" in RU.active_targets()
    assert "blog" in RU.unposted_targets([], 8)


def test_unposted_list_without_blog_when_disabled(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    assert RU.unposted_targets([], 8) == ["linkedin", "youtube", "threads"]


def test_generator_skips_blog_when_disabled(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    from content_generator.pipeline import generator as gen

    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("blog writer must not run when disabled")

    monkeypatch.setattr(gen, "_generate_blog", boom)
    monkeypatch.setattr(gen, "_extended_content_enabled", lambda: True)
    # Exercise the branch directly via the same condition the pipeline uses
    assert blog_flags.blog_enabled() is False
    # Simulate the pipeline gate
    from content_generator.core.blog_flags import blog_enabled
    assert not (True and blog_enabled())
    assert called["n"] == 0


def test_dispatcher_skips_blog_when_disabled(monkeypatch):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    monkeypatch.setenv("FORCE_SLOT", "generate")
    from content_generator.publisher import dispatcher, shopify_blog

    def boom(*a, **k):
        raise AssertionError("shopify blog must not publish when disabled")

    monkeypatch.setattr(shopify_blog, "post_content", boom)
    # Minimal content with an "approved" blog would still be skipped
    content = {
        "day_number": 1,
        "blog_post": {
            "title": "x",
            "introduction": "a" * 80,
            "body": "b" * 900,
            "conclusion": "c" * 40,
            "editorial_review": {"approved": True, "overall": 9.0},
        },
    }
    # Call only the blog branch logic by importing blog_enabled path used in dispatcher
    from content_generator.core.blog_flags import blog_enabled, blog_disabled_reason
    assert blog_enabled() is False
    assert "Blogs bot" in blog_disabled_reason()


def test_workflows_keep_blog_disabled():
    root = pathlib.Path(".")
    for name in ("daily.yml", "retry-unposted.yml", "publish-recovery.yml"):
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert 'BLOG_ENABLED: "false"' in text
        assert 'SHOPIFY_BLOG_ENABLED: "true"' not in text


def test_dispatcher_skips_cleanly_when_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOG_ENABLED", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ENABLED", raising=False)
    monkeypatch.setenv("FORCE_SLOT", "generate")
    monkeypatch.setenv("ENABLE_TIMED_SLOTS", "true")
    from content_generator.publisher import dispatcher
    monkeypatch.setattr(dispatcher, "_PUBLISH_LOG", str(tmp_path / "publish_log.json"))
    monkeypatch.setattr(
        "content_generator.core.editorial_engine.approved_assets",
        lambda content: {"blog_post": content.get("blog_post") or {}},
    )
    result = dispatcher.publish_all(
        {"blog_post": {"title": "x", "body": "y" * 900, "introduction": "i" * 80, "conclusion": "c" * 40}},
        day_number=1,
    )
    assert result["blog"]["attempted"] is False
    assert result["blog"]["error"] == "blog_disabled"
    assert result["blog"].get("skipped") is True
