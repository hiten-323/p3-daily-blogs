from __future__ import annotations

import pytest

from content_generator.providers import cerebras, deepseek, groq, openrouter


class _Response:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


_PROVIDER_CASES = [
    (groq, "GROQ_API_KEY"),
    (cerebras, "CEREBRAS_API_KEY"),
    (deepseek, "DEEPSEEK_API_KEY"),
    (openrouter, "OPENROUTER_API_KEY"),
]


@pytest.mark.parametrize("provider,env_name", _PROVIDER_CASES)
def test_model_specific_failure_falls_through(provider, env_name, monkeypatch):
    monkeypatch.setattr(provider, "MODELS", ["bad-model", "good-model"])
    monkeypatch.setenv(env_name, "test-key")

    good_body = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    responses = iter([
        _Response(404, text="model not found"),
        _Response(200, good_body),
    ])
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["json"]["model"])
        return next(responses)

    monkeypatch.setattr(provider._http, "post", post)

    text, usage = provider.call("prompt", 100)

    assert text == '{"ok": true}'
    assert usage["model"] == "good-model"
    assert calls == ["bad-model", "good-model"]


@pytest.mark.parametrize("provider,env_name", _PROVIDER_CASES)
def test_auth_failure_does_not_waste_calls_on_same_credential(provider, env_name, monkeypatch):
    monkeypatch.setattr(provider, "MODELS", ["bad-model", "good-model"])
    monkeypatch.setenv(env_name, "test-key")
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["json"]["model"])
        return _Response(401, text="invalid key")

    monkeypatch.setattr(provider._http, "post", post)

    text, usage = provider.call("prompt", 100)

    assert text is None
    assert usage["status_code"] == 401
    assert calls == ["bad-model"]


def test_groq_skips_an_oversized_prompt_without_posting(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testkeyvalue")
    monkeypatch.setattr(groq, "_TOKEN_LIMIT", 8000)
    posted = []

    def post(*_args, **_kwargs):
        posted.append(True)
        raise AssertionError("Groq was posted an oversized prompt")

    monkeypatch.setattr(groq._http, "post", post)
    text, usage = groq.call("x" * 40000, 1000)
    assert text is None
    assert usage["status_code"] == 413
    assert "exceeds 8000" in usage["error"]
    assert posted == []
