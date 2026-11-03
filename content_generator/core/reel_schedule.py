"""Reel schedule — which Instagram reel posts in which slot, and how many a day.

Owner decision (Hiten, 2 Nov 2026, 11:04 PM IST): three reels a day is too
much; post "Two reels, spread across the day".

From 3 Nov 2026:

  growth_reel  morning slot (09:53 IST)   the 30-day sales push reel (runs to 20 Nov 2026)
  reel_1       evening slot (21:53 IST)
  reel_2       never published (retired)

Rules every publish path follows (cron slots, retry-unposted, publish-recovery
and the after-midnight backstop):

* a slot publishes only its own reel and never substitutes another one;
* at most MAX_REELS_PER_DAY reels go live for one content day;
* two reels never go out together: a reel is held when another reel for the
  same content day went live less than MIN_REEL_GAP_HOURS ago;
* the morning reel is not chased after GROWTH_REEL_CUTOFF_IST, so a late
  retry can never put it next to the evening reel, and it is never backfilled
  after midnight.
"""
from __future__ import annotations

import datetime as dt

REEL_SLOT: dict[str, str] = {
    "growth_reel": "morning",
    "reel_1": "evening",
}
PUBLISHED_REELS: tuple[str, ...] = ("growth_reel", "reel_1")
RETIRED_REELS: frozenset[str] = frozenset({"reel_2"})
ALL_REEL_LABELS: frozenset[str] = frozenset(PUBLISHED_REELS) | RETIRED_REELS
MAX_REELS_PER_DAY = 2
MIN_REEL_GAP_HOURS = 3
# The morning reel is due from the morning slot until this IST time.
MORNING_REEL_CUTOFF_IST = (18, 0)
GROWTH_REEL_CUTOFF_IST = (18, 0)
REEL_PLATFORMS: tuple[str, ...] = ("instagram_reel", "instagram_video", "instagram")


def reel_for_slot(slot: str) -> str | None:
    """The single reel a slot owns, or None."""
    for name, owner in REEL_SLOT.items():
        if owner == slot:
            return name
    return None


def slot_for_reel(name: str) -> str | None:
    return REEL_SLOT.get(name)


def reel_window_open(name: str, ist_hour: int, ist_minute: int = 0) -> bool:
    """False once a morning reel is past its cutoff for the day."""
    if REEL_SLOT.get(name) == "morning":
        return (ist_hour, ist_minute) < MORNING_REEL_CUTOFF_IST
    return name in REEL_SLOT


def _record_time(record: dict) -> dt.datetime | None:
    for key in ("verified_at", "updated_at", "last_attempt_at"):
        raw = str(record.get(key) or "").strip()
        if not raw:
            continue
        try:
            stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp
    return None


def posted_reels(records: list[dict], posted_states) -> dict[str, dt.datetime | None]:
    """Reels already live for one content day, in any slot: asset -> time.

    A legacy evening row with no asset is reel_1, as the ledger has always read it.
    """
    out: dict[str, dt.datetime | None] = {}
    for record in records or []:
        if record.get("status") not in posted_states:
            continue
        platform = str(record.get("platform") or "").lower()
        if platform not in REEL_PLATFORMS:
            continue
        asset = str(record.get("asset") or "").strip()
        if not asset and record.get("slot") == "evening":
            asset = "reel_1"
        if asset not in ALL_REEL_LABELS:
            continue
        out[asset] = _record_time(record)
    return out


def reel_block_reason(name: str, records: list[dict], posted_states,
                      now_utc: dt.datetime | None = None) -> str:
    """Why this reel must not publish now ("" when it may)."""
    if name in RETIRED_REELS:
        return "reel_retired — two reels a day (owner, 2 Nov 2026)"
    if name not in REEL_SLOT:
        return f"reel_not_scheduled — {name}"
    live = posted_reels(records, posted_states)
    if name in live:
        return "already_published"
    if len(live) >= MAX_REELS_PER_DAY:
        return f"daily_reel_cap — {len(live)} reels already live (max {MAX_REELS_PER_DAY})"
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    gap = dt.timedelta(hours=MIN_REEL_GAP_HOURS)
    for other, when in live.items():
        if when is not None and abs(now_utc - when) < gap:
            return (f"reel_gap — {other} went live {when.isoformat()}; reels are spread "
                    f"at least {MIN_REEL_GAP_HOURS}h apart")
    return ""
