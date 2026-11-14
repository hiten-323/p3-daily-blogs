"""Regression contracts for the single publishing flag and safe generation dry-run."""

from pathlib import Path

from content_generator.scheduler import daily

ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_forces_all_outbound_paths_off(monkeypatch):
    monkeypatch.setattr(daily, "run_full_pipeline", lambda **kwargs: {"generated": True})
    result = daily.run_now(dry_run=True)
    assert result == {"generated": True}
    assert __import__("os").environ["DRY_RUN"] == "1"
    assert __import__("os").environ["PUBLISHING_ENABLED"] == "false"
    assert __import__("os").environ["NURTURE_ENABLED"] == "false"
    assert daily._publishing_enabled() is False


def test_dry_run_suppresses_nurture_and_founder_notifications(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    nurture = daily._do_nurture()
    founder = daily._do_founder_report({}, {}, {})
    assert nurture["reason"] == "dry_run"
    assert nurture["dispatched"] == 0
    assert founder is False


def test_daily_schedule_uses_one_default_on_publishing_flag():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    retry = (ROOT / ".github" / "workflows" / "retry-unposted.yml").read_text(encoding="utf-8")
    recovery = (ROOT / ".github" / "workflows" / "publish-recovery.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "vars.PUBLISHING_ENABLED || 'true'" in workflow
    assert "vars.PUBLISHING_ENABLED != 'false'" in workflow
    assert "vars.PUBLISHING_ENABLED != 'false'" in retry
    assert "vars.PUBLISHING_ENABLED != 'false'" in recovery
    assert "Unset or empty: publishing is **ON**" in readme
    assert "PUBLISHING_ENABLED" in readme
    assert "reel_2" not in workflow


def test_generate_dry_run_runs_pipeline_but_skips_publishing_and_commits():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "--dry-run" in workflow
    assert "github.event.inputs.dry_run == 'true' && 'false'" in workflow
    assert "github.event.inputs.dry_run != 'true'" in workflow
