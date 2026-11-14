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

def test_nine_piece_dry_run_holds_story_when_visual_renderer_does_not_pass(monkeypatch):
    from content_generator.core import editorial_engine, publish_bar, product_truth, process_match
    from content_generator.creative import story_video

    labels = {"instagram_post", "carousel", "growth_reel", "reel_1",
              "facebook_post", "threads_post", "linkedin_post", "yt_short"}
    monkeypatch.setattr(editorial_engine, "get_valid_assets", lambda content: labels)
    monkeypatch.setattr(publish_bar, "quality_block", lambda piece, label: "")
    monkeypatch.setattr(product_truth, "featured_product_name", lambda content: "purica")
    monkeypatch.setattr(product_truth, "piece_copy_text", lambda piece: "Smooth instant coffee")
    monkeypatch.setattr(product_truth, "asset_product_truth_findings", lambda piece, featured=None: [])
    monkeypatch.setattr(process_match, "process_match_findings", lambda text, featured=None: [])
    monkeypatch.setattr(story_video, "build_story_video", lambda **kwargs: None)
    monkeypatch.setattr(daily, "_remember_obstacle", lambda *a, **k: None)

    content = {
        "day_number": 340,
        "instagram_post": {}, "stories": {"story_1": {}}, "carousel": {},
        "growth_reel": {}, "reels": [{}], "facebook_post": {},
        "threads_post": {}, "linkedin_post": {}, "yt_short": {},
    }
    report = daily.dry_run_asset_report(content)
    assert report["passed"] == 8
    assert report["held"] == 1
    story = next(row for row in report["pieces"] if row["piece"] == "ig_story")
    assert story["status"] == "HOLD"
    assert "story_visual_gate_hold_or_render_failed" in story["reasons"]
