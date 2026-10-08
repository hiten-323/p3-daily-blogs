"""Shopify blog publishes once, from the generate slot, after every gate."""
from __future__ import annotations

import datetime
import logging
from pathlib import Path

from content_generator.core.blog_writer import generate_blog_post
from content_generator.publisher import dispatcher, shopify_blog

ROOT = Path(__file__).resolve().parents[1]
_FIXED_DAY = datetime.date(2026, 10, 4)


def _long_body() -> str:
    return " ".join(["Purity Beans lists the catalog jar for this section in India."] * 30)


def _llm(counter):
    def llm(prompt, label="", max_tokens=900):
        counter["n"] += 1
        if "outline" in str(label):
            return {"sections": []}
        if counter["n"] < 3:
            return {"body": "Too short."}
        return {"body": _long_body()}
    return llm


def _ready_post(tmp_path) -> dict:
    piece = generate_blog_post(
        6,
        llm_call=_llm({"n": 0}),
        output_dir=str(tmp_path),
        on_date="2026-10-04",
    )
    piece["editorial_score"] = {
        "overall": 8.6,
        "verdict": "PASS",
        "shareability": 8.6,
        "saveability": 8.6,
        "emotion_pull": 8.6,
        "hook_strength": 8.6,
        "brand_clarity": 8.6,
        "feedback": "Measured review.",
    }
    return {"blog_post": piece, "day_number": 6}


def _isolate(monkeypatch, tmp_path, slot=None):
    """Keep publish checks off committed output/, the runner date, and FORCE_SLOT."""
    monkeypatch.setenv("PB_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "content_generator.core.blog_quality.content_output_dir",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "content_generator.core.ist_dates.today_ist",
        lambda now=None: _FIXED_DAY,
    )
    if slot is None:
        monkeypatch.delenv("FORCE_SLOT", raising=False)
    else:
        monkeypatch.setenv("FORCE_SLOT", slot)


def _enable(monkeypatch, tmp_path, slot=None):
    _isolate(monkeypatch, tmp_path, slot=slot)
    monkeypatch.setenv("SHOPIFY_BLOG_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "purity-beans.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("SHOPIFY_BLOG_ID", "991")
    monkeypatch.setenv("BLOG_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("WEBSITE_URL", "https://p3online.in")
    monkeypatch.setattr(shopify_blog, "_hero_image_b64", lambda: None)


def test_workflow_enables_shopify_blog_on_the_pipeline():
    text = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert 'SHOPIFY_BLOG_ENABLED: "true"' in text
    assert "SHOPIFY_STORE_DOMAIN:" in text
    assert "SHOPIFY_ADMIN_TOKEN:" in text
    assert "SHOPIFY_BLOG_ID:" in text


def test_publish_logs_the_article_url(monkeypatch, tmp_path, caplog):
    _enable(monkeypatch, tmp_path)
    content = _ready_post(tmp_path)
    posts = []

    def admin(path, method="GET", body=None):
        if method == "POST":
            posts.append(body)
            return {"article": {"id": 42, "handle": content["blog_post"]["slug"]}}
        return {"articles": []}

    monkeypatch.setattr(shopify_blog, "_admin", admin)
    caplog.set_level(logging.INFO)
    result = shopify_blog.post_content(content, day=6)
    url = f"https://p3online.in/blogs/news/{content['blog_post']['slug']}"
    assert result["success"] is True
    assert result["attempted"] is True
    assert result["url"] == url
    assert posts and posts[0]["article"]["handle"] == content["blog_post"]["slug"]
    assert f"Published article URL: {url}" in caplog.text


def test_duplicate_handle_or_title_is_not_attempted(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    content = _ready_post(tmp_path)
    title = content["blog_post"]["title"]

    def handle_taken(path, method="GET", body=None):
        assert method != "POST"
        if "handle=" in path:
            return {"articles": [{"id": 7, "title": "Other", "handle": content["blog_post"]["slug"]}]}
        return {"articles": []}

    monkeypatch.setattr(shopify_blog, "_admin", handle_taken)
    handle_result = shopify_blog.post_content(content, day=6)
    assert handle_result["attempted"] is False
    assert handle_result["error"] == "not_attempted"
    assert handle_result["reason"] == "duplicate_handle"

    def title_taken(path, method="GET", body=None):
        assert method != "POST"
        if "handle=" in path:
            return {"articles": []}
        return {"articles": [{"id": 8, "title": title, "handle": "cowork-handle"}]}

    monkeypatch.setattr(shopify_blog, "_admin", title_taken)
    title_result = shopify_blog.post_content(content, day=6)
    assert title_result["attempted"] is False
    assert title_result["reason"] == "duplicate_title"


def test_missing_secrets_and_shopify_errors_skip(monkeypatch, tmp_path, caplog):
    _isolate(monkeypatch, tmp_path, slot="generate")
    content = _ready_post(tmp_path)
    monkeypatch.setenv("SHOPIFY_BLOG_ENABLED", "true")
    monkeypatch.setenv("BLOG_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("SHOPIFY_STORE_DOMAIN", raising=False)
    monkeypatch.delenv("SHOPIFY_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_BLOG_ID", raising=False)

    def boom(*args, **kwargs):
        raise AssertionError("Shopify must not be called when secrets are missing")

    monkeypatch.setattr(shopify_blog, "_admin", boom)
    caplog.set_level(logging.WARNING)
    missing = shopify_blog.post_content(content, day=6)
    assert missing["attempted"] is False
    assert missing["reason"] == "missing_secrets"
    assert "Missing Shopify secrets" in caplog.text

    _enable(monkeypatch, tmp_path)

    def post_fails(path, method="GET", body=None):
        if method == "POST":
            return None
        return {"articles": []}

    monkeypatch.setattr(shopify_blog, "_admin", post_fails)
    failed = shopify_blog.post_content(content, day=6)
    assert failed["success"] is False
    assert failed["attempted"] is False
    assert failed["reason"] == "shopify_error"
    assert "skipping publish without failing the run" in caplog.text


def test_unapproved_or_wrong_slot_does_not_call_shopify(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    content = _ready_post(tmp_path)
    content["blog_post"].pop("editorial_score")

    def boom(*args, **kwargs):
        raise AssertionError("Shopify must not be called")

    monkeypatch.setattr(shopify_blog, "_admin", boom)
    skipped = shopify_blog.post_content(content, day=6)
    assert skipped["reason"] == "not_editor_approved"

    content = _ready_post(tmp_path)
    content["blog_post"]["body"] = "Too short."
    monkeypatch.setenv("FORCE_SLOT", "morning")
    slot = shopify_blog.post_content(content, day=6)
    assert slot["reason"] == "wrong_slot"


def test_second_publish_the_same_day_is_not_attempted(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    content = _ready_post(tmp_path)
    posts = {"n": 0}

    def admin(path, method="GET", body=None):
        if method == "POST":
            posts["n"] += 1
            return {"article": {"id": 42, "handle": content["blog_post"]["slug"]}}
        return {"articles": []}

    monkeypatch.setattr(shopify_blog, "_admin", admin)
    first = shopify_blog.post_content(content, day=6)
    second = shopify_blog.post_content(content, day=6)
    assert first["success"] is True
    assert second["attempted"] is False
    assert second["reason"] == "already_published_today"
    assert posts["n"] == 1


def test_dispatcher_does_not_fail_the_run_for_a_blog_skip(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, slot="generate")
    monkeypatch.setenv("ENABLE_TIMED_SLOTS", "true")
    monkeypatch.setattr(dispatcher, "_PUBLISH_LOG", str(tmp_path / "publish_log.json"))
    monkeypatch.setattr(
        "content_generator.core.editorial_engine.approved_assets",
        lambda content: {},
    )
    result = dispatcher.publish_all(
        {"blog_post": {"title": "Held draft", "body": "Short.", "hold_reason": "provider_failure during s1"}},
        day_number=6,
    )
    assert result["blog"]["attempted"] is False
    assert result["blog"]["error"] == "not_attempted"
    assert "Blog" not in (result["summary"].split("Failed: ")[-1] if "Failed:" in result["summary"] else "")
    assert "Blog" in result["summary"]


def test_shopify_domain_is_a_host_and_the_token_is_not_logged(monkeypatch, caplog):
    from content_generator.analytics import revenue_attribution as revenue

    raw = "https://User:shpat_secretvalue@Purity-Beans.myshopify.com:443/admin/api?x=1"
    assert revenue.normalize_shopify_domain(raw) == "purity-beans.myshopify.com"
    assert revenue.normalize_shopify_domain("https://shop.myshopify.com/admin/") == "shop.myshopify.com"
    assert revenue.normalize_shopify_domain("shop.myshopify.com/") == "shop.myshopify.com"

    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", raw)
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "shpat_secretvalue")
    caplog.set_level(logging.INFO)
    assert revenue.shopify_store_host() == "purity-beans.myshopify.com"
    assert "[shopify] store host: purity-beans.myshopify.com" in caplog.text
    assert "shpat_secretvalue" not in caplog.text
    assert "https://" not in caplog.text

    seen = {}

    class _Resp:
        def read(self):
            return b'{"orders": []}'

    def urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["token"] = req.get_header("X-shopify-access-token")
        return _Resp()

    monkeypatch.setattr(revenue.urllib.request, "urlopen", urlopen)
    assert revenue._shopify_get("orders.json", {"limit": "1"}) == {"orders": []}
    assert seen["url"].startswith("https://purity-beans.myshopify.com/admin/api/")
    assert "https://https://" not in seen["url"]
    assert "/admin/admin" not in seen["url"]
    assert seen["token"] == "shpat_secretvalue"
