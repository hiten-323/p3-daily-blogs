"""Keep publishing_ledger.json consistent when several workflows push.

daily.yml and retry-unposted.yml run in separate concurrency groups, so both
can commit the ledger. A plain `git pull --rebase --autostash` would conflict
on the JSON file or let one runner's copy overwrite the other's records.

    python -m content_generator.ops.ledger_sync save     # before git pull
    python -m content_generator.ops.ledger_sync restore  # after git pull

`save` stashes this run's ledger outside the repo and resets the file to HEAD
so the pull is clean; `restore` merges it record-by-record into whatever the
pull brought in. A posted record always beats an unposted one, so a merge can
never make a live post look unposted (which could trigger a duplicate).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

LEDGER = Path("output/learning/publishing_ledger.json")
STASH = Path(tempfile.gettempdir()) / "publishing_ledger.local.json"
_RANK = {"VERIFIED_LIVE": 5, "PUBLISHED_UNVERIFIED": 4, "UNCERTAIN": 3, "PUBLISHING": 2}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "records": {}}


def _pick(a: dict, b: dict) -> dict:
    ra, rb = _RANK.get(a.get("status"), 0), _RANK.get(b.get("status"), 0)
    if ra != rb:
        return a if ra > rb else b
    return a if str(a.get("updated_at", "")) >= str(b.get("updated_at", "")) else b


def merge(base: dict, other: dict) -> dict:
    out = dict(base)
    records = dict(base.get("records", {}))
    for key, rec in other.get("records", {}).items():
        if not isinstance(rec, dict):
            continue
        cur = records.get(key)
        records[key] = rec if not isinstance(cur, dict) else _pick(cur, rec)
    out["records"] = records
    return out


def _write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def save() -> None:
    if LEDGER.exists():
        _write(_read(LEDGER), STASH)
    subprocess.run(["git", "checkout", "HEAD", "--", str(LEDGER)], check=False)


def restore() -> None:
    if not STASH.exists():
        return
    _write(merge(_read(LEDGER), _read(STASH)), LEDGER)


if __name__ == "__main__":
    {"save": save, "restore": restore}[sys.argv[1]]()
