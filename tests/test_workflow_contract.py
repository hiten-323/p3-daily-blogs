from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
POLICY = ROOT / "founder_policies.yaml"


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # NVIDIA is the primary LLM. A blank NVIDIA_MODEL secret must not be
    # required; the code default applies when the env value is empty.
    assert "NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}" in text
    assert "NVIDIA_MODEL: ${{ secrets.NVIDIA_MODEL }}" in text

    # Canonical production windows.
    assert "cron: '30 0 * * *'" in text
    assert "cron: '30 4 * * *'" in text
    assert "cron: '30 16 * * *'" in text

    # Manual execution must select a slot instead of inferring it from wall time.
    assert "Manual slot to execute — never infer from wall-clock time" in text
    assert "required: true" in text
    assert "- generate" in text and "- morning" in text and "- evening" in text

    # Generate is not a publication slot.
    assert "no publication expected at 06:00 IST" in text
    assert "GENERATE verified" in text

    # Publishing slots have an actual Meta preflight, before the pipeline runs.
    assert "Verify Meta publishing access" in text
    assert "graph.facebook.com/v24.0/" in text
    assert "env.FORCE_SLOT != 'generate'" in text

    # Soft Meta notice on generate (does not fail the generate slot).
    assert "Soft Meta token notice" in text or "Meta token soft-check" in text

    # Repository synchronization failures must never be swallowed.
    assert "git pull --rebase --autostash || true" not in text
    assert re.search(r"git pull --rebase --autostash\s*$", text, re.M)

    # No stale production-window references.
    assert "08:00 / 20:00" not in text
    assert "08:00/20:00" not in text

    # Extended content is a founder-policy decision, not a workflow hardcode.
    # Emergency env override is still allowed in the run step if present, but
    # the workflow must not force ENABLE_EXTENDED_CONTENT: "true".
    assert 'ENABLE_EXTENDED_CONTENT: "true"' not in text
    policy = POLICY.read_text(encoding="utf-8")
    assert "enable_extended_content:" in policy

    # Persist step must force-add learning + daily content so Git alone can
    # reconstruct state if the Actions cache disappears.
    assert "git add -f output/learning/" in text
    assert "output/content_" in text

    # EVERY TEST THE GATE INVOKES MUST EXIST.
    #
    # The gate runs before the pipeline, so a missing file fails every run
    # before anything generates or publishes — a total outage wearing the
    # costume of a safety check. This shipped once: the workflow called
    # test_workflow_contract.py and test_persistence_invariant.py while neither
    # had been written yet.
    runs_pytest = re.search(r"pytest\s[^\n]*\btests/", text)
    invoked = re.findall(r"python (tests/\w+\.py)", text)

    missing = [t for t in invoked if not (ROOT / t).is_file()]
    assert not missing, f"the gate invokes tests that do not exist: {missing}"

    # A suite nobody runs protects nothing. `pytest tests/` collects the whole
    # directory, so it satisfies this; naming files individually does not,
    # unless every file is named.
    if not runs_pytest:
        on_disk = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py")}
        unwired = sorted(on_disk - set(invoked))
        assert not unwired, f"test suites exist but are never run: {unwired}"

    # Whichever runner is used, every suite must actually EXECUTE something.
    # Ten suites were pytest-style (test_* functions, no main()); running those
    # as `python tests/x.py` merely imports them and exits 0, so they passed
    # while asserting nothing. Script-style suites therefore expose test_main()
    # and the gate uses pytest, which collects both shapes.
    for path in (ROOT / "tests").glob("test_*.py"):
        body = path.read_text(encoding="utf-8")
        collectable = ("def test_" in body)
        assert collectable, (
            f"{path.name} defines no test_* function, so pytest collects nothing "
            "from it — add test_main() if it is script-style"
        )

    print("workflow contract: PASS")


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    main()
