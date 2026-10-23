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
    for t in ("ig_feed", "ig_story", "facebook", "threads", "carousel", "reel_1", "reel_2", "youtube"):
        assert t in todo
    assert "growth_reel" in todo


def test_nothing_pending_once_each_piece_is_live():
    live = "VERIFIED_LIVE"
    rec = [{"slot": s, "platform": p, "status": live} for s, p in (
        ("morning", "instagram_story"), ("morning", "facebook"),
        ("generate", "linkedin"), ("generate", "youtube"), ("generate", "threads"))]
    rec.append({"slot": "morning", "platform": "instagram", "status": live, "asset": "instagram_post"})
    rec.append({"slot": "morning", "platform": "instagram", "status": live, "asset": "carousel"})
    for asset in ("reel_1", "reel_2", "growth_reel"):
        rec.append({"slot": "evening", "platform": "instagram_video", "status": live, "asset": asset})
    assert ru.pending_targets(T(12), records=rec, pack_exists=True) == []
    assert ru.pending_targets(T(22, 37), records=rec, pack_exists=True) == []


def test_bare_morning_post_does_not_hide_carousel_or_reels():
    # 2026-10-23 21:57 IST: feed, story, FB, LinkedIn and Threads were live.
    # The missing-target check listed only YouTube.
    live = "VERIFIED_LIVE"
    rec = [{"slot": s, "platform": p, "status": live} for s, p in (
        ("morning", "instagram"), ("morning", "instagram_story"), ("morning", "facebook"),
        ("generate", "linkedin"), ("generate", "threads"))]
    pending = ru.pending_targets(dt.datetime(2026, 10, 23, 21, 57), records=rec, pack_exists=True)
    for target in ("carousel", "reel_1", "reel_2", "growth_reel", "youtube"):
        assert target in pending
    assert pending != ["youtube"]
    assert "ig_feed" not in pending and "linkedin" not in pending and "threads" not in pending


def test_workflows_chain_on_due_targets_not_ledger_rows():
    wf = ROOT / ".github/workflows"
    retry = (wf / "retry-unposted.yml").read_text(encoding="utf-8")
    daily = (wf / "daily.yml").read_text(encoding="utf-8")
    assert "retry_unposted --pending" in retry
    assert "gh workflow run retry-unposted.yml" in retry
    assert "gh workflow run daily.yml" in retry and "slot=generate" in retry
    assert "DAILY_ACTIVE" in retry and 'status == \\"in_progress\\"' in retry
    assert "actions: write" in daily
    assert "gh workflow run retry-unposted.yml" in daily


def test_instagram_reel_alias_counts_as_posted():
    # The publisher writes the platform key instagram_reel for some reel paths.
    # A legacy row with no asset is the historical single reel (reel_1 only).
    rec = [{"slot": "evening", "platform": "instagram_reel", "status": "VERIFIED_LIVE"}]
    assert "reel_1" not in ru.unposted_targets(rec, 23)
    assert "reel_2" in ru.unposted_targets(rec, 23)


def _morning_settled(**ig):
    live = "VERIFIED_LIVE"
    rec = [{"slot": s, "platform": p, "status": live, "attempt_count": 1, "error": ""} for s, p in (
        ("morning", "instagram_story"), ("morning", "facebook"),
        ("generate", "linkedin"), ("generate", "youtube"), ("generate", "threads"))]
    rec.append({"slot": "morning", "platform": "instagram", "status": "FAILED",
                 "attempt_count": 3, "remote_id": "", "url": "", **ig})
    return rec


def test_pending_omits_targets_the_ledger_will_refuse():
    rec = _morning_settled(error="caption rejected by the platform")
    assert "ig_feed" not in ru.pending_targets(T(12), records=rec, pack_exists=True)


def test_pending_keeps_preflight_no_images_retryable():
    rec = _morning_settled(error="no_images")
    assert "ig_feed" in ru.pending_targets(T(12), records=rec, pack_exists=True)


def test_pending_probe_error_returns_nonzero(monkeypatch, capsys):
    import sys
    monkeypatch.setattr(ru, "pending_targets", lambda: (_ for _ in ()).throw(RuntimeError("probe broke")))
    monkeypatch.setattr(sys, "argv", ["retry_unposted.py", "--pending"])
    assert ru._cli() == 1
    assert capsys.readouterr().out.startswith("PENDING_ERROR:RuntimeError")
