"""Cross-run publish claims.

daily.yml and retry-unposted.yml run in separate concurrency groups, so two
runners can hold the same day at once. Each runner has its own copy of the
ledger, so the ledger alone cannot stop both from posting. Before a publish we
create a git ref ``refs/publish-claims/<date>/<slot>/<platform>`` on origin.
Creating a ref without --force is atomic on GitHub: exactly one runner wins.

* success: the claim is kept, so a runner that has not yet pulled the
  committed ledger still cannot post the same key again;
* clear failure: the claim is released, so a later retry may publish;
* crash mid-publish: the claim stays (an uncertain outcome counts as posted,
  as in the ledger). A claim older than PUBLISH_CLAIM_STALE_MIN is treated as
  abandoned only when origin's ledger shows no posted record for the key.

Active only inside GitHub Actions (or PUBLISH_CLAIMS=1); PUBLISH_CLAIMS=0
disables it. Local runs and tests are unaffected.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import uuid

log = logging.getLogger(__name__)
# Only the process that created/took over a claim may release that exact SHA.
_OWNED_CLAIMS: dict[str, str] = {}
_STALE_MIN = int(os.getenv("PUBLISH_CLAIM_STALE_MIN", "180"))
_POSTED = ("VERIFIED_LIVE", "PUBLISHED_UNVERIFIED", "UNCERTAIN")
_LEDGER = "output/learning/publishing_ledger.json"


def enabled() -> bool:
    flag = os.getenv("PUBLISH_CLAIMS", "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    # Never touch origin from the test suite, even when CI sets GITHUB_ACTIONS.
    return os.getenv("GITHUB_ACTIONS") == "true" and not os.getenv("PYTEST_CURRENT_TEST")


def ref_for(date: str, slot: str, platform: str, asset: str = "") -> str:
    safe = lambda s: re.sub(r"[^A-Za-z0-9._-]", "_", str(s))
    if asset:
        return f"refs/publish-claims/{safe(date)}/{safe(slot)}/{safe(platform)}/{safe(asset)}"
    return f"refs/publish-claims/{safe(date)}/{safe(slot)}/{safe(platform)}"


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout)


def _claim_commit() -> str:
    tree = subprocess.run(["git", "hash-object", "-t", "tree", "-w", "--stdin"], input="",
                       capture_output=True, text=True, timeout=30).stdout.strip()
    env = dict(os.environ, GIT_AUTHOR_NAME="Purity Beans Engine", GIT_AUTHOR_EMAIL="engine@puritybeans.auto",
               GIT_COMMITTER_NAME="Purity Beans Engine", GIT_COMMITTER_EMAIL="engine@puritybeans.auto")
    out = subprocess.run(["git", "commit-tree", tree, "-m",
                          f"publish-claim {int(time.time())} run={os.getenv('GITHUB_RUN_ID', '')} nonce={uuid.uuid4().hex}"],
                         capture_output=True, text=True, timeout=30, env=env)
    return out.stdout.strip()


def _remote_posted(date: str, slot: str, platform: str, asset: str = "") -> bool:
    if _git("fetch", "-q", "origin", "main").returncode != 0:
        return True  # cannot prove it is free: fail closed
    show = _git("show", f"origin/main:{_LEDGER}")
    try:
        recs = json.loads(show.stdout).get("records", {})
    except Exception:
        return True
    for r in recs.values():
        if not isinstance(r, dict):
            continue
        if not str(r.get("content_date", "")).startswith(date):
            continue
        if r.get("slot") != slot:
            continue
        if str(r.get("platform", "")).lower() != platform.lower():
            continue
        if r.get("status") not in _POSTED:
            continue
        rec_asset = str(r.get("asset") or "").strip()
        if asset:
            if rec_asset:
                if rec_asset != asset:
                    continue
            else:
                if asset not in ("instagram_post", "reel_1"):
                    continue
        return True
    return False


def _claim_details(ref: str) -> tuple[float | None, str | None]:
    """Return age and observed SHA after fetching; SHA is used for CAS takeover."""
    if _git("fetch", "-q", "origin", f"+{ref}:{ref}").returncode != 0:
        return None, None
    observed = _git("rev-parse", ref).stdout.strip()
    if not observed:
        return None, None
    msg = _git("log", "-1", "--format=%s", ref).stdout
    m = re.search(r"publish-claim (\d+)", msg)
    return ((time.time() - int(m.group(1))) / 60 if m else None, observed)


def acquire(date: str, slot: str, platform: str, asset: str = "") -> tuple[bool, str]:
    """(True, ref) when this run may publish; (False, reason) otherwise."""
    if not enabled():
        return True, ""
    ref = ref_for(date, slot, platform, asset=asset)
    try:
        if _remote_posted(date, slot, platform, asset=asset):
            return False, "already_published_remote"
        sha = _claim_commit()
        if not sha:
            return False, "claim_unavailable"
        if _git("push", "-q", "origin", f"{sha}:{ref}").returncode == 0:
            _OWNED_CLAIMS[ref] = sha
            return True, ref
        age, observed_sha = _claim_details(ref)
        if age is not None and observed_sha and age >= _STALE_MIN and not _remote_posted(date, slot, platform, asset=asset):
            # Compare-and-swap: takeover succeeds only if the remote ref still
            # points at the exact stale SHA observed above. Never unconditional force-push.
            lease = f"--force-with-lease={ref}:{observed_sha}"
            if _git("push", "-q", lease, "origin", f"{sha}:{ref}").returncode == 0:
                _OWNED_CLAIMS[ref] = sha
                log.warning("[publish-claim] took over stale claim %s (%.0f min)", ref, age)
                return True, ref
        return False, "claimed_by_other_run"
    except Exception as exc:  # fail closed: never risk a duplicate post
        log.warning("[publish-claim] claim error for %s: %s", ref, exc)
        return False, "claim_unavailable"


def release(ref: str) -> None:
    """Release only the exact claim SHA acquired by this process."""
    if not ref:
        return
    owned_sha = _OWNED_CLAIMS.get(ref)
    if not owned_sha:
        log.warning("[publish-claim] refusing to release claim not owned by this process: %s", ref)
        return
    try:
        lease = f"--force-with-lease={ref}:{owned_sha}"
        result = _git("push", "-q", lease, "origin", f":{ref}")
        if result.returncode == 0:
            _OWNED_CLAIMS.pop(ref, None)
        else:
            _OWNED_CLAIMS.pop(ref, None)
            log.warning("[publish-claim] release skipped; remote claim changed for %s", ref)
    except Exception as exc:
        log.warning("[publish-claim] release failed for %s: %s", ref, exc)
