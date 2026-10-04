"""
Provider model defaults must be usable models, not classifiers or routers.

2026-09-07 produced no content at all. Four providers were misconfigured in
three different ways, and only one was "the model is gone":

  groq        llama-3.3-70b-versatile / llama-3.1-8b-instant -> 404. Still listed
              PRODUCTION by Groq; the free-tier limit had become ContactSales, so
              the "or you do not have access to it" half of the error was the
              operative one.
  cerebras    zai-glm-4.7 -> 404 model_archived. gpt-oss-120b -> 402 payment
              required, which is an ACCOUNT state no model id can fix.
  gemini      gemini-3.8-flash -> 503 then 429. Current and not deprecated, but
              absent from the free-tier rate-limit table.
  openrouter  openrouter/free is an AUTO-ROUTER over the whole free pool, which
              contains nvidia/nemotron-3.5-content-safety. It answered yt_short
              with "User Safety: safe" (17 chars) and other labels with reasoning
              prose. Both parsed to nothing.

The last one is the trap worth guarding: a classifier returns a verdict, and a
verdict is a perfectly valid HTTP 200 that carries no content.
"""
from __future__ import annotations

import os

from content_generator.providers import cerebras, gemini, groq, nvidia, openrouter

# Substrings that mark a model as something other than a general text generator.
_NOT_A_GENERATOR = ("safeguard", "prompt-guard", "content-safety", "-guard-", "/guard")


def _all_defaults() -> list[tuple[str, str]]:
    out = [("gemini", gemini._MODEL)]
    out += [("nvidia", model) for model in nvidia._DEFAULT_MODELS]
    for name, mod in (("groq", groq), ("cerebras", cerebras), ("openrouter", openrouter)):
        out += [(name, m) for m in mod.MODELS]
    return out


def test_no_classifier_or_guard_model_is_configured() -> None:
    for provider, model in _all_defaults():
        low = model.lower()
        for bad in _NOT_A_GENERATOR:
            assert bad not in low, (
                f"{provider} default {model!r} looks like a classifier. Those return a "
                f"verdict with HTTP 200 — 'User Safety: safe' — which parses to nothing "
                f"and silently drops the day to fallback."
            )


def test_openrouter_does_not_use_the_auto_router() -> None:
    """
    openrouter/free routes across the entire free pool, including a content
    classifier and several reasoning models. Pin instruct models instead.
    """
    assert "openrouter/free" not in openrouter.MODELS, (
        "openrouter/free is an auto-router over a pool containing a content-safety "
        "classifier and reasoning models; it produced unusable output on 2026-09-07"
    )
    assert len(openrouter.MODELS) >= 2, "a single pinned model is a single point of failure"


def test_every_provider_has_a_usable_default() -> None:
    for provider, model in _all_defaults():
        assert model and model.strip() == model, (
            f"{provider} default {model!r} is empty or has stray whitespace — a split(',') "
            f"artefact reaches the API verbatim and 404s"
        )


def test_models_remain_env_overridable(monkeypatch) -> None:
    """
    Model ids drift faster than releases. Overriding must not need a code change —
    that is the whole reason these are getenv defaults.
    """
    import importlib

    monkeypatch.setenv("GROQ_MODELS", "some-new-model,another-one")
    reloaded = importlib.reload(groq)
    try:
        assert reloaded.MODELS == ["some-new-model", "another-one"]
    finally:
        monkeypatch.delenv("GROQ_MODELS", raising=False)
        importlib.reload(groq)
