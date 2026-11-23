"""First-pass quality (owner, 17 Nov 2026): pass the gates on the first generation.

No gate is changed: the rubric and pass marks are read from the scorers.
"""
import json

import pytest

from content_generator.core import first_pass, viral_gate
from content_generator.agents import editorial


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("XAI_API_KEY", "GROK_API_KEY", "FIRST_PASS_SELF_CRITIQUE", "FIRST_PASS_ROUNDS"):
        monkeypatch.delenv(k, raising=False)
    first_pass._DEADLINE["at"] = None
    yield
    first_pass._DEADLINE["at"] = None


def test_pass_marks_unchanged():
    assert viral_gate.PASS_MARK == 9.0
    assert first_pass._editorial_threshold() >= 8.0


def test_rubric_is_the_scorers_own_text():
    block = first_pass.rubric_block("reel_1")
    _rules, rubric = first_pass._editorial_rubric()
    assert rubric and rubric in block and rubric in editorial._PROMPT_TEMPLATE
    for dim in ("shareability", "saveability", "emotion_pull", "hook_strength", "brand_clarity"):
        assert dim in block
    for dim, text in viral_gate.DIMENSIONS.items():
        assert dim in block and text in block
    assert viral_gate.FORMAT_RULES["reel"] in block
    assert ">= 9.0" in block and "EVERY dimension" in block
    for rule in ("100%", "health claim", "fabricated urgency", "fresh", "lab tested",
                 "single-origin", "Ultra Blend", "Purica/Purista", "Bold/Prima", "live Shopify price"):
        assert rule in block, rule


def _write(tmp_path, day, label_key, piece):
    (tmp_path / f"content_{day}.json").write_text(json.dumps({label_key: piece}), encoding="utf-8")


def test_exemplars_are_past_pieces_that_passed_both_gates(tmp_path):
    good = {"hook": "WINNER HOOK", "editorial_score": {"overall": 8.9},
            "viral_potential": {"overall": 9.3, "passed": True}}
    weak = {"hook": "LOSER HOOK", "editorial_score": {"overall": 9.0},
            "viral_potential": {"overall": 8.2, "passed": False, "feedback": "hook too generic",
                                "weakest": ["hook"]}}
    _write(tmp_path, "2026-11-10", "carousel", good)
    _write(tmp_path, "2026-11-11", "carousel", weak)
    block = first_pass.exemplars_block("carousel", str(tmp_path))
    assert "WINNER HOOK" in block and "LOSER HOOK" not in block
    assert "editorial_score" not in block  # scores shown in the header, not as copy to imitate
    fb = first_pass.feedback_block("carousel", str(tmp_path))
    assert "hook too generic" in fb


def test_stories_and_reels_are_read_from_their_nested_slots(tmp_path):
    passed = {"editorial_score": {"overall": 8.5}, "viral_potential": {"overall": 9.1, "passed": True}}
    (tmp_path / "content_2026-11-12.json").write_text(json.dumps({
        "reels": [dict(passed, hook="REEL ONE")],
        "stories": {"story_1": dict(passed, headline="STORY ONE")},
    }), encoding="utf-8")
    assert "REEL ONE" in first_pass.exemplars_block("reel_1", str(tmp_path))
    assert "STORY ONE" in first_pass.exemplars_block("stories", str(tmp_path))


def test_brief_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(first_pass, "exemplars_block", lambda *a, **k: 1 / 0)
    assert "HOW THIS PIECE WILL BE SCORED" in first_pass.brief("threads_post", str(tmp_path))


def test_self_critique_is_off_without_the_xai_key_so_free_quotas_are_not_burned():
    calls = []

    def call(prompt, label, tokens):
        calls.append(label)
        return {"hook": "x"}

    draft, record = first_pass.generate("reel_1", "P", 100, call=call,
                                        evaluator=lambda *a: pytest.fail("must not score"))
    assert draft == {"hook": "x"} and calls == ["reel_1"] and record["enabled"] is False


def test_self_critique_on_with_the_xai_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "k")
    assert first_pass.self_critique_enabled()
    monkeypatch.setenv("FIRST_PASS_SELF_CRITIQUE", "false")
    assert not first_pass.self_critique_enabled()


def test_loop_rewrites_with_feedback_until_it_passes(monkeypatch):
    monkeypatch.setenv("FIRST_PASS_SELF_CRITIQUE", "true")
    drafts = iter([{"v": 1}, {"v": 2}, {"v": 3}])
    prompts = []

    def call(prompt, label, tokens):
        prompts.append((label, prompt))
        return next(drafts)

    results = {1: {"passed": False, "stage": "viral", "editorial": 8.6, "viral": 8.1,
                   "feedback": "hook generic"},
               2: {"passed": False, "stage": "editorial", "editorial": 7.2, "viral": None,
                   "feedback": "drops at line 3"},
               3: {"passed": True, "stage": "viral", "editorial": 8.8, "viral": 9.2, "feedback": ""}}
    best, record = first_pass.generate("carousel", "BASE", 100, call=call,
                                       evaluator=lambda label, d: results[d["v"]], max_rounds=4)
    assert best == {"v": 3} and record["passed"] is True and record["rounds"] == 3
    assert prompts[1][0] == "selfcritique_carousel"
    assert "hook generic" in prompts[1][1] and "BASE" in prompts[1][1]
    assert '"v": 1' in prompts[1][1]


def test_best_version_kept_when_none_passes(monkeypatch):
    monkeypatch.setenv("FIRST_PASS_SELF_CRITIQUE", "true")
    drafts = iter([{"v": 1}, {"v": 2}, {"v": 3}])
    scores = {1: {"passed": False, "stage": "viral", "editorial": 8.5, "viral": 8.6},
              2: {"passed": False, "stage": "copy", "editorial": None, "viral": None},
              3: {"passed": False, "stage": "viral", "editorial": 8.9, "viral": 8.2}}
    best, record = first_pass.generate("threads_post", "B", 50, call=lambda *a: next(drafts),
                                       evaluator=lambda l, d: scores[d["v"]], max_rounds=3)
    assert best == {"v": 1}  # highest viral among drafts that reached the viral gate
    assert record["passed"] is False and record["best"]["viral"] == 8.6


def test_scorer_or_rewrite_failure_keeps_the_draft(monkeypatch):
    monkeypatch.setenv("FIRST_PASS_SELF_CRITIQUE", "true")
    best, record = first_pass.generate("linkedin_post", "B", 50, call=lambda *a: {"v": 1},
                                       evaluator=lambda *a: (_ for _ in ()).throw(RuntimeError("down")))
    assert best == {"v": 1} and record["rounds"] == 0

    calls = iter([{"v": 1}])

    def call(*a):
        return next(calls)  # second call raises StopIteration -> treated as a failed rewrite

    best, record = first_pass.generate(
        "linkedin_post", "B", 50, call=call,
        evaluator=lambda *a: {"passed": False, "stage": "viral", "editorial": 8.1, "viral": 7.0})
    assert best == {"v": 1}


def test_budget_stops_extra_rounds(monkeypatch):
    monkeypatch.setenv("FIRST_PASS_SELF_CRITIQUE", "true")
    first_pass.start_budget(0)
    calls = []

    def call(prompt, label, tokens):
        calls.append(label)
        return {"v": len(calls)}

    first_pass.generate("reel_1", "B", 10, call=call,
                        evaluator=lambda *a: {"passed": False, "stage": "viral", "viral": 7.0})
    assert calls == ["reel_1"]


def test_rounds_are_capped(monkeypatch):
    monkeypatch.setenv("FIRST_PASS_ROUNDS", "99")
    assert first_pass.rounds() == first_pass.MAX_ROUNDS
    monkeypatch.setenv("FIRST_PASS_ROUNDS", "0")
    assert first_pass.rounds() == 1


def test_evaluate_uses_the_real_gate_order(monkeypatch):
    from content_generator.scheduler import daily
    from content_generator.core import editorial_engine
    monkeypatch.setattr(daily, "_schema_issues", lambda l, p: [])
    monkeypatch.setattr(daily, "_validate_piece_copy", lambda l, p: (False, ["'100%' banned"]))
    ev = first_pass.evaluate("reel_1", {"hook": "h"})
    assert ev["stage"] == "copy" and not ev["passed"] and "100%" in ev["feedback"]

    monkeypatch.setattr(daily, "_validate_piece_copy", lambda l, p: (True, []))
    monkeypatch.setattr(editorial, "review_content",
                        lambda piece, label: {"overall": 8.7, "feedback": "ok"})
    monkeypatch.setattr(editorial_engine, "get_current_pass_score", lambda: 8.0)
    monkeypatch.setattr(viral_gate, "evaluate", lambda label, piece: {
        "passed": False, "overall": 8.4, "weakest": ["hook"], "feedback": "weak hook"})
    ev = first_pass.evaluate("reel_1", {"hook": "h"})
    assert ev["stage"] == "viral" and ev["viral"] == 8.4 and not ev["passed"]
    assert "weak hook" in ev["feedback"]

    monkeypatch.setattr(viral_gate, "evaluate", lambda label, piece: {"passed": True, "overall": 9.2})
    ev = first_pass.evaluate("reel_1", {"hook": "h"})
    assert ev["passed"] and ev["editorial"] == 8.7 and ev["viral"] == 9.2


def test_generator_uses_first_pass_and_reports_it():
    src = open("content_generator/pipeline/generator.py", encoding="utf-8").read()
    assert "first_pass.generate" in src and "first_pass.brief(label)" in src
    assert 'output["first_pass_report"]' in src


def test_writer_uses_the_strongest_grok_model_first():
    from content_generator.providers import xai
    assert xai.MODELS[0] == "grok-4.7"

def test_scratch_prompt_includes_first_pass_brief():
    from content_generator.core.fallback_ladder import scratch_prompt
    prompt = scratch_prompt("reel_1", {"featured_product": "Bold"}, "critique", 8.0, "BRAND")
    assert "HOW THIS PIECE WILL BE SCORED" in prompt
    assert "GATE 1, EDITORIAL" in prompt


def test_story_word_cap_and_threads_anti_hedging_rules():
    from content_generator.prompts import stories, threads
    st_prompt = stories.build(1)
    assert "<= 12 words per frame" in st_prompt
    th_prompt = threads.build(("process", "clarity"), "avoid", 1)
    assert "FORBID COMPETITOR-KNOCKING" in th_prompt
    assert "ULTRA BLEND DISCLOSURE" in th_prompt


def test_inject_brand_covers_yt_short_and_reel_1_brand_facts():
    from content_generator.scheduler.daily import _inject_brand_into_piece
    reel = {"caption": "Just coffee in the jar", "cta": ""}
    _inject_brand_into_piece("reel_1", reel)
    assert "p3online.in" in reel["cta"]
    from content_generator.core.brand_validator import validate_brand_facts
    assert validate_brand_facts(f"{reel['caption']} {reel['cta']}")

    yt = {"tagline": "Morning brew", "scenes": [{"spoken": "Pouring hot water", "on_screen": "Brewing"}]}
    _inject_brand_into_piece("yt_short", yt)
    assert "Purity Beans" in yt["scenes"][-1]["spoken"] or "Purity Beans" in yt.get("tagline", "")

