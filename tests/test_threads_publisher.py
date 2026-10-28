"""Unit tests for Meta Threads API publisher and text extraction."""
import json
import urllib.request
import pytest
from content_generator.publisher import threads
from content_generator.prompts import threads as threads_prompt


def test_threads_is_configured(monkeypatch):
    monkeypatch.delenv("THREADS_USER_ID", raising=False)
    monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
    assert threads.is_configured() is False

    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "TH_TOKEN_XYZ")
    assert threads.is_configured() is True


def test_threads_extract_text_direct_dict():
    content = {
        "threads_post": {
            "text": "Most instant coffee in India contains 40% chicory root. Purity Beans contains 0%. https://p3online.in #PurityBeans"
        }
    }
    extracted = threads._extract_thread_text(content)
    assert "40% chicory" in extracted
    assert "Purity Beans" in extracted
    assert len(extracted) <= 500


def test_threads_missing_native_copy_does_not_fallback_to_linkedin():
    content = {
        "linkedin_post": {
            "hook": "Why pouring 100°C water destroys your morning coffee.",
            "cta": "Explore pure coffee at https://p3online.in"
        }
    }
    extracted = threads._extract_thread_text(content)
    assert extracted == ""


def test_threads_extract_text_clips_long_text():
    long_text = "Coffee fact " + ("a" * 600)
    content = {"threads_post": {"text": long_text}}
    extracted = threads._extract_thread_text(content)
    assert len(extracted) <= 500


def test_threads_post_content_unconfigured(monkeypatch):
    monkeypatch.delenv("THREADS_USER_ID", raising=False)
    monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
    res = threads.post_content({"threads_post": {"text": "hello"}}, day=1)
    assert res["success"] is False
    assert res["attempted"] is False
    assert res["skipped"] is True
    assert res["error"] == "not_configured"


def test_threads_prompt_builder():
    prompt = threads_prompt.build(("CHICORY TRUTH", "40% filler in commercial coffee"), avoid="AVOID", day=5)
    assert "UNDER 480 CHARACTERS" in prompt
    assert "Purity Beans" in prompt
    assert "https://p3online.in" in prompt


def test_threads_post_success_mock(monkeypatch):
    monkeypatch.setenv("THREADS_USER_ID", "th_user_999")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "th_tok_123")

    calls = []

    def mock_post_request(url, params):
        calls.append((url, params))
        if "threads_publish" in url:
            return {"id": "post_777888"}
        return {"id": "container_111222"}

    monkeypatch.setattr(threads, "_post_request", mock_post_request)
    monkeypatch.setattr(threads, "is_configured", lambda: True)
    monkeypatch.setattr("content_generator.publisher.prepublish_gate.authorize_publish", lambda content, platform: {"allowed": True, "reason": "test-approved"})

    content = {"threads_post": {"text": "Test thread post for Purity Beans! https://p3online.in"}}
    res = threads.post_content(content, day=1)

    assert res["success"] is True
    assert res["post_id"] == "post_777888"
    assert "post/post_777888" in res["url"]
    assert len(calls) == 2


def test_media_id_to_shortcode():
    # 17901169176377692 should convert to canonical base64 shortcode
    sc = threads._media_id_to_shortcode("17901169176377692")
    assert sc == "_mQS90nlc"
    assert threads._media_id_to_shortcode("invalid_non_numeric") == ""


def test_threads_checkpoint_returns_failure_without_raising(monkeypatch):
    import io
    import urllib.error

    monkeypatch.setenv("THREADS_USER_ID", "th_user_999")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "th_tok_123")
    monkeypatch.setattr(
        "content_generator.publisher.prepublish_gate.authorize_publish",
        lambda content, platform: {"allowed": True, "reason": "test-approved"},
    )
    body = (
        b'{"error":{"message":"This Threads account needs to complete a checkpoint '
        b'before it can access this app.","type":"OAuthException","code":190}}'
    )

    def urlopen(req, timeout=25):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(body))

    monkeypatch.setattr(threads.urllib.request, "urlopen", urlopen)
    res = threads.post_content({"threads_post": {"text": "Purity Beans checkpoint"}}, day=3)
    assert res["success"] is False
    assert res["attempted"] is True
    assert res["skipped"] is False
    assert "401" in res["error"]
    assert "checkpoint" in res["error"].lower()


def test_threads_exception_does_not_drop_other_platforms(monkeypatch, tmp_path):
    from content_generator.publisher import dispatcher
    from content_generator.publisher import publishing_ledger as ledger

    monkeypatch.setenv("ENABLE_TIMED_SLOTS", "true")
    monkeypatch.setenv("BLOG_ENABLED", "false")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "th_tok_123")
    monkeypatch.setenv("THREADS_USER_ID", "th_user_999")
    monkeypatch.setattr(dispatcher, "_PUBLISH_LOG", str(tmp_path / "publish_log.json"))
    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(
        "content_generator.publisher.platform_verification.verify_remote_post",
        lambda platform, record: {"state": "unknown", "method": "test", "detail": "skipped"},
    )
    monkeypatch.setattr(
        "content_generator.core.editorial_engine.approved_assets",
        lambda content: {"linkedin_post": content.get("linkedin_post") or {}},
    )
    monkeypatch.setattr(
        "content_generator.publisher.linkedin.post_content",
        lambda content, day=0: {"success": True, "post_id": "li-1", "url": "https://linkedin.example/li-1"},
    )

    def boom(content, day=0):
        raise RuntimeError("Threads checkpoint crashed the publisher")

    monkeypatch.setattr("content_generator.publisher.threads.post_content", boom)
    result = dispatcher.publish_all(
        {"linkedin_post": {"text": "label check"}, "threads_post": {"text": "hot take"}},
        day_number=4,
    )
    assert result["linkedin"]["success"] is True
    assert result["threads"]["success"] is False
    assert "checkpoint" in result["threads"]["error"]
    assert "instagram" in result
    assert "facebook" in result


def test_threads_numeric_id_uses_shortcode_url(monkeypatch):
    monkeypatch.setenv("THREADS_USER_ID", "th_user_999")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "th_tok_123")

    def mock_post_request(url, params):
        if "threads_publish" in url:
            return {"id": "17901169176377692"}
        return {"id": "container_111222"}

    monkeypatch.setattr(threads, "_post_request", mock_post_request)
    monkeypatch.setattr(threads, "is_configured", lambda: True)
    monkeypatch.setattr("content_generator.publisher.prepublish_gate.authorize_publish", lambda content, platform: {"allowed": True, "reason": "test-approved"})
    monkeypatch.setattr(threads, "get_thread_permalink", lambda post_id, token: "")

    content = {"threads_post": {"text": "Test numeric thread post"}}
    res = threads.post_content(content, day=1)

    assert res["success"] is True
    assert res["post_id"] == "17901169176377692"
    assert res["url"] == "https://www.threads.net/t/_mQS90nlc"

