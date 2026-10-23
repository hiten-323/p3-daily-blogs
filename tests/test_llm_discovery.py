from content_generator.providers import nvidia


def _discover(monkeypatch, catalog):
    class _Resp:
        status_code = 200

        def json(self):
            return {"data": [{"id": i} for i in catalog]}

    monkeypatch.setenv("LLM_MODEL_DISCOVERY", "1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    monkeypatch.setattr(nvidia, "_DISCOVERED", None)
    monkeypatch.setattr(nvidia._http, "get", lambda *a, **k: _Resp())
    return nvidia.get_models()


def test_nvidia_discovers_live_chat_models(monkeypatch):
    ms = _discover(monkeypatch, (
        "nvidia/nemotron-3.5-content-safety", "openai/gpt-oss-20b",
        "nvidia/nemotron-3-super-120b-a12b", "nvidia/llama-nemotron-embed-vl-1b-v2",
        "deepseek-ai/deepseek-v4.1-flash", "moonshotai/kimi-k2.6",
        "openai/gpt-oss-120b",
    ))
    assert ms[0] == "nvidia/nemotron-3-super-120b-a12b"
    assert "deepseek-ai/deepseek-v4.1-flash" in ms and "openai/gpt-oss-20b" in ms
    assert "moonshotai/kimi-k2.6" not in ms
    assert "openai/gpt-oss-120b" not in ms
    assert not any("safety" in m or "embed" in m for m in ms)
    assert len(ms) >= 2


def test_discovery_backup_chain_uses_catalog_models_not_kimi(monkeypatch):
    """GET /v1/models on 2026-10-23 still lists kimi-k2.6; chat/completions 404s it.
    The try-order must stay a chain of models that are actually on that catalog."""
    ms = _discover(monkeypatch, (
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "google/gemma-4-31b-it",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b",
        "deepseek-ai/deepseek-v4.1-flash",
        "moonshotai/kimi-k2.6",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "z-ai/glm-5.3-flash",
        "minimaxai/minimax-m3.1-flash",
        "nvidia/nemotron-nano-3-30b-a3b",
        "nvidia/llama-3.1-nemotron-70b-instruct",
        "nvidia/nemotron-3.5-content-safety",
        "qwen/qwen3-235b",
        "meta/llama-4-maverick",
    ))
    assert ms == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "google/gemma-4-31b-it",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b",
        "deepseek-ai/deepseek-v4.1-flash",
        "openai/gpt-oss-20b",
    ]
    assert all(model not in nvidia._REMOVED for model in ms)
    assert len(ms) >= 2
