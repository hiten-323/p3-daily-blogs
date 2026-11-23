"""xAI (Grok) is the main writer and scorer (owner, 17 Nov 2026).

Thresholds are untouched: these tests only cover routing and the provider.
"""
import json
from pathlib import Path

import pytest

from content_generator.providers import llm_router, provider_budget, xai, openai_compat

ROOT = Path(__file__).resolve().parents[1]
FULL = [n for n, _ in llm_router._PROVIDERS]


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_USAGE_DIR", str(tmp_path))
    for name in xai.KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    provider_budget.reset_for_tests()
    llm_router.reset_cascade_log()
    for st in llm_router._STATES.values():
        st.record_success()
    yield
    provider_budget.reset_for_tests()
    llm_router.reset_cascade_log()


class _Resp:
    def __init__(self, status, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text or (json.dumps(body) if body is not None else "")
        self.headers = {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _ok(text="hello"):
    return _Resp(200, {"choices": [{"message": {"content": text}}], "usage": {}})


def test_xai_is_distinct_from_groq_and_uses_the_xai_endpoint():
    from content_generator.providers import groq
    assert xai._URL == "https://api.x.ai/v1/chat/completions"
    assert "x.ai" not in groq._URL and xai._URL != groq._URL
    assert xai.MODELS[0] == "grok-4.7" and len(xai.MODELS) >= 2


def test_missing_key_is_skipped_silently(monkeypatch):
    called = []
    monkeypatch.setattr(openai_compat._http, "post", lambda *a, **k: called.append(1))
    assert xai.call("hi", 100) == (None, {})
    assert not called and xai.key_source() == ""


def test_key_name_and_alias(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "g")
    assert xai.key_source() == "GROK_API_KEY" and xai.get_key() == "g"
    monkeypatch.setenv("XAI_API_KEY", "x")
    assert xai.key_source() == "XAI_API_KEY" and xai.get_key() == "x"


def test_call_sends_bearer_key_grok_model_and_enough_tokens(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k")
    seen = {}

    def post(url, headers=None, timeout=None, json=None):
        seen.update(url=url, auth=headers["Authorization"], body=json)
        return _ok('{"overall": 9.1}')

    monkeypatch.setattr(openai_compat._http, "post", post)
    text, usage = xai.call("score", 800)
    assert text == '{"overall": 9.1}' and usage["model"] == "grok-4.7"
    assert seen["url"] == xai._URL and seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "grok-4.7"
    assert seen["body"]["max_tokens"] >= 4000  # reasoning must not eat the JSON answer


def test_xai_leads_every_route_including_the_scorers():
    for label in ("fresh_reel_1", "editorial_reel_1", "viral_reel_1", "stories",
                  "carousel", "editorial_instagram_post", "linkedin_post", "threads_post",
                  "facebook_post", "editorial_yt_short", "blog_section_s0", "anything"):
        order = provider_budget.order_for(label, FULL)
        assert order[0] == "xai", (label, order)
        assert sorted(order) == sorted(FULL)  # the whole free chain stays as fallback


def test_platform_free_provider_follows_xai():
    assert provider_budget.order_for("reel_1", FULL)[:2] == ["xai", "groq"]
    assert provider_budget.order_for("facebook_post", FULL)[:3] == ["xai", "mistral", "gemini"]


def test_a_429_falls_through_this_call_but_xai_stays_first_next_time(monkeypatch):
    calls = []

    def xai_429(prompt, max_tokens):
        calls.append("xai")
        return None, {"status_code": 429, "model": "grok-4.7", "error": "rate limited"}

    def gemini_ok(prompt, max_tokens):
        calls.append("gemini")
        return '{"ok": true}', {"model": "g"}

    monkeypatch.setattr(llm_router, "_PROVIDERS", [("xai", xai_429), ("gemini", gemini_ok)])
    from content_generator.core import brand_guard
    monkeypatch.setattr(brand_guard, "build_system_prompt", lambda: "")
    assert llm_router.call("p", label="editorial_reel_1") == {"ok": True}
    assert calls == ["xai", "gemini"]
    # A paid per-minute 429 does not demote xAI for the rest of the day.
    assert provider_budget.order_for("viral_reel_1", ["xai", "gemini", "groq"])[0] == "xai"


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_moves_down_the_chain(monkeypatch, status):
    monkeypatch.setattr(llm_router.time, "sleep", lambda s: None)
    calls = []

    def xai_5xx(prompt, max_tokens):
        calls.append("xai")
        return None, {"status_code": status, "model": "grok-4.7", "error": "down"}

    def groq_ok(prompt, max_tokens):
        calls.append("groq")
        return '{"ok": 1}', {"model": "q"}

    monkeypatch.setattr(llm_router, "_PROVIDERS", [("xai", xai_5xx), ("groq", groq_ok)])
    from content_generator.core import brand_guard
    monkeypatch.setattr(brand_guard, "build_system_prompt", lambda: "")
    assert llm_router.call("p", label="fresh_reel_1") == {"ok": 1}
    assert calls[-1] == "groq" and "xai" in calls


def test_github_models_is_not_in_the_chain_or_routes():
    assert "github_models" not in llm_router._DEFAULT_ORDER
    cfg = json.loads((ROOT / "config" / "provider_routing.json").read_text())
    routes = json.dumps(cfg["routes"])
    assert "github_models" not in routes
    assert cfg["primary_providers"] == ["xai"]


def test_workflows_pass_the_xai_secret_to_generation_scoring_and_retry_steps():
    import yaml
    for wf, steps in {
        "daily.yml": ("Probe LLM providers", "Run autonomous pipeline"),
        "retry-unposted.yml": ("Retry unposted platforms/types",),
        "publish-recovery.yml": ("Retry due publishing failures",),
    }.items():
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / wf).read_text())
        by_name = {s.get("name"): s for job in doc["jobs"].values() for s in job["steps"]}
        for step in steps:
            env = by_name[step].get("env") or {}
            assert env.get("XAI_API_KEY") == "${{ secrets.XAI_API_KEY }}", (wf, step)
            assert env.get("GROK_API_KEY") == "${{ secrets.GROK_API_KEY }}", (wf, step)


def test_thresholds_unchanged():
    from content_generator.core import viral_gate, fallback_ladder
    from content_generator.creative import visual_gate
    from content_generator.editorial import editorial_engine

    assert viral_gate.PASS_MARK == 9.0
    assert fallback_ladder.PASS_FLOOR == 8.0
    assert visual_gate.AESTHETIC_PASS == 8.0
    assert editorial_engine.get_current_pass_score() >= 8.0
