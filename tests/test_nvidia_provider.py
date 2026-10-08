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
    assert nvidia.get_models() == [
        "google/gemma-4-31b-it",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b",
    ]
    assert nvidia.get_model() == "google/gemma-4-31b-it"
    assert "meta/llama-3.3-70b-instruct" not in nvidia.get_models()
    monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    assert nvidia.get_model() == "meta/llama-3.1-70b-instruct"
    assert nvidia.get_models() == ["meta/llama-3.1-70b-instruct"]
    monkeypatch.setenv("NVIDIA_MODEL", " first/model , second/model ")
    assert nvidia.get_models() == ["first/model", "second/model"]
    assert nvidia.get_model() == "first/model"


def test_success_uses_chat_completions(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        seen["model"] = json["model"]
        seen["timeout"] = timeout
        return _Response(200, _ok_body())

    monkeypatch.setattr(nvidia._http, "post", post)
    text, usage = nvidia.call("Write a caption.", 120)
    assert text == '{"ok": true}'
    assert usage["model"] == "google/gemma-4-31b-it"
    assert seen["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert seen["auth"] == "Bearer nvapi-secretvalue"
    assert seen["model"] == "google/gemma-4-31b-it"
    assert seen["timeout"] == nvidia._CALL_TIMEOUT_S
    assert nvidia._CALL_TIMEOUT_S <= 30


@pytest.mark.parametrize("status", [404, 410])
def test_unavailable_model_tries_the_next_configured_model(monkeypatch, caplog, status):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv(
        "NVIDIA_MODEL",
        "meta/llama-3.3-70b-instruct,nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it",
    )
    sleeps = []
    monkeypatch.setattr(nvidia.time, "sleep", lambda seconds: sleeps.append(seconds))
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(json["model"])
        if json["model"] == "meta/llama-3.3-70b-instruct":
            return _Response(status, text="model reached end of life on 2026-08-26 nvapi-secretvalue")
        if json["model"] == "nvidia/nemotron-3-super-120b-a12b":
            return _Response(status, text="model not found")
        return _Response(200, _ok_body('{"hook": "live"}'))

    monkeypatch.setattr(nvidia._http, "post", post)
    caplog.set_level(logging.WARNING)
    text, usage = nvidia.call("prompt", 40)
    assert text == '{"hook": "live"}'
    assert usage["model"] == "google/gemma-4-31b-it"
    assert seen == [
        "meta/llama-3.3-70b-instruct",
        "nvidia/nemotron-3-super-120b-a12b",
        "google/gemma-4-31b-it",
    ]
    assert sleeps == []
    assert f"HTTP {status}" in caplog.text
    assert "trying next configured model nvidia/nemotron-3-super-120b-a12b" in caplog.text
    assert "trying next configured model google/gemma-4-31b-it" in caplog.text
    assert "nvapi-secretvalue" not in caplog.text


def test_every_configured_model_unavailable_reports_the_last(monkeypatch, caplog):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "gone/one,gone/two")
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(json["model"])
        return _Response(410, text="end of life")

    monkeypatch.setattr(nvidia._http, "post", post)
    caplog.set_level(logging.WARNING)
    text, usage = nvidia.call("prompt", 40)
    assert text is None
    assert usage["status_code"] == 410
    assert usage["model"] == "gone/two"
    assert seen == ["gone/one", "gone/two"]
    assert "no further configured models" in caplog.text


def test_auth_failure_does_not_try_the_next_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "bad-model,good-model")
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(json["model"])
        return _Response(401, text="invalid key")

    monkeypatch.setattr(nvidia._http, "post", post)
    text, usage = nvidia.call("prompt", 40)
    assert text is None
    assert usage["status_code"] == 401
    assert usage["model"] == "bad-model"
    assert seen == ["bad-model"]


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


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_empty_content_tries_the_next_model(monkeypatch, caplog, content):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it")
    sleeps = []
    monkeypatch.setattr(nvidia.time, "sleep", lambda seconds: sleeps.append(seconds))
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        assert timeout == nvidia._CALL_TIMEOUT_S
        seen.append(json["model"])
        if json["model"] == "nvidia/nemotron-3-super-120b-a12b":
            return _Response(200, _ok_body(content))
        return _Response(200, _ok_body('{"hook": "from gemma"}'))

    monkeypatch.setattr(nvidia._http, "post", post)
    caplog.set_level(logging.WARNING)
    text, usage = nvidia.call("prompt", 40)
    assert text == '{"hook": "from gemma"}'
    assert usage["model"] == "google/gemma-4-31b-it"
    assert seen == ["nvidia/nemotron-3-super-120b-a12b", "google/gemma-4-31b-it"]
    assert sleeps == []
    assert "returned empty content" in caplog.text
    assert "trying next configured model google/gemma-4-31b-it" in caplog.text


def test_empty_content_on_every_model_falls_back_to_groq(_clean_router, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "empty/one,empty/two")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkeyvalue")
    monkeypatch.setattr(nvidia.time, "sleep", lambda _seconds: None)
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(url)
        if "api.nvidia.com" in url:
            assert timeout == nvidia._CALL_TIMEOUT_S
            return _Response(200, _ok_body("  "))
        return _Response(200, _ok_body('{"hook": "from groq"}'))

    monkeypatch.setattr(nvidia._http, "post", post)
    out = router.call("Write JSON.", "reel_1", max_tokens=40)
    assert out["hook"] == "from groq"
    assert sum("api.nvidia.com" in url for url in seen) == 2
    assert any("api.groq.com" in url for url in seen)


def test_timeout_tries_the_next_model(monkeypatch, caplog):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secretvalue")
    monkeypatch.setenv("NVIDIA_MODEL", "slow/model,google/gemma-4-31b-it")
    seen = []

    def post(url, headers=None, json=None, timeout=None):
        assert timeout == nvidia._CALL_TIMEOUT_S
        seen.append(json["model"])
        if json["model"] == "slow/model":
            raise TimeoutError("timed out")
        return _Response(200, _ok_body('{"hook": "after timeout"}'))

    monkeypatch.setattr(nvidia._http, "post", post)
    caplog.set_level(logging.WARNING)
    text, usage = nvidia.call("prompt", 40)
    assert text == '{"hook": "after timeout"}'
    assert usage["model"] == "google/gemma-4-31b-it"
    assert seen == ["slow/model", "google/gemma-4-31b-it"]
    assert "trying next configured model google/gemma-4-31b-it" in caplog.text


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
