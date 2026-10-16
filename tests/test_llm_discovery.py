from content_generator.providers import nvidia


class _R:
    status_code = 200

    def json(self):
        return {"data": [{"id": i} for i in ("nvidia/nemotron-3.5-content-safety", "openai/gpt-oss-20b",
                                             "nvidia/nemotron-3-super-120b-a12b", "nvidia/llama-nemotron-embed-vl-1b-v2",
                                             "deepseek-ai/deepseek-v4.1-flash")]}


def test_nvidia_discovers_live_chat_models(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_DISCOVERY", "1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    monkeypatch.setattr(nvidia, "_DISCOVERED", None)
    monkeypatch.setattr(nvidia._http, "get", lambda *a, **k: _R())
    ms = nvidia.get_models()
    assert ms[0] == "nvidia/nemotron-3-super-120b-a12b"
    assert "deepseek-ai/deepseek-v4.1-flash" in ms and "openai/gpt-oss-20b" in ms
    assert not any("safety" in m or "embed" in m for m in ms)
