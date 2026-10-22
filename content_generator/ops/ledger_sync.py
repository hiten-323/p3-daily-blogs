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
POSTS = Path("output/learning/published_posts.json")
POSTS_STASH = Path(tempfile.gettempdir()) / "published_posts.local.json"
LESSONS = Path("output/learning/obstacle_lessons.json")
LESSONS_STASH = Path(tempfile.gettempdir()) / "obstacle_lessons.local.json"
_RANK = {"VERIFIED_LIVE": 5, "PUBLISHED_UNVERIFIED": 4, "UNCERTAIN": 3, "PUBLISHING": 2}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "records": {}}


def _read_posts(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except (OSError, ValueError):
        pass
    return []


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


def merge_posts(base: list[dict], other: list[dict]) -> list[dict]:
    """Merge published_posts.json entries keyed by media_id, preserving snapshots, retry counts, and observations."""
    out_map: dict[str, dict] = {}
    ordered_keys: list[str] = []

    def _key(p: dict) -> str:
        return str(p.get("media_id") or p.get("asset_id") or id(p))

    for p in base:
        if isinstance(p, dict):
            k = _key(p)
            out_map[k] = dict(p)
            ordered_keys.append(k)

    for p in other:
        if not isinstance(p, dict):
            continue
        k = _key(p)
        if k not in out_map:
            out_map[k] = dict(p)
            ordered_keys.append(k)
        else:
            cur = out_map[k]
            # 1. insights_recorded: True beats False
            if p.get("insights_recorded"):
                cur["insights_recorded"] = True

            # 2. measurement_snapshots: merge and deduplicate by window
            cur_snaps = {str(s.get("window")): s for s in (cur.get("measurement_snapshots") or []) if isinstance(s, dict)}
            for s in (p.get("measurement_snapshots") or []):
                if isinstance(s, dict):
                    w = str(s.get("window"))
                    if w not in cur_snaps or (s.get("views") is not None and cur_snaps[w].get("views") is None):
                        cur_snaps[w] = s
            cur["measurement_snapshots"] = list(cur_snaps.values())

            # 3. fetch_attempts_by_window: preserve max retry counts
            cur_attempts = dict(cur.get("fetch_attempts_by_window") or {})
            for w, cnt in (p.get("fetch_attempts_by_window") or {}).items():
                cur_attempts[w] = max(cur_attempts.get(w, 0), cnt)
            cur["fetch_attempts_by_window"] = cur_attempts

            # 4. failed_windows: union
            cur_failed = set(cur.get("failed_windows") or []) | set(p.get("failed_windows") or [])
            cur["failed_windows"] = sorted(cur_failed)

            # 5. preserve non-empty metadata
            for field in ("hook", "topic", "format", "hashtags", "track", "platform", "published_at",
                          "kpi_at_creation", "policy_version", "attention_mechanism", "scroller_state",
                          "psychology_frame", "hook_strategy", "payoff_type", "decision_version"):
                if not cur.get(field) and p.get(field):
                    cur[field] = p[field]

    return [out_map[k] for k in ordered_keys]


def _write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_posts(data: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_lessons(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("lessons"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "lessons": []}


def merge_lessons(base: dict, other: dict) -> dict:
    """Keep the higher count for each lesson id and preserve a fix either side learned."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for src in list(base.get("lessons") or []) + list(other.get("lessons") or []):
        if not isinstance(src, dict):
            continue
        lid = str(src.get("id") or "")
        if not lid:
            continue
        if lid not in by_id:
            by_id[lid] = dict(src)
            order.append(lid)
            continue
        cur = by_id[lid]
        winner = src if int(src.get("count") or 0) >= int(cur.get("count") or 0) else cur
        loser = cur if winner is src else src
        merged = dict(winner)
        if not merged.get("fix") and loser.get("fix"):
            merged["fix"] = loser["fix"]
        if str(loser.get("last_seen") or "") > str(merged.get("last_seen") or ""):
            merged["last_seen"] = loser["last_seen"]
        first = [str(item.get("first_seen") or "") for item in (loser, merged) if item.get("first_seen")]
        if first:
            merged["first_seen"] = min(first)
        by_id[lid] = merged
    return {"version": 1, "lessons": [by_id[key] for key in order]}


def save() -> None:
    if LEDGER.exists():
        _write(_read(LEDGER), STASH)
    if POSTS.exists():
        _write_posts(_read_posts(POSTS), POSTS_STASH)
    if LESSONS.exists():
        _write(_read_lessons(LESSONS), LESSONS_STASH)
    subprocess.run(["git", "checkout", "HEAD", "--", str(LEDGER)], check=False)
    subprocess.run(["git", "checkout", "HEAD", "--", str(POSTS)], check=False)
    subprocess.run(["git", "checkout", "HEAD", "--", str(LESSONS)], check=False)


def restore() -> None:
    if STASH.exists():
        _write(merge(_read(LEDGER), _read(STASH)), LEDGER)
    if POSTS_STASH.exists():
        _write_posts(merge_posts(_read_posts(POSTS), _read_posts(POSTS_STASH)), POSTS)
    if LESSONS_STASH.exists():
        _write(merge_lessons(_read_lessons(LESSONS), _read_lessons(LESSONS_STASH)), LESSONS)


if __name__ == "__main__":
    {"save": save, "restore": restore}[sys.argv[1]]()

