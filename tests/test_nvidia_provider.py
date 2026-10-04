"""NVIDIA NIM is the primary LLM. Fallbacks stay in the previous order."""
from __future__ import annotations

import logging

import pytest

from content_generator.providers import groq, nvidia
from content_generator.providers import llm_router as router


class _Response:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


def _ok_body(text: str = '{"ok": true}') -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4},
    }


@pytest.fixture
def _clean_router():
    router.reset_cascade_log()
    for state in router._STATES.values():
        state.record_success()
    yield
    router.reset_cascade_log()


def test_provider_order_starts_with_nvidia():
    names = [name for name, _fn in router._PROVIDERS]
    assert names[0] == "nvidia"
    assert names[1:] == ["groq", "gemini", "cerebras", "deepseek", "openrouter"]


def test_empty_model_env_keeps_the_default(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "   ")
    assert nvidia.get_model() == "meta/llama-3.3-70b-instruct"
    monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    assert nvidia.get_model() == "meta/llama-3.1-70b-instruct"


def test_success_uses_chat_completions(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        seen["model"] = json["model"]
        return _Response(200, _ok_body())

    monkeypatch.setattr(nvidia._http, "post", post)
    text, usage = nvidia.call("Write a caption.", 120)
    assert text == '{"ok": true}'
    assert usage["model"] == "meta/llama-3.3-70b-instruct"
    assert seen["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert seen["auth"] == "Bearer nvapi-secretvalue"
    assert seen["model"] == "meta/llama-3.3-70b-instruct"


def test_429_is_retried_then_reported(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    sleeps = []
    monkeypatch.setattr(nvidia.time, "sleep", lambda seconds: sleeps.append(seconds))
    calls = {"n": 0}

    def post(*_args, **_kwargs):
        calls["n"] += 1
        return _Response(429, text="slow down nvapi-secretvalue")

    monkeypatch.setattr(nvidia._http, "post", post)
    text, usage = nvidia.call("prompt", 40)
    assert text is None
    assert usage["status_code"] == 429
    assert calls["n"] == 4
    assert sleeps == [2, 5, 12]
    assert "nvapi-secretvalue" not in usage["error"]
    assert "***" in usage["error"]


def test_429_falls_back_to_groq(_clean_router, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkeyvalue")
    monkeypatch.setattr(nvidia.time, "sleep", lambda _seconds: None)
    seen = {"nvidia": 0, "groq": 0}

    def post(url, *_args, **_kwargs):
        if "api.nvidia.com" in url:
            seen["nvidia"] += 1
            return _Response(429, text="quota")
        seen["groq"] += 1
        return _Response(200, _ok_body('{"hook": "from groq"}'))

    monkeypatch.setattr(nvidia._http, "post", post)

    out = router.call("Write JSON.", "reel_1", max_tokens=40)
    assert out["hook"] == "from groq"
    assert seen["nvidia"] == 4
    assert seen["groq"] == 1


def test_missing_key_is_skipped(_clean_router, monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkeyvalue")

    def nvidia_post(*_args, **_kwargs):
        raise AssertionError("NVIDIA was called without a key")

    def groq_post(*_args, **_kwargs):
        return _Response(200, _ok_body('{"hook": "groq only"}'))

    monkeypatch.setattr(nvidia._http, "post", nvidia_post)
    monkeypatch.setattr(groq._http, "post", groq_post)

    text, usage = nvidia.call("prompt", 20)
    assert text is None
    assert usage == {}
    out = router.call("Write JSON.", "carousel", max_tokens=40)
    assert out["hook"] == "groq only"


def test_health_check_redacts_the_key(monkeypatch, caplog):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")

    def get(url, headers=None, timeout=None):
        assert url == "https://integrate.api.nvidia.com/v1/models"
        assert timeout == 15
        return _Response(401, text="rejected nvapi-secretvalue")

    monkeypatch.setattr(nvidia._http, "get", get)
    result = nvidia.health_check()
    assert result.startswith("HTTP 401")
    assert "nvapi-secretvalue" not in result

    caplog.set_level(logging.INFO)
    router.log_provider_status()
    assert "nvidia" in caplog.text
    assert "nvapi-secretvalue" not in caplog.text
    assert "NVIDIA health check:" in caplog.text


def test_health_check_skips_without_a_key(monkeypatch, caplog):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def get(*_args, **_kwargs):
        raise AssertionError("health check posted without a key")

    monkeypatch.setattr(nvidia._http, "get", get)
    assert nvidia.health_check() == "skipped"
    caplog.set_level(logging.INFO)
    router.log_provider_status()
    assert "skipped (no key)" in caplog.text
    assert "providers with keys present:" in caplog.text


def test_nvidia_only_satisfies_the_key_check(monkeypatch):
    from content_generator.scheduler.health_monitor import _check_api_keys

    for name in (
        "NVIDIA_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
        "CEREBRAS_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    report = _check_api_keys()
    assert report["status"] == "ok"
    assert report["present"] == ["NVIDIA"]
    assert "nvapi-secretvalue" not in str(report)
