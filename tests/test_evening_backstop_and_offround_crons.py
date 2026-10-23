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


def test_reel_counted_missing_without_evening_records():
    assert "reel_1" in ru.unposted_targets([], 23)
    assert "reel_2" in ru.unposted_targets([], 23)
    rec = [{"slot": "evening", "platform": "instagram", "status": "VERIFIED_LIVE"}]
    assert "reel_1" not in ru.unposted_targets(rec, 23)
    assert "reel_2" in ru.unposted_targets(rec, 23)
