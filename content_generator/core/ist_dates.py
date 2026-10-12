"""
One calendar for the content engine: Asia/Kolkata.

GitHub runners are UTC. The founder day, the content filename, and the
`date` field inside that file are the IST calendar date. Generate and the
morning/evening slots must use this helper or they disagree — a long-form
date like "October 03, 2026" used to be compared to "2026-10-03" and every
publish slot held itself for stale content.
"""
from __future__ import annotations

import datetime
import re
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)
_LONG_DATE = re.compile(rf"^({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})$", re.I)
_ISO_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def today_ist(now: datetime.datetime | None = None) -> datetime.date:
    """Calendar date in Asia/Kolkata. Naive datetimes are treated as UTC."""
    if now is None:
        return datetime.datetime.now(IST).date()
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(IST).date()


def content_date_iso(value) -> str:
    """
    Normalize a content `date` to YYYY-MM-DD.

    Accepts ISO dates, ISO datetimes, and the legacy generator form
    "October 03, 2026" / "October 3, 2026". Returns "" when the value
    is missing or not a date we can trust.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    iso = _ISO_PREFIX.match(raw)
    if iso:
        try:
            return datetime.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).isoformat()
        except ValueError:
            return ""
    long = _LONG_DATE.match(raw)
    if long:
        try:
            return datetime.datetime.strptime(
                f"{long.group(1)} {int(long.group(2))}, {long.group(3)}",
                "%B %d, %Y",
            ).date().isoformat()
        except ValueError:
            return ""
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def content_date_for_slot(slot: str, now: datetime.datetime | None = None) -> datetime.date:
    """IST day whose content a slot should load.

    GitHub often starts the 22:00 IST evening cron after midnight. That run is
    still yesterday's reel, not a request for a file the 06:00 generate has
    not written yet. A manual evening dispatch after noon stays on today.
    Morning and generate only roll back when they themselves spill past
    midnight into the next day's pre-generate window.
    """
    if now is None:
        now_ist = datetime.datetime.now(IST)
    elif now.tzinfo is None:
        now_ist = now.replace(tzinfo=datetime.timezone.utc).astimezone(IST)
    else:
        now_ist = now.astimezone(IST)
    today = now_ist.date()
    minutes = now_ist.hour * 60 + now_ist.minute
    slot_id = str(slot or "").strip().lower()
    if slot_id == "evening" and minutes < 12 * 60:
        return today - datetime.timedelta(days=1)
    if slot_id in {"morning", "generate"} and minutes < 6 * 60:
        return today - datetime.timedelta(days=1)
    return today


def asset_date(content, now: datetime.datetime | None = None) -> str:
    """Filename date for assets that belong to this content file."""
    parsed = content_date_iso(content.get("date") if isinstance(content, dict) else None)
    return parsed or today_ist(now).isoformat()


def content_matches_today(content: dict, today: datetime.date | None = None) -> tuple[bool, str]:
    """
    True when the file is today's work (or carries no date).

    A present but unparseable date is stale: publishing it would attach
    unknown copy to today's decision record.
    """
    today_iso = (today or today_ist()).isoformat()
    raw = content.get("date") if isinstance(content, dict) else None
    if raw in (None, ""):
        return True, ""
    parsed = content_date_iso(raw)
    shown = parsed or str(raw)
    if not parsed:
        return False, (
            f"stale_content — file date {raw!r} is not a recognizable date, today is {today_iso}"
        )
    if parsed != today_iso:
        return False, f"stale_content — file is dated {shown}, today is {today_iso}"
    return True, ""
