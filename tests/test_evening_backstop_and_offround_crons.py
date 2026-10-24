import datetime as dt
from pathlib import Path

from content_generator.scheduler import retry_unposted as ru
from content_generator.core.slot_registry import SLOTS

ROOT = Path(__file__).resolve().parents[1]


def test_crons_off_round_minutes():
    text = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    for cron in ("43 0 * * *", "23 4 * * *", "23 16 * * *"):
        assert f"cron: '{cron}'" in text
    for bad in ("30 0 * * *", "30 4 * * *", "30 16 * * *"):
        assert f"cron: '{bad}'" not in text
    for s in SLOTS:
        assert s["ist"].split(":")[1] not in ("00", "30")


def test_generate_stays_after_0600_ist():
    # content_date_for_slot rolls generate back a day before 06:00 IST.
    gen = next(s for s in SLOTS if s["id"] == "generate")
    hh, mm = map(int, gen["ist"].split(":"))
    assert hh * 60 + mm >= 6 * 60


def test_backstop_waits_until_2215():
    t = lambda h, m: dt.datetime(2026, 10, 16, h, m)
    assert ru.evening_backstop_wait(t(22, 7))
    assert not ru.evening_backstop_wait(t(22, 37))
    assert not ru.evening_backstop_wait(t(23, 7))


def _approved_pack():
    return {
        "instagram_post": {"hook": "feed"},
        "reel_1": {"hook": "a"},
        "reel_2": {"hook": "b"},
        "growth_reel": {"hook": "g"},
    }


def test_reel_targets_publish_once_the_evening_slot_has_started():
    """21:54 IST is after the 21:53 evening slot. A dropped cron must not drop the reels."""
    todo = ["ig_feed", "reel_1", "reel_2", "growth_reel"]
    plan = ru.publish_plan(todo, _approved_pack(), 21, 54)
    assert plan["prewarm"] == set()
    assert plan["slots"] == {"morning", "evening"}
    assert plan["reels"] == ["growth_reel", "reel_1", "reel_2"]


def test_reels_stay_prewarm_before_the_evening_slot():
    todo = ["ig_feed", "reel_1", "reel_2", "growth_reel"]
    plan = ru.publish_plan(todo, _approved_pack(), 21, 52)
    assert plan["prewarm"] == {"reel_1", "reel_2", "growth_reel"}
    assert plan["slots"] == {"morning"}
    assert plan["reels"] == []


def test_backstop_window_still_publishes_each_unposted_reel():
    """22:07 used to delete every reel target so the cron could own them. The cron posts one."""
    todo = ["ig_feed", "reel_1", "reel_2", "growth_reel"]
    plan = ru.publish_plan(todo, _approved_pack(), 22, 7)
    assert "evening" in plan["slots"]
    assert plan["reels"] == ["growth_reel", "reel_1", "reel_2"]


def test_publish_only_asset_does_not_substitute_another_reel():
    from content_generator.scheduler.slots import _select_evening_reel
    approved = _approved_pack()
    assert _select_evening_reel(approved, only="reel_1")[0] == "reel_1"
    assert _select_evening_reel(approved, {"reel_1"}, only="reel_1") is None
    assert _select_evening_reel(approved)[0] == "growth_reel"


def test_reel_counted_missing_without_evening_records():
    assert "reel_1" in ru.unposted_targets([], 23)
    assert "reel_2" in ru.unposted_targets([], 23)
    rec = [{"slot": "evening", "platform": "instagram", "status": "VERIFIED_LIVE"}]
    assert "reel_1" not in ru.unposted_targets(rec, 23)
    assert "reel_2" in ru.unposted_targets(rec, 23)
