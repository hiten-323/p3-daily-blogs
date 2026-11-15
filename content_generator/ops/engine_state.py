"""Engine run state lives on the ``engine-state`` branch, not on ``main``.

``main`` is protected: it accepts only pull requests whose status checks pass,
so the engine's own ``[skip ci]`` state commits were rejected (GH006, run 531 on
15 Nov 2026) and no publish slot could load the generated pack. Code still comes
from ``main``; generated content, creatives, the publishing ledger and the
learning data are written to and read from ``engine-state``.

    python -m content_generator.ops.engine_state load            # after checkout
    python -m content_generator.ops.engine_state save -m "msg"   # persist step

``load`` overlays the state files from ``origin/engine-state`` onto the main
checkout (falls back to main when the branch does not exist yet). The ledger,
published posts, lessons and jar provenance registry are merged record by
record with main's copies, so a lesson added on main by a PR is kept. It then
records a manifest of what it loaded.

``save`` copies only the files this run changed (against that manifest) into a
worktree of the current ``origin/engine-state`` tip, merges the same JSON files
with the remote copies (a posted record always beats an unposted one), prunes
dated creatives older than yesterday (IST), commits and pushes. A rejected push
(another runner saved first) is retried on the new tip.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from content_generator.ops import ledger_sync

log = logging.getLogger("engine_state")

BRANCH = os.getenv("ENGINE_STATE_BRANCH", "engine-state")
REMOTE = "origin"
TRACKING = f"refs/remotes/{REMOTE}/{BRANCH}"

# State paths the engine persists. Code never comes from the state branch.
STATE_PATTERNS = (
    ".last_run",
    "output/learning/*",
    "output/creative/*",
    "output/reports/*",
    "output/content_*.json",
    "output/blog_*",
    "output/.running*",
    "output/publish_log.json",
)
STATE_ROOTS = (".last_run", "output")

LEDGER = "output/learning/publishing_ledger.json"
POSTS = "output/learning/published_posts.json"
LESSONS = "output/learning/obstacle_lessons.json"
PROVENANCE = "output/creative/jar_provenance.json"
MERGED = (LEDGER, POSTS, LESSONS, PROVENANCE)

ENGINE_ENV = {
    "GIT_AUTHOR_NAME": "Purity Beans Engine", "GIT_AUTHOR_EMAIL": "engine@puritybeans.auto",
    "GIT_COMMITTER_NAME": "Purity Beans Engine", "GIT_COMMITTER_EMAIL": "engine@puritybeans.auto",
}


class StateError(RuntimeError):
    pass


def _git(*args: str, cwd: str | Path | None = None, check: bool = False,
         binary: bool = False, timeout: int = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ, **ENGINE_ENV)
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=not binary,
                         timeout=timeout, env=env)
    if check and res.returncode != 0:
        err = res.stderr if not binary else res.stderr.decode("utf-8", "replace")
        raise StateError(f"git {' '.join(args[:3])} failed: {str(err).strip()[:300]}")
    return res


# Scratch/lock files next to the registry are never state.
EXCLUDE_PATTERNS = ("*/.jar_provenance.*", "*.tmp", "*/__pycache__/*")


def is_state_path(path: str) -> bool:
    path = path.replace(os.sep, "/")
    if any(fnmatch.fnmatchcase(path, pat) for pat in EXCLUDE_PATTERNS):
        return False
    return any(fnmatch.fnmatchcase(path, pat) for pat in STATE_PATTERNS)


def manifest_path() -> Path:
    base = os.getenv("ENGINE_STATE_MANIFEST")
    if base:
        return Path(base)
    return Path(os.getenv("RUNNER_TEMP") or tempfile.gettempdir()) / "engine_state_manifest.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan(root: Path = Path(".")) -> dict[str, str]:
    """sha256 of every state file under root, keyed by repo-relative path."""
    out: dict[str, str] = {}
    for top in STATE_ROOTS:
        base = root / top
        if base.is_file():
            rel = top
            if is_state_path(rel):
                out[rel] = _sha(base.read_bytes())
            continue
        if not base.is_dir():
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                full = Path(dirpath) / name
                rel = full.relative_to(root).as_posix()
                if is_state_path(rel) and full.is_file():
                    out[rel] = _sha(full.read_bytes())
    return out


def remote_exists() -> bool:
    """True/False for the state branch on origin. Raises when origin is unreachable."""
    for attempt in range(3):
        res = _git("ls-remote", "--exit-code", "--heads", REMOTE, BRANCH, timeout=60)
        if res.returncode == 0:
            return True
        if res.returncode == 2:
            return False
        time.sleep(3 * (attempt + 1))
    raise StateError(f"cannot reach {REMOTE} to look up {BRANCH}")


def fetch() -> str | None:
    """Fetch the state branch; its commit SHA, or None when it does not exist."""
    if not remote_exists():
        return None
    for attempt in range(3):
        res = _git("fetch", "-q", REMOTE, f"+refs/heads/{BRANCH}:{TRACKING}", timeout=600)
        if res.returncode == 0:
            return _git("rev-parse", TRACKING, check=True).stdout.strip()
        time.sleep(5 * (attempt + 1))
    raise StateError(f"could not fetch {BRANCH}")


def _tree_files(ref: str) -> list[str]:
    res = _git("ls-tree", "-r", "-z", "--name-only", ref, "--", *STATE_ROOTS, check=True)
    return [p for p in res.stdout.split("\0") if p and is_state_path(p)]


def _blob(ref: str, path: str) -> bytes:
    return _git("show", f"{ref}:{path}", check=True, binary=True).stdout


def _load_json(raw: bytes | None):
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _read_json_file(path: Path):
    try:
        return _load_json(path.read_bytes())
    except OSError:
        return None


def merge_json(rel: str, primary, secondary):
    """Merge two copies of a mergeable state file; returns (data, writer)."""
    if rel == LEDGER:
        a = primary if isinstance(primary, dict) and isinstance(primary.get("records"), dict) else {"version": 1, "records": {}}
        b = secondary if isinstance(secondary, dict) and isinstance(secondary.get("records"), dict) else {"version": 1, "records": {}}
        return ledger_sync.merge(a, b), ledger_sync._write
    if rel == POSTS:
        a = [x for x in primary if isinstance(x, dict)] if isinstance(primary, list) else []
        b = [x for x in secondary if isinstance(x, dict)] if isinstance(secondary, list) else []
        return ledger_sync.merge_posts(a, b), ledger_sync._write_posts
    if rel == LESSONS:
        a = primary if isinstance(primary, dict) and isinstance(primary.get("lessons"), list) else {"version": 1, "lessons": []}
        b = secondary if isinstance(secondary, dict) and isinstance(secondary.get("lessons"), list) else {"version": 1, "lessons": []}
        return ledger_sync.merge_lessons(a, b), ledger_sync._write
    # Provenance registry: union, the secondary (newer) side wins per file.
    merged = dict(primary) if isinstance(primary, dict) else {}
    if isinstance(secondary, dict):
        merged.update(secondary)

    def _write(data, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return merged, _write


def write_manifest(root: Path = Path("."), source: str = "") -> dict:
    data = {"branch": BRANCH, "source": source, "files": scan(root)}
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    return data


def load(root: Path = Path(".")) -> str:
    """Overlay engine-state onto the main checkout. Returns the source used."""
    sha = fetch()
    if not sha:
        print(f"[engine-state] {BRANCH} does not exist yet; using the state committed on main")
        write_manifest(root, source="main")
        return "main"
    main_copies = {rel: _read_json_file(root / rel) for rel in MERGED}
    files = _tree_files(sha)
    for rel in files:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_blob(sha, rel))
    for rel in MERGED:
        state_copy = _read_json_file(root / rel) if rel in files else None
        main_copy = main_copies.get(rel)
        if state_copy is None and main_copy is None:
            continue
        data, writer = merge_json(rel, main_copy, state_copy)
        writer(data, root / rel)
    print(f"[engine-state] loaded {len(files)} state files from {BRANCH}@{sha[:10]} (merged ledgers with main)")
    write_manifest(root, source=f"{BRANCH}@{sha}")
    return BRANCH


def _read_manifest(root: Path) -> dict[str, str]:
    try:
        data = json.loads(manifest_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            return data["files"]
    except (OSError, ValueError):
        pass
    # No manifest (load was skipped): compare against what main's HEAD holds.
    out: dict[str, str] = {}
    for rel in _tree_files("HEAD"):
        out[rel] = _sha(_blob("HEAD", rel))
    return out


def changes(root: Path = Path(".")) -> tuple[list[str], list[str]]:
    before = _read_manifest(root)
    now = scan(root)
    changed = sorted(p for p, h in now.items() if before.get(p) != h)
    deleted = sorted(p for p in before if p not in now)
    return changed, deleted


_DATED = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def prune_creatives(root: Path, today: _dt.date | None = None) -> int:
    """Drop dated creatives older than yesterday (IST); slots only need today/yesterday."""
    if today is None:
        from zoneinfo import ZoneInfo
        today = _dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    cutoff = today - _dt.timedelta(days=1)
    removed = 0
    base = root / "output" / "creative"
    if not base.is_dir():
        return 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        m = _DATED.search(path.name)
        if not m:
            continue
        try:
            stamped = _dt.date(*(int(g) for g in m.groups()))
        except ValueError:
            continue
        if stamped < cutoff:
            path.unlink()
            removed += 1
    return removed


def _apply(root: Path, wt: Path, changed: list[str], deleted: list[str]) -> None:
    for rel in changed:
        src, dest = root / rel, wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rel in MERGED and dest.exists():
            data, writer = merge_json(rel, _read_json_file(dest), _read_json_file(src))
            writer(data, dest)
        else:
            shutil.copy2(src, dest)
    for rel in deleted:
        target = wt / rel
        if target.is_file():
            target.unlink()


def save(message: str, root: Path = Path("."), attempts: int = 5) -> bool:
    """Commit this run's state changes onto engine-state and push. True on success."""
    root = root.resolve()
    changed, deleted = changes(root)
    if not changed and not deleted:
        print("[engine-state] nothing changed this run; nothing to save")
        return True
    print(f"[engine-state] saving {len(changed)} changed and {len(deleted)} removed state files to {BRANCH}")
    for attempt in range(1, attempts + 1):
        base = fetch() or _git("rev-parse", "HEAD", cwd=root, check=True).stdout.strip()
        wt = Path(tempfile.mkdtemp(prefix="engine-state-"))
        try:
            _git("worktree", "add", "-q", "--detach", str(wt), base, cwd=root, check=True, timeout=600)
            _apply(root, wt, changed, deleted)
            prune_creatives(wt)
            present = [p for p in STATE_ROOTS if (wt / p).exists()]
            _git("add", "-f", "-A", "--", *present, cwd=wt, check=True)
            if _git("diff", "--cached", "--quiet", cwd=wt).returncode == 0:
                print("[engine-state] state already up to date on the branch")
                return True
            _git("commit", "-q", "-m", message, cwd=wt, check=True)
            push = _git("push", "-q", REMOTE, f"HEAD:refs/heads/{BRANCH}", cwd=wt, timeout=600)
            if push.returncode == 0:
                new = _git("rev-parse", "HEAD", cwd=wt).stdout.strip()
                print(f"[engine-state] pushed {BRANCH}@{new[:10]}")
                return True
            print(f"[engine-state] push rejected (attempt {attempt}/{attempts}); "
                  f"merging with the new tip and retrying: {push.stderr.strip()[:200]}")
        finally:
            _git("worktree", "remove", "--force", str(wt), cwd=root)
            shutil.rmtree(wt, ignore_errors=True)
        time.sleep(3 * attempt)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine_state")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load")
    p_save = sub.add_parser("save")
    p_save.add_argument("-m", "--message", required=True)
    sub.add_parser("changes")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "load":
            load()
            return 0
        if args.cmd == "changes":
            changed, deleted = changes()
            print(json.dumps({"changed": changed, "deleted": deleted}, indent=1))
            return 0
        return 0 if save(args.message) else 1
    except StateError as exc:
        print(f"::error::engine-state {args.cmd} failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
