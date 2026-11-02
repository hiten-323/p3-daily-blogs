"""Two reels a day, spread across the day (owner, 2 Nov 2026 11:04 PM IST).

growth_reel posts in the morning slot (09:53 IST), reel_1 in the evening slot
(21:53 IST), reel_2 never. Retry, recovery and the after-midnight backstop all
follow the same schedule and never post both reels together.
"""
import datetime as dt
import json
from pathlib import Path

import pytest

from content_generator.core import reel_schedule as rs
from content_generator.scheduler import retry_unposted as ru
from content_generator.scheduler import slots as sl

ROOT = Path(__file__).resolve().parents[1]
LIVE = ("VERIFIED_LIVE", "PUBLISHED_UNVERIFIED", "UNCERTAIN")
DAY = dt.date(2026, 11, 3)
UTC = dt.timezone.utc


def _pack():
    return {
        "instagram_post": {"hook": "feed"},
        "carousel": {"hook": "slides"},
        "growth_reel": {"hook": "g", "caption": "Growth reel. #PurityBeans"},
        "reel_1": {"hook": "a", "caption": "Reel one. #PurityBeans"},
        "reel_2": {"hook": "b", "caption": "Reel two. #PurityBeans"},
    }


def _row(asset, slot, at, platform="instagram_video", status="VERIFIED_LIVE"):
    return {"asset": asset, "slot": slot, "platform": platform, "status": status,
            "verified_at": at.isoformat()}


# ── schedule ────────────────────────────────────────────────────────────────

def test_schedule_is_growth_morning_reel_1_evening_reel_2_retired():
    assert rs.REEL_SLOT == {"growth_reel": "morning", "reel_1": "evening"}
    assert rs.reel_for_slot("morning") == "growth_reel"
    assert rs.reel_for_slot("evening") == "reel_1"
    assert rs.reel_for_slot("generate") is None
    assert "reel_2" in rs.RETIRED_REELS
    assert rs.MAX_REELS_PER_DAY == 2


def test_retired_reel_2_is_always_blocked():
    assert rs.reel_block_reason("reel_2", [], LIVE).startswith("reel_retired")


def test_daily_cap_blocks_a_third_reel():
    early = dt.datetime(2026, 11, 3, 1, 0, tzinfo=UTC)
    rows = [_row("growth_reel", "morning", early), _row("reel_2", "evening", early)]
    why = rs.reel_block_reason("reel_1", rows, LIVE, now_utc=early + dt.timedelta(hours=12))
    assert why.startswith("daily_reel_cap")


def test_reels_are_never_posted_together():
    growth_at = dt.datetime(2026, 11, 3, 16, 0, tzinfo=UTC)  # 21:30 IST
    rows = [_row("growth_reel", "morning", growth_at)]
    assert rs.reel_block_reason("reel_1", rows, LIVE,
                                now_utc=growth_at + dt.timedelta(minutes=20)).startswith("reel_gap")
    assert rs.reel_block_reason("reel_1", rows, LIVE,
                                now_utc=growth_at + dt.timedelta(hours=4)) == ""


def test_already_live_reel_is_not_posted_again():
    at = dt.datetime(2026, 11, 3, 4, 30, tzinfo=UTC)
    assert rs.reel_block_reason("growth_reel", [_row("growth_reel", "morning", at)], LIVE) == "already_published"


def test_failed_rows_do_not_count_as_live_reels():
    at = dt.datetime(2026, 11, 3, 4, 30, tzinfo=UTC)
    rows = [_row("growth_reel", "morning", at, status="FAILED")]
    assert rs.posted_reels(rows, LIVE) == {}


def test_growth_reel_window_closes_before_the_evening_reel():
    assert rs.reel_window_open("growth_reel", 10, 7)
    assert rs.reel_window_open("growth_reel", 17, 59)
    assert not rs.reel_window_open("growth_reel", 18, 0)
    assert not rs.reel_window_open("growth_reel", 22, 7)
    assert rs.reel_window_open("reel_1", 23, 0)
    assert not rs.reel_window_open("reel_2", 12, 0)


# ── retry-unposted ──────────────────────────────────────────────────────────

def test_retry_targets_follow_the_new_slots():
    assert "reel_2" not in ru.TARGETS
    assert ru.TARGETS["growth_reel"][0] == "morning"
    assert ru.TARGETS["reel_1"][0] == "evening"
    assert ru.EVENING_REEL_TARGETS == ("reel_1",)
    assert "reel_2" not in ru.INSTAGRAM_TARGETS


def test_reel_2_is_never_due_or_regenerated():
    assert "reel_2" not in ru.unposted_targets([], 12)
    assert "reel_2" not in ru.unposted_targets([], 23)
    assert "reel_2" not in ru.labels_to_regen(list(ru.TARGETS), {}, [])


def test_growth_reel_due_in_the_morning_only():
    assert "growth_reel" in ru.unposted_targets([], 10)
    assert "growth_reel" in ru.unposted_targets([], 17)
    assert "growth_reel" not in ru.unposted_targets([], 18)
    assert "growth_reel" not in ru.unposted_targets([], 23)


def test_morning_growth_reel_row_covers_growth_reel_only():
    at = dt.datetime(2026, 11, 3, 4, 30, tzinfo=UTC)
    rows = [_row("growth_reel", "morning", at)]
    todo = ru.unposted_targets(rows, 12)
    assert "growth_reel" not in todo
    assert "ig_feed" in todo and "carousel" in todo and "ig_story" in todo
    rows.append(_row("growth_reel", "morning", at, platform="instagram_story"))
    assert "ig_story" in ru.unposted_targets(rows, 12)


def test_backstop_after_midnight_never_includes_the_growth_reel():
    assert ru.EVENING_REEL_TARGETS == ("reel_1",)
    src = (ROOT / "content_generator/scheduler/retry_unposted.py").read_text(encoding="utf-8")
    assert "for t in EVENING_REEL_TARGETS if t in unposted_targets(records_for_date(y), 23)" in src


def test_retry_plan_never_runs_both_reels():
    plan = ru.publish_plan(["growth_reel", "reel_1"], _pack(), 23, 0, override=True)
    assert plan["reels"] == []
    plan = ru.publish_plan(["reel_1"], _pack(), 22, 7)
    assert plan["reels"] == ["reel_1"]
    plan = ru.publish_plan(["growth_reel", "reel_1"], _pack(), 11, 7)
    assert plan["slots"] == {"morning"} and plan["reels"] == []


def test_instagram_pause_still_drops_every_reel_target(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "true")
    targets = ru.active_targets()
    assert not set(targets) & {"growth_reel", "reel_1", "reel_2"}
    assert "facebook" in targets


def test_pause_switch_value_is_untouched():
    data = json.loads((ROOT / "config/instagram_pause.json").read_text(encoding="utf-8"))
    assert "paused" in data


# ── slots ───────────────────────────────────────────────────────────────────

def test_slots_select_only_their_own_reel():
    pack = _pack()
    assert sl._select_slot_reel(pack, "morning")[0] == "growth_reel"
    assert sl._select_slot_reel(pack, "evening")[0] == "reel_1"
    assert sl._select_slot_reel({"reel_2": pack["reel_2"]}, "evening") is None
    assert sl._select_slot_reel({"growth_reel": pack["growth_reel"]}, "evening") is None
    assert sl._select_slot_reel({"reel_1": pack["reel_1"]}, "morning") is None


@pytest.fixture
def publish_env(monkeypatch):
    """Stub the Meta publishers; record which reel assets and platforms publish."""
    calls = []
    records = []
    monkeypatch.setattr(sl, "_reel_records", lambda on_date: list(records))
    import content_generator.publisher.instagram as ig
    monkeypatch.setattr(ig, "is_configured", lambda: True)
    monkeypatch.setattr(ig, "_assemble_caption", lambda body, piece, day: body)
    monkeypatch.setattr(ig, "_post_reel_direct_binary", lambda path, caption: {"success": True, "media_id": "1"})
    import content_generator.creative.reel_video as rv
    monkeypatch.setattr(rv, "build_reel_video", lambda reel, day, label="", on_date=None: f"/tmp/{label}.mp4")
    import content_generator.publisher.publishing_ledger as pl

    def _ledger(platform, content, slot, day, publish, asset=""):
        calls.append((platform, slot, asset))
        return publish()

    monkeypatch.setattr(pl, "publish_with_ledger", _ledger)
    import content_generator.core.publish_bar as pb
    monkeypatch.setattr(pb, "quality_block", lambda piece, label: "")
    monkeypatch.setattr(sl, "_find_hero_video", lambda: None)
    monkeypatch.setattr(sl, "_track", lambda *a, **k: None)
    fb = []
    monkeypatch.setattr(sl, "_mirror_to_facebook",
                        lambda content, day, slot, **k: fb.append((slot, k.get("mirror_label"))) or {"success": True})
    return {"calls": calls, "records": records, "fb": fb}


def test_evening_slot_posts_reel_1_only_with_facebook_mirror(publish_env):
    out = sl._publish_slot_reel("evening", 307, {"day_number": 307}, _pack(), DAY)
    assert out["chosen"] == "reel_1"
    assert publish_env["calls"] == [("instagram_video", "evening", "reel_1")]
    assert publish_env["fb"] == [("evening", "reel_1")]


def test_evening_slot_holds_once_reel_1_is_live(publish_env):
    publish_env["records"].append(_row("reel_1", "evening", dt.datetime.now(UTC)))
    out = sl._publish_slot_reel("evening", 307, {"day_number": 307}, _pack(), DAY)
    assert out["contract"]["status"] == "held"
    assert "already_published" in out["contract"]["reason"]
    assert publish_env["calls"] == []


def test_evening_slot_holds_reel_1_next_to_a_fresh_growth_reel(publish_env):
    publish_env["records"].append(_row("growth_reel", "morning", dt.datetime.now(UTC)))
    out = sl._publish_slot_reel("evening", 307, {"day_number": 307}, _pack(), DAY)
    assert out["contract"]["reason"].startswith("reel_gap")
    assert publish_env["calls"] == []
    from content_generator.core.publish_contract import evaluate
    assert evaluate(out["contract"])["ok"] is True


def test_morning_reel_posts_growth_reel_without_a_second_facebook_post(publish_env, monkeypatch):
    import content_generator.core.ist_dates as ist
    monkeypatch.setattr(ist, "today_ist", lambda now=None: DAY)
    import content_generator.core.editorial_engine as ee
    monkeypatch.setattr(ee, "approved_assets", lambda content: _pack())

    class _Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 11, 3, 4, 30, tzinfo=UTC)  # 10:00 IST

    monkeypatch.setattr(sl.datetime, "datetime", _Clock)
    res = sl._morning_reel({"day_number": 307}, 307, DAY)
    assert res.get("success") is True and res.get("asset") == "growth_reel"
    assert publish_env["calls"] == [("instagram_video", "morning", "growth_reel")]
    assert publish_env["fb"] == []  # the morning feed mirror is the day's morning FB post


def test_morning_reel_window_closed_in_the_evening(publish_env, monkeypatch):
    import content_generator.core.ist_dates as ist
    monkeypatch.setattr(ist, "today_ist", lambda now=None: DAY)

    class _Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 11, 3, 16, 30, tzinfo=UTC)  # 22:00 IST

    monkeypatch.setattr(sl.datetime, "datetime", _Clock)
    assert sl._morning_reel({}, 307, DAY)["reason"] == "morning_reel_window_closed"
    assert publish_env["calls"] == []


def test_morning_reel_is_never_backfilled_for_another_day(publish_env, monkeypatch):
    import content_generator.core.ist_dates as ist
    monkeypatch.setattr(ist, "today_ist", lambda now=None: DAY + dt.timedelta(days=1))
    assert sl._morning_reel({}, 307, DAY)["reason"] == "morning_reel_window_closed"
    assert publish_env["calls"] == []


def test_morning_reel_respects_the_instagram_pause(publish_env, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "true")
    assert sl._morning_reel({}, 307, DAY)["reason"] == "instagram_paused"
    assert publish_env["calls"] == []


def test_paused_evening_still_mirrors_facebook_and_posts_no_reel(publish_env, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "true")
    import content_generator.core.instagram_pause as ip
    monkeypatch.setattr(ip, "paused_result", lambda: {"success": False, "skipped": True, "error": "paused"})
    import content_generator.publisher.instagram as ig
    monkeypatch.setattr(ig, "prepare_feed_image", lambda image: None)
    monkeypatch.setattr(ig, "post_local_story", lambda image: {"success": True})
    monkeypatch.setattr(sl, "_find_reel_thumbnail", lambda date_str=None: "/tmp/thumb.jpg")
    import content_generator.creative.jar_provenance as jp
    monkeypatch.setattr(jp, "verify_jar_provenance", lambda path: {"verified": True})
    out = sl._publish_slot_reel("evening", 307, {"day_number": 307}, _pack(), DAY)
    assert out["chosen"] == "reel_1" and out["ig_paused"] is True
    assert publish_env["calls"] == []
    assert publish_env["fb"] == [("evening", "reel_1")]


# ── no third reel anywhere else ────────────────────────────────────────────

def test_sales_push_never_adds_a_third_reel():
    from content_generator.campaigns import trial_diwali_push as push
    content = {"sales_push": {"active": True, "slug": "bold", "reel": {"video_path": "/tmp/x.mp4"}}}
    assert push.publish_for_slot(content, "evening", 1)["reason"] == "two_reels_per_day"


def test_gates_unchanged():
    from content_generator.core.publish_contract import LEGIT_HOLDS
    assert "reel_gap" in LEGIT_HOLDS and "daily_reel_cap" in LEGIT_HOLDS
    retry = (ROOT / ".github/workflows/retry-unposted.yml").read_text(encoding="utf-8")
    assert "QUALITY_LADDER_MAX: '8'" in retry
