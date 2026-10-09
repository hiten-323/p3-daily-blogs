"""
Git persistence invariant — learning and daily content must be recoverable
from the repository without the Actions cache.

If the cache key evaporates, the next run must still find:
  - output/learning/*.json  (force-added every run)
  - output/content_YYYY-MM-DD.json (force-added every generate)

This test is structural: it asserts the workflow and generator contracts that
make that reconstruction possible. It does not invent metrics.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
GENERATOR = ROOT / "content_generator" / "pipeline" / "generator.py"


def main() -> None:
    wf = WORKFLOW.read_text(encoding="utf-8")
    gen = GENERATOR.read_text(encoding="utf-8")

    # Persist step force-adds the paths that matter.
    assert "git add -f output/learning/" in wf, "learning must be force-added to Git"
    assert re.search(r'git add -f ["\']?output/content_', wf), "daily content JSON must be force-added"

    # Push failure is fatal — publish slots cannot load unpushed content.
    assert "Could not push run artefacts" in wf or "publish slots cannot load" in wf

    # Generator writes content_{date}.json under output/ — the same path the
    # workflow force-adds and the morning/evening slots load.
    assert 'content_{date_str}.json' in gen or 'f"content_{date_str}.json"' in gen

    # Extended content is resolved via policy helper, not a bare env default.
    assert "_extended_content_enabled" in gen
    assert "enable_extended_content" in gen

    # Publishing ledger and lock state must persist even when a platform fails,
    # otherwise a later recovery run can forget an attempt and duplicate a post.
    persist_block = re.search(r"Persist validated state[\s\S]{0,300}", wf)
    assert persist_block and "always()" in persist_block.group(0), (
        "publishing state must persist after both successful and failed attempts"
    )
    assert "github.event.inputs.dry_run != 'true'" in persist_block.group(0)

    # Diagnostics are operational evidence, not the source of truth. Artifact
    # exhaustion or an upload outage must therefore never turn a valid run into
    # a failed pipeline or prevent Git persistence.
    upload_block = re.search(r"Upload run diagnostics \(best effort\)([\s\S]{0,500}?)Persist validated state", wf)
    assert upload_block, "best-effort diagnostics step must remain adjacent to persistence"
    upload_text = upload_block.group(1)
    assert re.search(r"if:\s*always\(\)", upload_text), "diagnostics must run on both success and failure"
    assert re.search(r"continue-on-error:\s*true", upload_text), "diagnostics upload must never block persistence"

    print("persistence invariant: PASS")


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    main()
