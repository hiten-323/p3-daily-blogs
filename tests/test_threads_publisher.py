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
            "cta": "Explore 100% pure coffee at https://p3online.in"
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
