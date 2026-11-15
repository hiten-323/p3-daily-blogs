"""Distinctness gate: one idea per piece per day, no repeats of recent openings."""
from __future__ import annotations

import json

from content_generator.core import distinctness as d


def _day(**over):
    content = {
        "date": "2026-11-15",
        "growth_reel": {"hook": "Your kettle hits 100°C but your coffee wants 94°C.", "angle": "craft"},
        "reels": [{"hook": "Pouring boiling water straight from the kettle scorches the cup.", "angle": "craft"}],
        "instagram_post": {"hook": "Smell the jar before you spoon it: that note is the story.", "angle": "sensory"},
        "carousel": {"title": "Three gifting ideas for the coffee person in your office", "angle": "gifting"},
        "threads_post": {"text": "Which do you add first, milk or coffee? Wrong answers only.", "angle": "poll"},
    }
    content.update(over)
    return content


def test_same_idea_on_same_surface_is_a_collision():
    cols = d.find_collisions(_day(), history=[])
    labels = {c["label"]: c for c in cols}
    assert "reel_1" in labels and labels["reel_1"]["with"] == "growth_reel"
    assert "growth_reel" not in labels  # the higher-priority piece is kept


def test_near_duplicate_hooks_across_surfaces_collide():
    content = _day(threads_post={"text": "Smell the jar before you spoon it: that note is the whole story."})
    cols = d.find_collisions(content, history=[])
    assert any(c["label"] == "threads_post" and c["with"] == "instagram_post" for c in cols)


def test_same_ad_template_on_two_videos_collides():
    content = _day(reels=[{"hook": "Watch the crystals melt in slow motion tonight.", "ad_template_id": "asmr_macro"}],
                   growth_reel={"hook": "Three cafe habits that quietly ruin a home cup.", "ad_template_id": "asmr_macro"})
    cols = d.find_collisions(content, history=[])
    assert any(c["label"] == "reel_1" and "template" in c["reason"] for c in cols)


def test_recent_repeat_on_same_platform_collides_but_other_platform_does_not():
    history = [d.fingerprint("carousel", {"title": "Three gifting ideas for the coffee person in your office"}) | {"date": "2026-11-10"}]
    cols = d.find_collisions(_day(reels=[{"hook": "Milk first or coffee first? Let us settle it."}]), history=history)
    assert any(c["label"] == "carousel" and c["kind"] == "recent_repeat" for c in cols)
    history = [d.fingerprint("linkedin_post", {"hook": "Three gifting ideas for the coffee person in your office"}) | {"date": "2026-11-10"}]
    cols = d.find_collisions(_day(reels=[{"hook": "Milk first or coffee first? Let us settle it."}]), history=history)
    assert not any(c["label"] == "carousel" for c in cols)


def test_enforce_regenerates_and_rechecks_and_reports():
    content = _day()
    calls = []

    def regen(label, piece, feedback):
        calls.append((label, feedback))
        return {"hook": "Weigh one spoon: two grams is a full cup.", "angle": "quantity", "editorial_score": 9.9}

    rescored = []
    report = d.enforce_distinctness(content, regen, rescore=lambda labels: rescored.append(labels), history=[])
    assert calls and calls[0][0] == "reel_1"
    assert "DISTINCTNESS REJECTION" in calls[0][1] and "Angles still unused" in calls[0][1]
    assert content["reels"][0]["hook"].startswith("Weigh one spoon")
    assert "editorial_score" not in content["reels"][0]  # must be re-scored by the normal gate
    assert report["passes"] and report["regenerated"] == ["reel_1"]
    assert rescored == [{"reel_1"}]
    assert content["distinctness"]["pre_editorial"]["initial_collisions"]


def test_enforce_without_regenerator_only_reports():
    content = _day()
    report = d.enforce_distinctness(content, None, history=[])
    assert not report["passes"] and report["remaining_collisions"]


def test_history_reads_previous_content_files_only(tmp_path):
    (tmp_path / "content_2026-11-14.json").write_text(json.dumps({"carousel": {"title": "Old idea about labels on jars"}}))
    (tmp_path / "content_2026-11-15.json").write_text(json.dumps({"carousel": {"title": "Today"}}))
    (tmp_path / "content_2026-10-01.json").write_text(json.dumps({"carousel": {"title": "Too old to matter here"}}))
    rows = d.load_history("2026-11-15", output_dir=str(tmp_path))
    assert [r["date"] for r in rows] == ["2026-11-14"]


def test_novelty_prompt_lists_recent_openings_for_the_surface():
    history = [d.fingerprint("carousel", {"title": "Three lines on your jar that change how you read labels", "angle": "checklist"}) | {"date": "2026-11-12"},
               d.fingerprint("instagram_post", {"hook": "The caramel note in your black coffee", "angle": "checklist"}) | {"date": "2026-11-11"}]
    text = d.novelty_prompt_block("carousel", history=history)
    assert "Three lines on your jar" in text and "checklist (2x)" in text
    assert d.novelty_prompt_block("threads_post", history=history) == ""


def test_daily_wrapper_uses_normal_regenerator(monkeypatch):
    from content_generator.scheduler import daily
    monkeypatch.setenv("DISTINCTNESS_GATE", "1")
    monkeypatch.setattr("content_generator.core.distinctness.load_history", lambda *a, **k: [])
    seen = []

    def fake_regen(label, piece, feedback, content, from_scratch=False):
        seen.append(label)
        return {"hook": "Weigh one spoon: two grams is a full cup.", "frames": []}

    monkeypatch.setattr(daily, "_regenerate_piece", fake_regen)
    monkeypatch.setattr(daily, "_apply_regeneration", lambda label, original, improved: {**original, **improved})
    content = _day()
    report = daily._do_distinctness(content, stage="pre_editorial")
    assert seen == ["reel_1"] and report["passes"]
