"""
Slot registry — THE definition of when the engine runs and what each run owes.

Scheduling used to be stated in three places: the cron list in daily.yml, the
FORCE_SLOT mapping beside it, and the table in scheduler/slots.py. They drifted,
and the drift was invisible because every copy described its times as
"owner-chosen": the workflow fired the publish slots at 08:00 and 20:00 IST
while slots.py documented — and the founder had chosen — 10:00 and 22:00. The
workflow is the one that actually runs, so every Instagram post went out two
hours early for as long as that disagreement existed.

Python is now the source of truth. The workflow still holds the cron lines,
because GitHub requires them there, but they are DERIVED values: test_config_drift
regenerates the expected crons and FORCE_SLOT branches from this file and fails
if the YAML has moved away. Editing the YAML alone can no longer change the
schedule silently.

To change a publishing time, edit SLOTS here, then run:

    python -m content_generator.core.slot_registry --workflow

and paste the printed cron block and FORCE_SLOT expression into daily.yml.
"""
from __future__ import annotations

# IST is UTC+5:30. Times are stated in IST because that is how the founder
# thinks about them; the cron is computed.
_IST_OFFSET_MIN = 330

SLOTS: list[dict] = [
    {
        "id":        "generate",
        "ist":       "06:13",
        "expects":   ["linkedin"],
        "purpose":   "Full pipeline: insights, revenue, generate, editorial, "
                     "images, LinkedIn/YouTube (blog off by default). Instagram + Facebook HELD.",
    },
    {
        "id":        "morning",
        "ist":       "09:53",
        "expects":   ["instagram", "facebook"],
        "purpose":   "IG carousel + FB mirror (owner-chosen time).",
    },
    {
        "id":        "evening",
        "ist":       "21:53",
        "expects":   ["instagram", "facebook"],
        "purpose":   "IG reel post + FB mirror (owner-chosen time).",
    },
]
SLOTS_BY_ID = {s["id"]: s for s in SLOTS}


def _ist_to_utc(ist: str) -> tuple[int, int]:
    hh, mm = (int(x) for x in ist.split(":"))
    total = (hh * 60 + mm - _IST_OFFSET_MIN) % (24 * 60)
    return total // 60, total % 60


def cron_for(slot_id: str) -> str:
    """The GitHub cron expression for a slot, derived from its IST time."""
    h, m = _ist_to_utc(SLOTS_BY_ID[slot_id]["ist"])
    return f"{m} {h} * * *"


def all_crons() -> list[str]:
    return [cron_for(s["id"]) for s in SLOTS]


def slot_for_cron(cron: str) -> str | None:
    for s in SLOTS:
        if cron_for(s["id"]) == cron:
            return s["id"]
    return None


def expected_platforms(slot_id: str) -> list[str]:
    return list(SLOTS_BY_ID.get(slot_id, {}).get("expects", []))


def slot_from_utc_hour(hour: int) -> str:
    """
    Which slot a given UTC hour belongs to, used when FORCE_SLOT is absent
    (a manual dispatch). Each hour maps to the most recent slot at or before it,
    derived from the registry rather than hardcoded boundaries that could
    disagree with the crons.
    """
    ordered = sorted(((_ist_to_utc(s["ist"])[0], s["id"]) for s in SLOTS))
    chosen = ordered[-1][1]          # before the first slot of the day -> last
    for start_h, slot_id in ordered:
        if hour >= start_h:
            chosen = slot_id
    return chosen


def force_slot_expression() -> str:
    """The FORCE_SLOT ternary for daily.yml, derived from the registry."""
    parts = []
    for s in SLOTS:
        parts.append(f"github.event.schedule == '{cron_for(s['id'])}' && '{s['id']}'")
    expr = parts[0]
    for p in parts[1:]:
        expr += f" || ({p}"
    expr += " || ''" + ")" * (len(parts) - 1)
    return "${{ " + expr + " }}"


def workflow_block() -> str:
    """Paste-able cron block + FORCE_SLOT line for daily.yml."""
    lines = ["  schedule:"]
    for s in SLOTS:
        h, m = _ist_to_utc(s["ist"])
        lines.append(f"    # {h:02d}:{m:02d} UTC = {s['ist']} IST — "
                     f"{s['id'].upper()} slot: {s['purpose']}")
        lines.append(f"    - cron: '{cron_for(s['id'])}'")
    lines.append("")
    lines.append(f"          FORCE_SLOT: {force_slot_expression()}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--workflow" in sys.argv:
        print(workflow_block())
    else:
        for s in SLOTS:
            h, m = _ist_to_utc(s["ist"])
            print(f"{s['id']:9} {s['ist']} IST = {h:02d}:{m:02d} UTC  "
                  f"cron={cron_for(s['id'])!r}  expects={s['expects']}")
