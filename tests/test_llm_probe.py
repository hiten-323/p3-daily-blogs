"""Dry-run probe tests: fallback and aggregate health must be reliable."""
from content_generator.providers import llm_probe


def test_nvidia_probe_uses_fallback_after_empty_content(monkeypatch):
    monkeypatch.setattr(llm_probe.nvidia, "get_key", lambda: "nvapi-test")
    monkeypatch.setattr(
        llm_probe.nvidia,
        "get_models",
        lambda: ["nvidia/old-model", "nvidia/nemotron-3.5-lightning-30b-a3b"],
    )
    seen = []

    def fake_chat(url, key, model, extra_headers=None, *, reject_empty=False):
        seen.append((model, reject_empty))
        return "empty content" if model == "nvidia/old-model" else "OK"

    monkeypatch.setattr(llm_probe, "_openai_chat", fake_chat)

    assert llm_probe._nvidia_chat() == "OK"
    assert seen == [
        ("nvidia/old-model", True),
        ("nvidia/nemotron-3.5-lightning-30b-a3b", True),
    ]


def test_nvidia_probe_reports_empty_only_when_every_model_is_empty(monkeypatch):
    monkeypatch.setattr(llm_probe.nvidia, "get_key", lambda: "nvapi-test")
    monkeypatch.setattr(llm_probe.nvidia, "get_models", lambda: ["model-a", "model-b"])
    monkeypatch.setattr(
        llm_probe,
        "_openai_chat",
        lambda *args, **kwargs: "empty content",
    )

    assert llm_probe._nvidia_chat() == "empty content"


def test_nvidia_probe_skips_without_key(monkeypatch):
    monkeypatch.setattr(llm_probe.nvidia, "get_key", lambda: "")
    assert llm_probe._nvidia_chat() == "skipped"


def test_main_succeeds_when_fallback_provider_is_healthy(monkeypatch):
    monkeypatch.setattr(llm_probe, "_KEY_GETTERS", [])
    monkeypatch.setattr(
        llm_probe,
        "probe_results",
        lambda: [("nvidia", "all NVIDIA models failed; model-a: HTTP 410"), ("groq", "OK")],
    )

    assert llm_probe.main() == 0


def test_main_fails_when_no_provider_is_healthy(monkeypatch):
    monkeypatch.setattr(llm_probe, "_KEY_GETTERS", [])
    monkeypatch.setattr(
        llm_probe,
        "probe_results",
        lambda: [("nvidia", "all NVIDIA models failed; model-a: HTTP 410"), ("groq", "skipped")],
    )

    assert llm_probe.main() == 1


def test_main_fails_when_every_provider_is_skipped(monkeypatch):
    monkeypatch.setattr(llm_probe, "_KEY_GETTERS", [])
    monkeypatch.setattr(
        llm_probe,
        "probe_results",
        lambda: [("nvidia", "skipped"), ("groq", "skipped")],
    )

    assert llm_probe.main() == 1
