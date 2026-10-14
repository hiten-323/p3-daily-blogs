"""Day 286 follow-ups: from-scratch regen on banned claims, YT Short target,
natural blog copy, and fast provider failover."""
from __future__ import annotations

from content_generator.core import fallback_ladder as ladder
from content_generator.core.schema_validation import YoutubeShortSchema
from content_generator.core import blog_plan
from content_generator.providers import groq, nvidia


def test_banned_claim_feedback_triggers_scratch():
    fb = "brand: ['product truth: Wrong price: never claim Rs 18 / ₹18 a cup.']"
    assert ladder.is_banned_claim_failure(fb)
    assert not ladder.is_banned_claim_failure("Hook is weak; score 6.1")
    assert not ladder.is_banned_claim_failure("")


def test_scratch_prompt_drops_old_copy():
    piece = {"caption": "Only ₹18 a cup!", "frames": [{"on_screen": "₹18"}], "featured_product": "ultra_blend"}
    prompt = ladder.scratch_prompt("reel_1", piece, "brand: Wrong price ₹18", 8.0, "BRAND")
    assert "Only ₹18 a cup!" not in prompt
    assert '"caption"' in prompt and "BRAND-NEW" in prompt
    base = ladder.scratch_base(piece)
    assert base == {"featured_product": "ultra_blend"}


def test_pass_floor_unchanged():
    assert ladder.PASS_FLOOR == 8.0


def _short(**kw):
    data = {"hook": "A hook long enough", "script": "s" * 60, "cta": "Follow @purepantryprovisions"}
    data.update(kw)
    return data


def test_yt_short_prose_target_moves_to_audience():
    m = YoutubeShortSchema(**_short(target="Urban Indian coffee drinkers who rush their brew"))
    assert m.target is None
    assert m.audience.startswith("Urban Indian")


def test_yt_short_numeric_target_kept():
    assert YoutubeShortSchema(**_short(target="1,500")).target == 1500
    assert YoutubeShortSchema(**_short(target=20)).target == 20


def test_blog_sections_do_not_repeat_primary_keyword():
    topic = next(t for t in blog_plan.TOPICS if t["id"] == "choose-jar") if hasattr(blog_plan, "TOPICS") else None
    if topic is None:
        topic = {"id": "x", "primary": "instant coffee jar", "secondary": [], "title": "t", "slug": "s"}
    assert topic["primary"] != "purity beans jar"
    sections = " ".join(blog_plan.section_prose(topic, i) for i in range(6))
    assert sections.lower().count(topic["primary"].lower()) == 0
    heads = blog_plan.headings_for(topic)
    assert sum(topic["primary"] in h["heading"] for h in heads) == 1


def test_groq_compacts_long_prompt_under_limit():
    rules = "\n\n".join(f"Filler paragraph {i} " + "x" * 400 for i in range(80))
    prompt = "SYSTEM RULES:\nNever claim Rs 18 a cup.\n\n" + rules + "\n\nUSER REQUEST:\nWrite a section."
    out = groq.compact_prompt(prompt, 2000)
    assert out and len(out) <= 2000 * 4
    assert "Never claim Rs 18" in out and out.endswith("Write a section.")


def test_nvidia_skips_sick_model_and_fails_fast(monkeypatch):
    nvidia._reset_model_health()
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("NVIDIA_MODEL", "a/one,b/two")
    calls = []

    def fake(prompt, max_tokens, model, headers):
        calls.append(model)
        return None, {"status_code": 0, "model": model, "error": "Read timed out"}

    monkeypatch.setattr(nvidia, "_call_model", fake)
    for _ in range(nvidia._SICK_AFTER):
        assert nvidia.call("p", 10)[0] is None
    calls.clear()
    text, usage = nvidia.call("p", 10)
    assert text is None and calls == [] and "unhealthy" in usage["error"]
    nvidia._reset_model_health()


def test_new_free_providers_skip_without_keys(monkeypatch):
    from content_generator.providers import cloudflare, github_models, huggingface, mistral
    for var in ("GITHUB_MODELS_TOKEN", "MISTRAL_API_KEY", "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_ACCOUNT_ID", "HF_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    for mod in (cloudflare, github_models, huggingface, mistral):
        assert mod.call("p", 10) == (None, {})
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")  # account id still missing
    assert cloudflare.get_key() == ""


def test_free_provider_fails_over_on_empty(monkeypatch):
    from content_generator.providers import mistral, openai_compat

    class R:
        status_code = 200
        text = ""
        def __init__(self, c): self.c = c
        def json(self): return {"choices": [{"message": {"content": self.c}}]}

    seen = []

    def post(url, headers=None, json=None, timeout=None):
        seen.append(json["model"])
        return R("" if len(seen) == 1 else '{"ok": 1}')

    monkeypatch.setattr(openai_compat._http, "post", post)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    text, usage = mistral.call("p", 10)
    assert text == '{"ok": 1}' and len(seen) == 2


def test_openrouter_only_free_models():
    from content_generator.providers import openrouter
    assert openrouter.MODELS and all(m.endswith(":free") for m in openrouter.MODELS)
