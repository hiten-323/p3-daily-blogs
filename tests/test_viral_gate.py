from content_generator.core import viral_gate as vg

GOOD = {k: 9 for k in vg.DIMENSIONS}


def _call(scores, overall=9):
    return lambda prompt, label, max_tokens: {"scores": scores, "overall": overall, "feedback": "f"}


def test_pass_mark_is_8():
    assert vg.PASS_MARK == 8.0


def test_passes_at_or_above_8():
    r = vg.evaluate("reel_1", {"caption": "POV: the office cup"}, call=_call(GOOD))
    assert r["passed"] and r["overall"] == 9


def test_overall_cannot_be_inflated_by_model():
    low = dict(GOOD, hook=2, follow_cta=3)
    r = vg.evaluate("threads_post", {"text": "x"}, call=_call(low, overall=9.5))
    assert not r["passed"] and r["overall"] < 8


def test_missing_dimension_fails_closed():
    r = vg.evaluate("carousel", {"caption": "x"}, call=_call({"hook": 10}))
    assert not r["passed"] and "error" in r


def test_provider_error_fails_closed():
    def boom(*a, **k):
        raise RuntimeError("down")
    assert not vg.evaluate("linkedin_post", {"text": "x"}, call=boom)["passed"]


def test_honesty_overrides_virality():
    for bad in ("Only 3 jars left, hurry!", "10,000+ happy customers", "Boosts immunity",
                "100% pure coffee", "India's #1 coffee", "went viral with a million views"):
        r = vg.evaluate("reel_1", {"caption": bad}, call=_call(GOOD))
        assert not r["passed"] and r["honesty"], bad


def test_honest_copy_not_flagged():
    assert vg.honesty_issues({"caption": "Pure coffee. Freeze-dried granules. Prevents clumping? Stir 30s."}) == []


def test_feedback_rotates_hook_and_keeps_rules():
    res = {"overall": 6.5, "weakest": ["hook"], "feedback": "weak open"}
    a, b = vg.feedback_for("reel_1", res, 0), vg.feedback_for("reel_1", res, 1)
    assert a != b and "DIFFERENT hook" in a and "Never invent" in a and "@purepantryprovisions" in a


def test_every_format_has_hooks_and_rules():
    for label in ("reel_1", "reel_2", "growth_reel", "yt_short", "carousel", "instagram_post",
                  "threads_post", "linkedin_post", "facebook_post", "blog_post", "story"):
        f = vg.format_for(label)
        assert vg.HOOK_TEMPLATES[f] and vg.FORMAT_RULES[f]
        assert "100%" not in " ".join(vg.HOOK_TEMPLATES[f])


def test_prompt_block_includes_hooks():
    from content_generator.prompts.growth_engine import prompt_block
    assert "VIRAL HOOK TEMPLATES" in prompt_block("reel_1", "bold", 1)


def _score_body(overall: float = 8.7) -> str:
    import json
    return json.dumps({
        "scores": {k: 9 for k in vg.DIMENSIONS},
        "overall": overall,
        "weakest": ["follow_cta"],
        "feedback": "Put the follow reason in the last beat.",
        "better_hook": "Watch one spoon bloom at 85 C.",
    })


# What nvidia/nemotron-3-ultra returned on 2026-10-23: a think trace, sometimes
# with a brace example inside it, and the score object only after the trace.
_REASONING_THEN_JSON = (
    "<think>\n"
    "The user wants me to score a YouTube Short piece for Purity Beans based on "
    "specific dimensions. I need to evaluate the provided JSON piece honestly and "
    "return scores.\n"
    "A scratch note {\"hook\": 1} is not the score.\n"
    "</think>\n"
    "The user wants me to score a YouTube Short piece for Purity Beans based on "
    "specific dimensions. I need to evaluate the provided JSON piece honestly and "
    "return scores.\n\n"
    + _score_body()
)

# The same run truncated inside the trace: 2905 chars, no JSON object at all.
_REASONING_ONLY = (
    "The user wants me to score a YouTube Short piece for Purity Beans based on "
    "specific dimensions. I need to evaluate the provided JSON piece honestly and "
    "return sc"
)


def _nvidia_router(monkeypatch, raw: str):
    from content_generator.providers import llm_router as router
    router.reset_cascade_log()
    for state in router._STATES.values():
        state.record_success()

    def answer(_prompt, _max_tokens):
        return raw, {"model": "nvidia/nemotron-3-ultra-550b-a55b"}

    monkeypatch.setattr(router, "_PROVIDERS", [("nvidia", answer)])
    return router


def test_reasoning_prose_then_json_is_a_real_viral_score(monkeypatch):
    router = _nvidia_router(monkeypatch, _REASONING_THEN_JSON)
    result = vg.evaluate("yt_short", {"caption": "Watch the granules bloom."}, call=router.call)
    assert vg.PASS_MARK == 8.0
    assert result["passed"] is True
    assert result["overall"] == 8.7
    assert "error" not in result
    assert set(result["scores"]) == set(vg.DIMENSIONS)


def test_reasoning_only_truncated_response_is_held(monkeypatch):
    router = _nvidia_router(monkeypatch, _REASONING_ONLY)
    result = vg.evaluate("yt_short", {"caption": "Watch the granules bloom."}, call=router.call)
    assert vg.PASS_MARK == 8.0
    assert result["passed"] is False
    assert result["overall"] is None
    assert str(result.get("error", "")).startswith("viral_scoring_failed")
