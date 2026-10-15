import json

import pytest

from content_generator.core import draft_purge
from content_generator.providers import provider_budget, llm_router


@pytest.fixture(autouse=True)
def _usage_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_USAGE_DIR", str(tmp_path))
    provider_budget.reset_for_tests()
    for st in llm_router._STATES.values():
        st.record_success()
    yield
    provider_budget.reset_for_tests()


def _reel(text):
    return {"id": "r", "featured_product": "Purista", "objective": "follow", "caption": text,
            "frames": [{"on_screen": text, "spoken": "hi"}] * 5}


def test_rs18_draft_is_discarded_not_kept():
    content = {"reels": [_reel("Lovely pure coffee at home"), _reel("Brew at home for Rs 18 per cup")],
               "video_prompts": {"reel_2": {"on_screen_text": "RS 18 PER CUP"}}}
    purged = draft_purge.purge_banned_drafts(content)
    assert "reel_2" in purged and "video_prompts.reel_2" in purged
    r2 = content["reels"][1]
    assert r2["needs_regen"] and r2["held"] and "caption" not in r2 and "frames" not in r2
    assert "caption" in r2["_shape"] and "frames" in r2["_shape"]
    assert not draft_purge._RS18.search(json.dumps(content, ensure_ascii=False))
    assert content["reels"][0]["caption"] == "Lovely pure coffee at home"


def test_save_content_never_persists_banned_draft(tmp_path):
    from content_generator.pipeline.generator import save_content
    path = save_content({"date": "2026-10-15", "threads_post": {"text": "Cafe ₹180 vs ₹18 at home"}},
                        output_dir=str(tmp_path))
    saved = open(path, encoding="utf-8").read()
    assert "₹18" not in saved and "needs_regen" in saved


def test_needs_regen_piece_uses_original_shape_in_scratch_prompt():
    from content_generator.core.fallback_ladder import scratch_prompt
    piece = draft_purge.purged_piece(_reel("Rs 18 a cup"), ["Wrong price"])
    prompt = scratch_prompt("reel_2", piece, "brand: wrong price", 8.0, "BRAND")
    assert '"frames"' in prompt and "needs_regen" not in prompt.split("Return ONE")[1]


@pytest.mark.parametrize("label,route", [
    ("fresh_reel_2", "ig_reel"), ("editorial_growth_reel", "ig_reel"), ("stories", "stories"),
    ("carousel_mech", "ig_post"), ("linkedin_angle", "linkedin"), ("threads_angle", "threads"),
    ("facebook_angle", "facebook"), ("editorial_yt_short", "yt_short"), ("blog_section_s0", "blog"),
])
def test_label_routes(label, route):
    assert provider_budget.platform_for_label(label) == route


BASE = ["gemini", "groq", "cerebras", "openrouter", "github_models",
        "mistral", "cloudflare", "huggingface", "deepseek", "nvidia"]


def test_each_platform_starts_on_its_own_provider():
    assert provider_budget.order_for("reel_1", BASE)[0] == "groq"
    assert provider_budget.order_for("stories", BASE)[0] == "gemini"
    assert provider_budget.order_for("carousel", BASE)[0] == "cerebras"
    assert provider_budget.order_for("linkedin_post", BASE)[0] == "github_models"
    assert provider_budget.order_for("threads_post", BASE)[0] == "openrouter"
    assert provider_budget.order_for("facebook_post", BASE)[0] == "mistral"
    for label in ("reel_1", "blog_post", "yt_short"):
        assert sorted(provider_budget.order_for(label, BASE)) == sorted(BASE)  # full chain kept


def test_429_rotates_this_and_later_pieces_and_persists(tmp_path):
    provider_budget.record("groq", ok=False, status=429, usage={"status_code": 429})
    order = provider_budget.order_for("reel_2", BASE)
    assert order[0] != "groq" and order[-1] == "groq"
    assert provider_budget.order_for("growth_reel", BASE)[0] != "groq"
    state = json.loads(next(tmp_path.glob("provider_usage_*.json")).read_text())
    assert state["providers"]["groq"]["429s"] == 1


def test_over_80_percent_quota_rotates():
    for _ in range(41):  # openrouter free quota 50/day in config
        provider_budget.record("openrouter", ok=True, usage={"prompt_tokens": 1, "completion_tokens": 1},
                               label="threads_post")
    assert provider_budget.order_for("threads_post", BASE)[0] != "openrouter"


def test_remaining_quota_header_rotates():
    provider_budget.record("cerebras", ok=True, usage={"ratelimit": {"remaining_requests": 5,
                                                                      "limit_requests": 100}})
    assert provider_budget.order_for("carousel", BASE)[0] != "cerebras"


def test_groq_rate_limited_fails_over_and_logs_producer(monkeypatch, caplog):
    calls = []

    def groq(prompt, n):
        calls.append("groq")
        return None, {"status_code": 429, "model": "gpt-oss-20b", "error": "Rate limit reached (TPM)"}

    def nokey(prompt, n):
        calls.append("nokey")
        return None, {}

    def gemini(prompt, n):
        calls.append("gemini")
        return '{"caption": "ok"}', {"prompt_tokens": 10, "completion_tokens": 5, "model": "flash"}

    provs = [("gemini", gemini), ("groq", groq)] + [(n, nokey) for n in BASE[2:]]
    monkeypatch.setattr(llm_router, "_PROVIDERS", provs)
    monkeypatch.setattr(llm_router.ollama, "is_available", lambda: False)
    monkeypatch.setattr("content_generator.core.brand_guard.build_system_prompt", lambda: "RULES")
    import logging
    caplog.set_level(logging.INFO)
    for i in range(4):  # several reels in a row: Groq 429 must not sink the run
        assert llm_router.call("p", label=f"reel_{i}") == {"caption": "ok"}
    assert "PRODUCED_BY=gemini" in caplog.text
    assert calls.count("groq") == 1  # rotated away after its 429
    # missing-key providers never trip a circuit
    assert llm_router._STATES["mistral"].is_available()


def test_last_chance_pass_ignores_tripped_circuits(monkeypatch):
    for _ in range(3):
        llm_router._STATES["gemini"].record_failure()
    assert not llm_router._STATES["gemini"].is_available()
    monkeypatch.setattr(llm_router, "_PROVIDERS",
                        [("gemini", lambda p, n: ('{"a": 1}', {"model": "x"}))])
    monkeypatch.setattr(llm_router, "_KEY_GETTERS", (("gemini", lambda: "k"),))
    monkeypatch.setattr(llm_router.ollama, "is_available", lambda: False)
    monkeypatch.setattr("content_generator.core.brand_guard.build_system_prompt", lambda: "RULES")
    assert llm_router.call("p", label="stories") == {"a": 1}
