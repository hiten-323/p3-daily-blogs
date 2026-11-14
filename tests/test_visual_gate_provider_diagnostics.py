"""Vision fallback diagnostics never hide missing keys or provider/credit failures."""

from content_generator.creative import visual_gate as vg


def test_huggingface_vision_fallback_uses_existing_hf_token(monkeypatch):
    seen = {}
    monkeypatch.setenv("HF_TOKEN", "test-token-never-log")
    monkeypatch.setenv("HF_VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
    monkeypatch.setattr(vg, "_openai_vision",
                        lambda url, key, model, b64, extra=None:
                        seen.update(url=url, key=key, model=model, b64=b64) or (8.4, []))
    result = vg._huggingface("encoded-image")
    assert result == (8.4, [])
    assert seen["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert seen["model"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert seen["key"] == "test-token-never-log"


def test_all_vision_provider_failures_are_named_and_reported(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    monkeypatch.setenv("GROQ_API_KEY", "present")
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "present")
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    monkeypatch.setenv("HF_TOKEN", "present")
    monkeypatch.setenv("NVIDIA_API_KEY", "present")
    monkeypatch.setattr(vg, "_jpeg_b64", lambda path: "image")
    monkeypatch.setattr(vg, "_dead", lambda key: False)
    monkeypatch.setattr(vg, "_mark", lambda *args: None)
    monkeypatch.setattr(vg, "_OUTAGE", {"n": 0})

    def fail(_):
        raise RuntimeError("HTTP 402 insufficient credits")

    monkeypatch.setattr(vg, "VISION_PROVIDERS", [
        ("gemini", fail), ("groq", fail), ("huggingface", fail),
    ])
    result = vg.aesthetic_score("story.jpg")
    assert result["score"] is None
    assert any("gemini:HTTP 402" in err for err in result["errors"])
    assert any("groq:HTTP 402" in err for err in result["errors"])
    assert any("huggingface:HTTP 402" in err for err in result["errors"])
    assert "all providers down" in caplog.text.lower()
    assert "test-token-never-log" not in caplog.text


def test_missing_vision_credentials_are_explicitly_reported(monkeypatch, caplog):
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_MODELS_TOKEN",
                 "OPENROUTER_API_KEY", "HF_TOKEN", "NVIDIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(vg, "_jpeg_b64", lambda path: "image")
    monkeypatch.setattr(vg, "_OUTAGE", {"n": 0})
    monkeypatch.setattr(vg, "VISION_PROVIDERS", [("huggingface", lambda _: None)])
    result = vg.aesthetic_score("story.jpg")
    assert result["score"] is None
    assert result["errors"] == ["huggingface:missing_credentials"]
    assert "provider=huggingface unavailable: missing credentials" in caplog.text
