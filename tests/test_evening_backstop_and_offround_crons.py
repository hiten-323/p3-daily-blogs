"""The retry chain must not drop reel_1 during the evening slot window."""
import os
import sys
from pathlib import Path

from content_generator.scheduler import retry_unposted as ru

ROOT = Path(__file__).resolve().parents[1]


def _approved_pack():
    return {
        "reel_1": {
            "hook": "Why your instant coffee tastes like bitter mud",
            "editorial_score": {"overall": 8.7, "verdict": "pass"},
        },
        "growth_reel": {
            "hook": "The Rs 200-a-week habit nobody calculates",
            "editorial_score": {"overall": 8.9, "verdict": "pass"},
        },
        "reel_2": {
            "hook": "Zero chicory on the label",
            "editorial_score": {"overall": 8.8, "verdict": "pass"},
        },
        "instagram_post": {
            "caption": "Real coffee caption",
            "editorial_score": {"overall": 8.5, "verdict": "pass"},
        },
        "carousel": {
            "slides": ["Slide 1", "Slide 2"],
            "editorial_score": {"overall": 8.6, "verdict": "pass"},
        },
        "stories": {
            "frames": ["Frame 1"],
            "editorial_score": {"overall": 8.5, "verdict": "pass"},
        },
        "facebook_post": {
            "message": "FB caption",
            "editorial_score": {"overall": 8.5, "verdict": "pass"},
        },
    }


def test_reel_1_publishes_once_the_evening_slot_has_started():
    """21:54 IST is after the 21:53 evening slot. A dropped cron must not drop reel_1.

    Two reels a day (owner, 2 Nov 2026): reel_2 is retired and growth_reel is a
    morning target, so the evening plan is reel_1 alone.
    """
    todo = ["ig_feed", "reel_1"]
    plan = ru.publish_plan(todo, _approved_pack(), 21, 54)
    assert plan["prewarm"] == set()
    assert plan["slots"] == {"morning", "evening"}
    assert plan["reels"] == ["reel_1"]


def test_reel_1_stays_prewarm_before_the_evening_slot():
    todo = ["ig_feed", "reel_1"]
    plan = ru.publish_plan(todo, _approved_pack(), 21, 52)
    assert plan["prewarm"] == {"reel_1"}
    assert plan["slots"] == {"morning"}
    assert plan["reels"] == []


def test_reel_1_is_an_evening_target_and_prewarmed_before_evening():
    todo = ["growth_reel", "reel_1"]
    plan = ru.publish_plan(todo, _approved_pack(), 10, 7)
    assert plan["prewarm"] == {"reel_1"}
    assert plan["slots"] == {"morning"}
    assert plan["reels"] == []


def test_backstop_window_still_publishes_reel_1():
    """22:07 used to delete every reel target so the cron could own them."""
    todo = ["ig_feed", "reel_1"]
    plan = ru.publish_plan(todo, _approved_pack(), 22, 7)
    assert "evening" in plan["slots"]
    assert plan["reels"] == ["reel_1"]


def test_publish_plan_never_puts_both_reels_in_one_run():
    plan = ru.publish_plan(["growth_reel", "reel_1"], _approved_pack(), 22, 7, override=True)
    assert "morning" in plan["slots"]
    assert plan["reels"] == []


def test_publish_only_asset_does_not_substitute_another_reel():
    from content_generator.scheduler.slots import _select_evening_reel, _select_slot_reel
    approved = _approved_pack()
    assert _select_evening_reel(approved, only="reel_1")[0] == "reel_1"
    assert _select_evening_reel(approved, {"reel_1"}, only="reel_1") is None
    assert _select_evening_reel(approved)[0] == "reel_1"
    assert _select_evening_reel(approved, only="reel_2") is None
    assert _select_evening_reel(approved, only="growth_reel") is None
    assert _select_slot_reel(approved, "morning")[0] == "growth_reel"
    assert _select_slot_reel(approved, "morning", only="reel_1") is None


def test_reel_counted_missing_without_evening_records():
    assert "reel_1" in ru.unposted_targets([], 23)
    assert "reel_2" not in ru.unposted_targets([], 23)
    rec = [{"slot": "evening", "platform": "instagram_video", "asset": "reel_1", "status": "VERIFIED_LIVE"}]
    assert "reel_1" not in ru.unposted_targets(rec, 23)
