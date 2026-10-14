"""Tests for the Ollama provider and LLM router integration."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from content_generator.providers import ollama
from content_generator.providers import llm_router as router


class _Response:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


def test_ollama_disabled_via_env(monkeypatch):
    monkeypatch.setenv("ENABLE_OLLAMA", "false")
    assert not ollama.is_available()
    assert ollama.get_key() == ""
    assert ollama.health_check() == "skipped"


def test_ollama_ci_without_custom_url_is_skipped(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("ENABLE_OLLAMA", raising=False)
    assert not ollama.is_available()


def test_ollama_call_success(monkeypatch):
    monkeypatch.setenv("ENABLE_OLLAMA", "true")
    monkeypatch.setattr(ollama, "is_available", lambda: True)

    good_body = {
        "choices": [{"message": {"content": '{"hook": "Pure Coffee", "body": "pure Arabica"}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8},
    }

    def fake_post(*args, **kwargs):
        return _Response(200, good_body)

    monkeypatch.setattr(ollama._http, "post", fake_post)

    text, usage = ollama.call("Write a post.", 100)
    assert text == '{"hook": "Pure Coffee", "body": "pure Arabica"}'
    assert usage["prompt_tokens"] == 12
    assert usage["completion_tokens"] == 8


def test_ollama_call_http_error(monkeypatch):
    monkeypatch.setenv("ENABLE_OLLAMA", "true")
    monkeypatch.setattr(ollama, "is_available", lambda: True)

    def fake_post(*args, **kwargs):
        return _Response(500, text="Internal server error")

    monkeypatch.setattr(ollama._http, "post", fake_post)

    text, usage = ollama.call("Write a post.", 100)
    assert text is None
    assert usage["status_code"] == 500


def test_llm_router_prepends_ollama_when_available(monkeypatch):
    monkeypatch.setattr(ollama, "is_available", lambda: True)

    calls = []

    def fake_ollama_call(prompt, max_tokens):
        calls.append("ollama")
        return '{"hook": "Hello from Ollama"}', {"prompt_tokens": 5, "completion_tokens": 5}

    monkeypatch.setattr(ollama, "call", fake_ollama_call)

    data = router.call("Generate test", "test_label", max_tokens=50)
    assert data["hook"] == "Hello from Ollama"
    assert calls == ["ollama"]
