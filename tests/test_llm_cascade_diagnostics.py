"""The cascade must say why it failed and keep trying usable fallbacks."""
from __future__ import annotations

import pytest

from content_generator.providers import llm_router as router


@pytest.fixture(autouse=True)
def _clean_router():
    router.reset_cascade_log()
    for st in router._STATES.values():
        st.record_success()
    yield
    router.reset_cascade_log()


def _all_providers(text, usage):
    """Force every provider in the table to return the same outcome."""
    return [(name, lambda _p, _m, t=text, u=usage: (t, u)) for name, _ in router._PROVIDERS]


def test_auth_rejection_is_named(monkeypatch, caplog) -> None:
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(
        None, {"status_code": 401, "model": "llama-3.3-70b-versatile",
               "error": '{"error":"Invalid API Key"}'}))
    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            router.call("prompt", "carousel")

    rows = router.get_cascade_log()
    assert rows
    assert {r["category"] for r in rows} == {"auth_rejected"}
    assert "the key is present but invalid" in caplog.text
    assert "llama-3.3-70b-versatile" in caplog.text


def test_decommissioned_model_is_named(monkeypatch, caplog) -> None:
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(
        None, {"status_code": 400, "model": "mixtral-8x7b-32768",
               "error": '{"error":{"message":"model has been decommissioned"}}'}))
    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            router.call("prompt", "reel_1")

    assert "decommissioned or misspelled model id" in caplog.text
    assert "mixtral-8x7b-32768" in caplog.text


def test_missing_key_is_distinguished_from_a_rejection(monkeypatch, caplog) -> None:
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(None, {}))
    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            router.call("prompt", "carousel")

    assert "check keys are set and non-empty" in caplog.text
    assert {r["category"] for r in router.get_cascade_log()} == {"no_api_key_or_transport"}


def test_quota_is_distinguished(monkeypatch, caplog) -> None:
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(
        None, {"status_code": 429, "model": "gemini-2.0-flash", "error": "rate limit"}))
    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            router.call("prompt", "carousel")

    assert "quota exhausted" in caplog.text


def test_unparseable_provider_response_falls_through(monkeypatch, caplog) -> None:
    calls = []

    def first(_prompt, _max_tokens):
        calls.append("first")
        return "not json", {"model": "bad-model"}

    def second(_prompt, _max_tokens):
        calls.append("second")
        return '{"ok": true}', {"model": "good-model"}

    monkeypatch.setattr(router, "_PROVIDERS", [("groq", first), ("gemini", second)])

    def parse(raw):
        if raw == "not json":
            raise ValueError("not JSON")
        return {"ok": True}

    monkeypatch.setattr(router, "extract", parse)

    with caplog.at_level("ERROR"):
        out = router.call("prompt", "carousel")

    assert out == {"ok": True}
    assert calls == ["first", "second"]
    assert "continuing to next provider" in caplog.text
    assert any(r["category"] == "unparseable" for r in router.get_cascade_log())


def test_empty_parsed_response_falls_through(monkeypatch, caplog) -> None:
    calls = []

    def first(_prompt, _max_tokens):
        calls.append("first")
        return "{}", {"model": "empty-model"}

    def second(_prompt, _max_tokens):
        calls.append("second")
        return '{"ok": true}', {"model": "good-model"}

    monkeypatch.setattr(router, "_PROVIDERS", [("groq", first), ("gemini", second)])
    monkeypatch.setattr(router, "extract", lambda raw: {} if raw == "{}" else {"ok": True})

    with caplog.at_level("ERROR"):
        out = router.call("prompt", "carousel")

    assert out == {"ok": True}
    assert calls == ["first", "second"]
    assert "failure mode B" in caplog.text
    assert any(r["category"] == "parsed_empty" for r in router.get_cascade_log())


def test_no_credential_reaches_the_diagnostics(monkeypatch, caplog) -> None:
    leak = "gsk_liveSecretKeyValue123"
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(
        None, {"status_code": 401, "model": "m",
               "error": f'{{"error":"bad key Bearer {leak}"}}'}))
    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError):
            router.call("prompt", "carousel")

    assert leak not in caplog.text
    assert all(leak not in str(r) for r in router.get_cascade_log())


def test_every_attempt_records_the_fields_needed_to_act(monkeypatch) -> None:
    monkeypatch.setattr(router, "_PROVIDERS", _all_providers(
        None, {"status_code": 503, "model": "m", "error": "upstream"}))
    monkeypatch.setattr(router.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError):
        router.call("prompt", "carousel")

    for row in router.get_cascade_log():
        for field in ("provider", "model", "status", "attempts", "latency_s",
                      "category", "label"):
            assert field in row, f"cascade row missing {field}: {row}"


def test_an_answered_response_outranks_a_4xx_elsewhere(monkeypatch, caplog) -> None:
    """
    A provider that answered and produced junk is a different problem from one
    that never connected, and must be named first even when another provider in
    the same cascade returned a 4xx.

    On 2026-09-07 yt_short was reported as "a decommissioned model id" because
    cerebras 404'd, when the proximate failure was openrouter answering with
    reasoning prose instead of JSON. That sends the reader to the wrong fix.
    """
    router.reset_cascade_log()
    for st in router._STATES.values():
        st.record_success()

    def _providers():
        out = []
        for i, (name, _) in enumerate(router._PROVIDERS):
            if i == 0:                       # a dead model id
                out.append((name, lambda _p, _m: (None, {
                    "status_code": 404, "model": "zai-glm-4.7",
                    "error": "model_archived"})))
            else:                            # answers, but with prose
                out.append((name, lambda _p, _m: ("Let me analyze this request...", {})))
        return out

    monkeypatch.setattr(router, "_PROVIDERS", _providers())
    monkeypatch.setattr(router, "extract",
                        lambda raw: (_ for _ in ()).throw(ValueError("No JSON object found")))

    with caplog.at_level("ERROR"):
        try:
            router.call("prompt", "yt_short")
        except Exception:
            pass

    assert "the response was unusable" in caplog.text, (
        "verdict blamed a 4xx when a provider had actually answered"
    )
    assert "decommissioned" not in caplog.text.split("verdict:")[-1]
    router.reset_cascade_log()


def test_blank_200_is_not_ok_and_falls_through(monkeypatch) -> None:
    """Groq HTTP 200 with 0 chars must not be recorded as a successful answer."""
    calls = []

    def blank(_prompt, _max_tokens):
        calls.append("groq")
        return "", {"model": "openai/gpt-oss-120b"}

    def good(_prompt, _max_tokens):
        calls.append("gemini")
        return '{"ok": true}', {"model": "gemini-ok"}

    monkeypatch.setattr(router, "_PROVIDERS", [("groq", blank), ("gemini", good)])
    monkeypatch.setattr(router, "extract", lambda raw: {"ok": True})

    out = router.call("prompt", "yt_short")

    assert out == {"ok": True}
    assert calls == ["groq", "gemini"]
    groq_rows = [row for row in router.get_cascade_log() if row["provider"] == "groq"]
    assert groq_rows and groq_rows[0]["category"] == "empty_content"
    assert groq_rows[0]["detail"] == "empty content"
    assert not any(row["category"] == "ok" and "0 chars" in str(row.get("detail"))
                   for row in router.get_cascade_log())
