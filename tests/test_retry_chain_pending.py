"""The retry chain must survive a dropped cron that writes no ledger rows."""
import datetime as dt
from pathlib import Path

from content_generator.scheduler import retry_unposted as ru

ROOT = Path(__file__).resolve().parents[1]
T = lambda h, m=7: dt.datetime(2026, 10, 17, h, m)


def test_no_chain_before_0700():
    assert ru.pending_targets(T(6), records=[], pack_exists=False) == []


def test_missing_pack_keeps_chain_alive():
    assert ru.pending_targets(T(10, 25), records=[], pack_exists=False) == [ru.NO_PACK]


def test_dropped_morning_slot_with_no_rows_is_pending():
    # Oct 17: only a generate|threads SKIPPED row, morning never ran.
    rec = [{"slot": "generate", "platform": "threads", "status": "SKIPPED"}]
    todo = ru.pending_targets(T(11, 37), records=rec, pack_exists=True)
    for t in ("ig_feed", "ig_story", "facebook", "threads"):
        assert t in todo
    assert "ig_reel" not in todo  # evening reel is not due before 22:00


def test_nothing_pending_once_morning_and_generate_live():
    live = "VERIFIED_LIVE"
    rec = [{"slot": s, "platform": p, "status": live} for s, p in (
        ("morning", "instagram"), ("morning", "instagram_story"), ("morning", "facebook"),
        ("generate", "linkedin"), ("generate", "youtube"), ("generate", "threads"))]
    assert ru.pending_targets(T(12), records=rec, pack_exists=True) == []
    assert ru.pending_targets(T(22, 37), records=rec, pack_exists=True) == ["ig_reel"]


def test_workflows_chain_on_due_targets_not_ledger_rows():
    wf = ROOT / ".github/workflows"
    retry = (wf / "retry-unposted.yml").read_text(encoding="utf-8")
    daily = (wf / "daily.yml").read_text(encoding="utf-8")
    assert "retry_unposted --pending" in retry
    assert "gh workflow run retry-unposted.yml" in retry
    assert "gh workflow run daily.yml" in retry and "slot=generate" in retry
    assert "actions: write" in daily
    assert "gh workflow run retry-unposted.yml" in daily


def test_instagram_reel_alias_counts_as_posted():
    # The publisher writes the platform key instagram_reel for some reel paths.
    rec = [{"slot": "evening", "platform": "instagram_reel", "status": "VERIFIED_LIVE"}]
    assert "ig_reel" not in ru.unposted_targets(rec, 23)
