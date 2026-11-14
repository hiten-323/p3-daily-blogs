"""A claim-blocked Instagram Story must not be republished forever.

2026-11-03: stories.story_1 was "FREEZE-DRIED VS AGGLOMERATED" on a Purista day.
Process match refused it (agglomerated has to name Bold). The retry workflow
loaded that same headline every five minutes, so the Story never moved.
"""
from __future__ import annotations

import json
from pathlib import Path


_BLOCKED_HEADLINE = "FREEZE-DRIED VS AGGLOMERATED"
_BLOCKED_SUB = "Can you taste the difference in your cup?"


def _pack() -> dict:
    return {
        "day_number": 306,
        "date": "2026-11-03",
        "featured_product": "Purista",
        "stories": {
            "story_1": {
                "type": "poll",
                "headline": _BLOCKED_HEADLINE,
                "subtext": _BLOCKED_SUB,
                "poll_question": "Which instant coffee texture do you buy most often?",
                "option_a": "Fine dark granules",
                "option_b": "Coarse freeze-dried crystals",
            },
            "story_2": {
                "headline": "FRESH SINGLE-ORIGIN BEANS",
                "subtext": "Free sample versus the competitor jar.",
            },
            "story_3": {
                "headline": _BLOCKED_HEADLINE,
                "subtext": "Same blocked comparison again.",
            },
            "story_4": {
                "headline": "Want to taste pure freeze-dried coffee?",
                "offer": "Purista is freeze-dried pure Robusta.",
            },
        },
        "reels": [{"hook": "EVENING REEL STAYS", "caption": "reel_1 only"}],
    }


def _publish_text(headline: str, sub: str) -> str:
    from content_generator.publisher.product_links import story_link_line

    return f"{headline}\n{story_link_line(sub)}"


def test_original_agglomerated_line_still_fails_process_match():
    """The claim check itself stays closed. Recovery may not loosen it."""
    from content_generator.core.process_match import process_match_findings

    hits = process_match_findings(
        _publish_text(_BLOCKED_HEADLINE, _BLOCKED_SUB), featured="Purista",
    )
    assert hits
    assert "agglomerated mention must match Bold" in hits[0]["reason"]


def test_retry_replaces_claim_blocked_story_and_records_the_lesson(tmp_path, monkeypatch):
    from content_generator.core.process_match import process_match_findings
    from content_generator.publisher.story_copy import resolve_story_copy
    from content_generator.scheduler import retry_unposted as ru

    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(tmp_path / "lessons.json"))
    content = _pack()
    reel = dict(content["reels"][0])

    assert ru.recover_blocked_stories(content, ["reel_1"]) is False
    assert content["stories"]["story_1"]["headline"] == _BLOCKED_HEADLINE

    assert ru.recover_blocked_stories(content, ["ig_story", "reel_1"]) is True
    copy = resolve_story_copy(content, 306)
    published = _publish_text(copy["headline"], copy["sub"])
    assert copy["headline"] != _BLOCKED_HEADLINE
    assert process_match_findings(published, featured="Purista") == []
    lowered = published.lower()
    assert "single-origin" not in lowered
    assert "free sample" not in lowered
    assert "competitor" not in lowered
    assert "fresh" not in lowered
    assert "purity beans" in lowered or "bean" not in lowered.replace("purity beans", "")
    assert "prima" not in lowered
    assert content["reels"] == [reel]
    assert "reel_2" not in content
    assert "reel_2" not in ru.TARGETS
    assert ru.TARGETS["reel_1"][0] == "evening"
    assert ru.TARGETS["reel_1"][2] == ("reel_1",)

    lessons = json.loads((tmp_path / "lessons.json").read_text(encoding="utf-8"))
    row = lessons["lessons"][0]
    assert row["label"] == "stories"
    assert row["gate"] == "process_match"
    assert "agglomerated" in row["reason"].lower()

    assert ru.recover_blocked_stories(content, ["ig_story"]) is False
    assert json.loads((tmp_path / "lessons.json").read_text(encoding="utf-8"))["lessons"][0]["count"] == 1

    src = Path("content_generator/scheduler/retry_unposted.py").read_text(encoding="utf-8")
    assert src.index("recover_blocked_stories(content, todo)") < src.index("run_publish_slot")


def test_bank_variant_is_used_when_other_frames_are_blocked(tmp_path, monkeypatch):
    from content_generator.core.process_match import process_match_findings
    from content_generator.publisher.story_copy import resolve_story_copy
    from content_generator.scheduler.retry_unposted import recover_blocked_stories

    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(tmp_path / "lessons.json"))
    content = _pack()
    content["day_number"] = 200
    content["stories"].pop("story_4")
    assert recover_blocked_stories(content, ["ig_story"]) is True
    copy = resolve_story_copy(content, 200)
    published = _publish_text(copy["headline"], copy["sub"])
    assert copy["headline"] == "ONE INGREDIENT"
    assert "bean" not in published.lower()
    assert process_match_findings(published, featured="Purista") == []


def test_measured_story_is_not_swapped_off_the_quality_bar(tmp_path, monkeypatch):
    from content_generator.scheduler.retry_unposted import recover_blocked_stories

    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(tmp_path / "lessons.json"))
    content = _pack()
    content["stories"]["story_1"]["editorial_score"] = {"overall": 8.6, "verdict": "PASS"}
    content["stories"]["story_1"]["viral_potential"] = {"passed": True, "overall": 9.2}
    assert recover_blocked_stories(content, ["ig_story"]) is False
    assert content["stories"]["story_1"]["headline"] == _BLOCKED_HEADLINE
    assert content["stories"]["story_1"]["editorial_score"]["overall"] == 8.6
    lessons = json.loads((tmp_path / "lessons.json").read_text(encoding="utf-8"))
    assert lessons["lessons"][0]["gate"] == "process_match"


def test_post_story_logs_the_claim_block_and_does_not_publish(tmp_path, monkeypatch):
    from content_generator.publisher import instagram

    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(tmp_path / "lessons.json"))
    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    content = _pack()
    content["stories"] = {"story_1": dict(content["stories"]["story_1"])}
    # This test is about the process-match block, so give the story the
    # verdicts the shared bar now requires before that check runs.
    content["stories"]["story_1"]["editorial_score"] = {"overall": 8.6, "verdict": "PASS"}
    content["stories"]["story_1"]["viral_potential"] = {"passed": True, "overall": 9.2, "honesty": []}
    result = instagram.post_story(content, day=306)
    assert result["success"] is False
    assert result["attempted"] is False
    assert result["skipped"] is True
    assert result["error"] == "process_match_failed"
    lessons = json.loads((tmp_path / "lessons.json").read_text(encoding="utf-8"))
    assert lessons["lessons"][0]["gate"] == "process_match"
    assert content["stories"]["story_1"]["headline"] == _BLOCKED_HEADLINE
