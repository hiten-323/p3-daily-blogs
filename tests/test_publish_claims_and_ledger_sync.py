import subprocess
from pathlib import Path

import pytest

from content_generator.ops import ledger_sync
from content_generator.publisher import publish_claim

ROOT = Path(__file__).resolve().parents[1]


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def clone(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    led = work / "output/learning/publishing_ledger.json"
    led.parent.mkdir(parents=True)
    led.write_text('{"version": 1, "records": {}}\n')
    _git(work, "add", ".")
    _git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    _git(work, "push", "-q", "origin", "main")
    monkeypatch.chdir(work)
    monkeypatch.setenv("PUBLISH_CLAIMS", "1")
    return work


def test_only_one_run_wins_a_claim(clone):
    ok1, ref = publish_claim.acquire("2026-10-16", "evening", "instagram_video")
    ok2, why = publish_claim.acquire("2026-10-16", "evening", "instagram_video")
    assert ok1 and ref.startswith("refs/publish-claims/")
    assert not ok2 and why == "claimed_by_other_run"
    publish_claim.release(ref)
    ok3, _ = publish_claim.acquire("2026-10-16", "evening", "instagram_video")
    assert ok3


def test_remote_posted_record_blocks(clone):
    led = clone / "output/learning/publishing_ledger.json"
    led.write_text('{"version":1,"records":{"2026-10-16|evening|instagram_video|x":'
                   '{"content_date":"2026-10-16","slot":"evening","platform":"instagram_video","status":"VERIFIED_LIVE"}}}')
    _git(clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "posted")
    _git(clone, "push", "-q", "origin", "main")
    ok, why = publish_claim.acquire("2026-10-16", "evening", "instagram_video")
    assert not ok and why == "already_published_remote"


def test_disabled_outside_actions(monkeypatch):
    monkeypatch.delenv("PUBLISH_CLAIMS", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert publish_claim.acquire("2026-10-16", "evening", "instagram") == (True, "")


def test_ledger_merge_never_unposts():
    live = {"status": "VERIFIED_LIVE", "updated_at": "2026-10-16T01:00:00+00:00"}
    later_fail = {"status": "FAILED", "updated_at": "2026-10-16T02:00:00+00:00"}
    m = ledger_sync.merge({"records": {"k": live}}, {"records": {"k": later_fail, "j": later_fail}})
    assert m["records"]["k"]["status"] == "VERIFIED_LIVE"
    assert "j" in m["records"]
    newer = ledger_sync.merge({"records": {"k": {"status": "FAILED", "updated_at": "1"}}},
                              {"records": {"k": {"status": "SKIPPED", "updated_at": "2"}}})
    assert newer["records"]["k"]["status"] == "SKIPPED"


def test_workflows_use_separate_groups_and_ledger_sync():
    wf = ROOT / ".github/workflows"
    daily = (wf / "daily.yml").read_text()
    retry = (wf / "retry-unposted.yml").read_text()
    assert "group: purity-beans-daily" in daily
    assert "group: purity-beans-retry" in retry
    for t in (daily, retry, (wf / "publish-recovery.yml").read_text()):
        assert "ledger_sync save" in t and "ledger_sync restore" in t



def test_release_never_deletes_a_claim_replaced_by_another_runner(clone, monkeypatch):
    ok, ref = publish_claim.acquire("2026-10-16", "evening", "instagram_video")
    assert ok
    original_sha = publish_claim._OWNED_CLAIMS[ref]

    # Simulate another runner replacing this ref after our claim was acquired.
    replacement = publish_claim._claim_commit()
    _git(clone, "push", "-q", "--force", "origin", f"{replacement}:{ref}")
    publish_claim.release(ref)

    remote_sha = _git(clone, "ls-remote", "origin", ref).split()[0]
    assert remote_sha == replacement
    assert remote_sha != original_sha


def test_claim_recovery_uses_compare_and_swap_not_unconditional_force(clone):
    import inspect

    source = inspect.getsource(publish_claim.acquire)
    assert "--force-with-lease=" in source
    assert '"--force", "origin"' not in source
