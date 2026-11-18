"""Engine run state is saved to / loaded from the engine-state branch (main is protected)."""
import json
import subprocess
import datetime as dt
from pathlib import Path

import pytest

from content_generator.ops import engine_state
from content_generator.publisher import publish_claim

ROOT = Path(__file__).resolve().parents[1]
LED = "output/learning/publishing_ledger.json"
LESSONS = "output/learning/obstacle_lessons.json"


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _write(root, rel, data):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if not isinstance(data, str) else data)


@pytest.fixture
def origin(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    _write(seed, LED, {"version": 1, "records": {"old": {"status": "VERIFIED_LIVE", "content_date": "2026-11-14"}}})
    _write(seed, LESSONS, {"version": 1, "lessons": [{"id": "main-lesson", "count": 1}]})
    _write(seed, "output/creative/jar_provenance.json", {"a.jpg": {"source": "real_jar"}})
    _write(seed, "content_generator/code.py", "print('code')\n")
    _git(seed, "add", "-f", ".")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    _git(seed, "push", "-q", "origin", "main")
    return origin


def _runner(tmp_path, origin, name, monkeypatch):
    work = tmp_path / name
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    monkeypatch.chdir(work)
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / f"{name}.manifest.json"))
    return work


def _branch_file(origin, rel):
    return subprocess.run(["git", "--git-dir", str(origin), "show", f"engine-state:{rel}"],
                          capture_output=True, text=True).stdout


def test_first_save_creates_branch_and_leaves_main_alone(tmp_path, origin, monkeypatch):
    work = _runner(tmp_path, origin, "gen", monkeypatch)
    assert engine_state.load(Path(".")) == "main"
    _write(work, "output/content_2026-11-16.json", {"day": 319})
    led = json.loads((work / LED).read_text())
    led["records"]["new"] = {"status": "VERIFIED_LIVE", "content_date": "2026-11-16"}
    _write(work, LED, led)
    _write(work, "output/scratch.log", "not state")
    assert engine_state.save("chore: state [skip ci]", Path("."))
    assert json.loads(_branch_file(origin, "output/content_2026-11-16.json")) == {"day": 319}
    assert "new" in json.loads(_branch_file(origin, LED))["records"]
    assert _branch_file(origin, "output/scratch.log") == ""
    main_files = _git(work, "ls-tree", "-r", "--name-only", "origin/main")
    assert "output/content_2026-11-16.json" not in main_files


def test_slot_loads_state_and_keeps_lessons_added_on_main(tmp_path, origin, monkeypatch):
    gen = _runner(tmp_path, origin, "gen", monkeypatch)
    engine_state.load(Path("."))
    _write(gen, "output/content_2026-11-16.json", {"day": 319})
    _write(gen, LESSONS, {"version": 1, "lessons": [{"id": "main-lesson", "count": 1},
                                                     {"id": "engine-lesson", "count": 2}]})
    assert engine_state.save("state", Path("."))

    # A PR adds a lesson on main after the engine saved.
    pr = tmp_path / "pr"
    subprocess.run(["git", "clone", "-q", str(origin), str(pr)], check=True)
    _write(pr, LESSONS, {"version": 1, "lessons": [{"id": "main-lesson", "count": 1},
                                                    {"id": "pr-lesson", "count": 1}]})
    _git(pr, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "lesson")
    _git(pr, "push", "-q", "origin", "main")

    slot = _runner(tmp_path, origin, "slot", monkeypatch)
    assert engine_state.load(Path(".")) == "engine-state"
    assert json.loads((slot / "output/content_2026-11-16.json").read_text()) == {"day": 319}
    ids = {x["id"] for x in json.loads((slot / LESSONS).read_text())["lessons"]}
    assert ids == {"main-lesson", "engine-lesson", "pr-lesson"}
    assert (slot / "content_generator/code.py").exists()


def test_concurrent_runners_never_lose_ledger_records(tmp_path, origin, monkeypatch):
    a = _runner(tmp_path, origin, "a", monkeypatch)
    engine_state.load(Path("."))
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / "b.manifest.json"))
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True)
    monkeypatch.chdir(b)
    engine_state.load(Path("."))

    for root, key, status in ((a, "ig", "VERIFIED_LIVE"), (b, "fb", "FAILED")):
        led = json.loads((root / LED).read_text())
        led["records"][key] = {"status": status, "updated_at": "2026-11-16T01:00:00Z"}
        _write(root, LED, led)

    monkeypatch.chdir(a)
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / "a.manifest.json"))
    assert engine_state.save("a", Path("."))
    monkeypatch.chdir(b)
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / "b.manifest.json"))
    assert engine_state.save("b", Path("."))
    recs = json.loads(_branch_file(origin, LED))["records"]
    assert recs["ig"]["status"] == "VERIFIED_LIVE" and "fb" in recs and "old" in recs


def test_untouched_files_do_not_overwrite_newer_branch_copies(tmp_path, origin, monkeypatch):
    a = _runner(tmp_path, origin, "a", monkeypatch)
    engine_state.load(Path("."))
    _write(a, "output/content_2026-11-16.json", {"v": 1})
    assert engine_state.save("v1", Path("."))

    slow = _runner(tmp_path, origin, "slow", monkeypatch)
    engine_state.load(Path("."))
    monkeypatch.chdir(a)
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / "a.manifest.json"))
    engine_state.load(Path("."))
    _write(a, "output/content_2026-11-16.json", {"v": 2})
    assert engine_state.save("v2", Path("."))

    monkeypatch.chdir(slow)
    monkeypatch.setenv("ENGINE_STATE_MANIFEST", str(tmp_path / "slow.manifest.json"))
    _write(slow, "output/publish_log.json", {"x": 1})
    assert engine_state.save("slow", Path("."))
    assert json.loads(_branch_file(origin, "output/content_2026-11-16.json")) == {"v": 2}


def test_deletions_and_prune_reach_the_branch(tmp_path, origin, monkeypatch):
    work = _runner(tmp_path, origin, "gen", monkeypatch)
    engine_state.load(Path("."))
    # Keep one dated creative newer than the test clock so save() has a real state change.
    _write(work, "output/creative/reel_2026-11-19.jpg", "img")
    _write(work, "output/creative/old_2026-11-01.jpg", "img")
    _write(work, "output/creative/.jar_provenance.lock", "x")
    assert engine_state.save("s", Path("."))
    # save() pushes through a detached worktree; refresh this clone's remote-tracking ref before inspecting it.
    _git(work, "fetch", "-q", "origin", "+refs/heads/engine-state:refs/remotes/origin/engine-state")
    files = _git(work, "ls-tree", "-r", "--name-only", "origin/engine-state")
    assert "output/creative/old_2026-11-01.jpg" not in files  # pruned (older than yesterday)
    assert ".jar_provenance.lock" not in files
    assert "output/creative/reel_2026-11-19.jpg" in files
    engine_state.load(Path("."))
    (work / "output/creative/reel_2026-11-19.jpg").unlink()
    assert engine_state.save("d", Path("."))
    _git(work, "fetch", "-q", "origin", "engine-state")
    files = _git(work, "ls-tree", "-r", "--name-only", "origin/engine-state")
    assert "output/creative/reel_2026-11-19.jpg" not in files


def test_prune_keeps_today_yesterday_and_undated(tmp_path):
    for name in ("a_2026-11-16.jpg", "b_2026-11-15.jpg", "c_2026-11-14.jpg", "jar_provenance.json"):
        _write(tmp_path, f"output/creative/{name}", "x")
    assert engine_state.prune_creatives(tmp_path, today=dt.date(2026, 11, 16)) == 1
    left = sorted(p.name for p in (tmp_path / "output/creative").iterdir())
    assert left == ["a_2026-11-16.jpg", "b_2026-11-15.jpg", "jar_provenance.json"]


def test_post_recorded_on_engine_state_blocks_duplicate(tmp_path, origin, monkeypatch):
    work = _runner(tmp_path, origin, "gen", monkeypatch)
    monkeypatch.setenv("PUBLISH_CLAIMS", "1")
    engine_state.load(Path("."))
    led = json.loads((work / LED).read_text())
    led["records"]["k"] = {"content_date": "2026-11-16", "slot": "evening",
                           "platform": "instagram_video", "status": "VERIFIED_LIVE"}
    _write(work, LED, led)
    assert engine_state.save("posted", Path("."))
    ok, why = publish_claim.acquire("2026-11-16", "evening", "instagram_video")
    assert not ok and why == "already_published_remote"


def test_workflows_load_and_save_engine_state():
    wf = ROOT / ".github/workflows"
    for name in ("daily.yml", "retry-unposted.yml", "publish-recovery.yml"):
        text = (wf / name).read_text()
        assert "content_generator.ops.engine_state load" in text, name
        assert "content_generator.ops.engine_state save" in text, name
        # Nothing pushes or pulls main any more; main only takes PRs.
        assert "git push" not in text and "git pull" not in text, name
        assert text.index("engine_state load") < text.index("engine_state save"), name
