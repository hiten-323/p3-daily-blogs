from content_generator.core import viral_gate as vg

GOOD = {k: 9 for k in vg.DIMENSIONS}


def _call(scores, overall=9):
    return lambda prompt, label, max_tokens: {"scores": scores, "overall": overall, "feedback": "f"}


def test_pass_mark_is_9():
    assert vg.PASS_MARK == 9.0


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


def _score_body(overall: float = 9.2) -> str:
    import json
    return json.dumps({
        "scores": {k: 9.4 for k in vg.DIMENSIONS},
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
    assert vg.PASS_MARK == 9.0
    assert result["passed"] is True
    assert result["overall"] == 9.2
    assert "error" not in result
    assert set(result["scores"]) == set(vg.DIMENSIONS)


def test_reasoning_only_truncated_response_is_held(monkeypatch):
    router = _nvidia_router(monkeypatch, _REASONING_ONLY)
    result = vg.evaluate("yt_short", {"caption": "Watch the granules bloom."}, call=router.call)
    assert vg.PASS_MARK == 9.0
    assert result["passed"] is False
    assert result["overall"] is None
    assert str(result.get("error", "")).startswith("viral_scoring_failed")


def test_incomplete_judge_is_retried_once_then_can_pass():
    calls = {"n": 0}

    def call(prompt, label, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"scores": {"hook": 9}, "overall": 9, "feedback": "truncated"}
        return {"scores": dict(GOOD), "overall": 9.2, "feedback": "specific", "weakest": ["hook"]}

    result = vg.evaluate("threads_post", {"text": "The jar lists the process."}, call=call)
    assert calls["n"] == 2
    assert result["passed"] is True
    assert result["overall"] == 9.0
    assert vg.PASS_MARK == 9.0


def test_scoring_failure_keeps_the_draft(monkeypatch):
    """A 9.1 draft must not be rewritten when the judge returns no dimensions."""
    from content_generator.agents import editorial
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    body = (
        "Purity Beans Bold is agglomerated pure coffee. "
        "The back panel names the process. https://p3online.in"
    )
    reviews = {"n": 0}
    scores = {"n": 0}
    regens = {"n": 0}

    def review(piece, label="content"):
        reviews["n"] += 1
        return {
            "shareability": 9.1, "saveability": 9.1, "emotion_pull": 9.1,
            "hook_strength": 9.1, "brand_clarity": 9.1,
            "overall": 9.1, "verdict": "PASS", "feedback": "holds",
        }

    def evaluate(label, piece, call=None):
        scores["n"] += 1
        if scores["n"] == 1:
            return {"passed": False, "overall": None, "scores": {}, "honesty": [],
                    "pass_mark": 9.0, "error": "viral_scoring_failed: ValueError: missing dimensions",
                    "feedback": "viral_scoring_failed: ValueError: missing dimensions"}
        return {"passed": True, "overall": 9.2, "scores": dict(GOOD), "honesty": [],
                "pass_mark": 9.0, "feedback": "specific"}

    def regenerate(*args, **kwargs):
        regens["n"] += 1
        raise AssertionError("scoring failure must not rewrite the draft")

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(editorial, "review_content", review)
    monkeypatch.setattr("content_generator.core.viral_gate.evaluate", evaluate)
    monkeypatch.setattr("content_generator.core.viral_gate.enabled", lambda: True)
    monkeypatch.setattr(daily, "_regenerate_piece", regenerate)
    monkeypatch.setattr(daily, "_growth_gate_reason", lambda *a, **k: "")
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "2")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "2")

    content = {
        "day_number": 309,
        "featured_product": "Bold",
        "threads_post": {"text": body},
    }
    daily._do_editorial(content, only={"threads_post"})
    assert "back panel names the process" in content["threads_post"]["text"]
    assert regens["n"] == 0
    assert scores["n"] == 2
    assert content["threads_post"]["viral_potential"]["overall"] == 9.2
    assert content["threads_post"]["editorial_score"]["overall"] == 9.1


def test_trailing_fragment_does_not_replace_the_score(monkeypatch):
    """A reasoning model often emits the score and then a small closing object.
    The fragment must not become the parse, or normalize raises ValueError and
    the piece is held with no score."""
    raw = (
        "The user wants me to score a YouTube Short piece for Purity Beans.\n"
        + _score_body()
        + '\n{"note": "done"}'
    )
    result = vg.evaluate("threads_post", {"text": "Read the jar."}, call=_nvidia_router(monkeypatch, raw).call)
    assert vg.PASS_MARK == 9.0
    assert result["passed"] is True
    assert result["overall"] == 9.2
    assert "error" not in result


def test_flat_dimension_scores_still_use_the_bar(monkeypatch):
    import json
    flat = {k: 9 for k in vg.DIMENSIONS}
    flat.update(overall=7.4, feedback="Sharper hook.", better_hook="Read the jar first.", weakest=["hook"])
    raw = "Here is the score, not wrapped.\n" + json.dumps(flat)
    result = vg.evaluate("threads_post", {"text": "Read the jar."}, call=_nvidia_router(monkeypatch, raw).call)
    assert result["passed"] is False
    assert result["overall"] == 7.4
    assert "error" not in result
