"""Publish slots follow the content day, including a delayed evening cron."""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from content_generator.core.ist_dates import IST, asset_date, content_date_for_slot
from content_generator.scheduler.run_lock import RunLock


def _ist(year, month, day, hour, minute) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_evening_after_midnight_still_owns_yesterday():
    now = _ist(2026, 10, 11, 1, 45)
    assert content_date_for_slot("evening", now) == datetime.date(2026, 10, 10)


def test_evening_at_the_slot_stays_on_today():
    now = _ist(2026, 10, 11, 22, 5)
    assert content_date_for_slot("evening", now) == datetime.date(2026, 10, 11)


def test_manual_afternoon_evening_stays_on_today():
    now = _ist(2026, 10, 11, 15, 0)
    assert content_date_for_slot("evening", now) == datetime.date(2026, 10, 11)


def test_morning_before_generate_rolls_back():
    now = _ist(2026, 10, 12, 3, 0)
    assert content_date_for_slot("morning", now) == datetime.date(2026, 10, 11)


def test_morning_after_generate_stays_on_today():
    now = _ist(2026, 10, 11, 16, 0)
    assert content_date_for_slot("morning", now) == datetime.date(2026, 10, 11)


def test_asset_date_prefers_the_content_file():
    assert asset_date({"date": "October 10, 2026"}) == "2026-10-10"
    assert asset_date({}) == datetime.datetime.now(IST).date().isoformat()


def test_run_lock_stamps_the_content_day(tmp_path):
    path = tmp_path / ".running_evening"
    lock = RunLock(lock_path=str(path), for_date=datetime.date(2026, 10, 10))
    lock.__enter__()
    assert path.read_text(encoding="utf-8").startswith("2026-10-10|")
    lock.release()
