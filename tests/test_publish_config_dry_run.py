"""Regression contracts for the single publishing flag and safe generation dry-run."""

from pathlib import Path

from content_generator.scheduler import daily

ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_forces_all_outbound_paths_off(monkeypatch):
    # run_now writes os.environ directly; register the keys with monkeypatch
    # so the dry-run flags do not leak into later tests.
    for key in ("DRY_RUN", "PUBLISHING_ENABLED", "NURTURE_ENABLED"):
        monkeypatch.setenv(key, "")
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


def test_daily_schedule_uses_one_opt_in_publishing_flag():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    retry = (ROOT / ".github" / "workflows" / "retry-unposted.yml").read_text(encoding="utf-8")
    recovery = (ROOT / ".github" / "workflows" / "publish-recovery.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Publishing is opt-in: only an explicit 'true' publishes.
    for text in (workflow, retry, recovery):
        assert "vars.PUBLISHING_ENABLED == 'true'" in text
        assert "vars.PUBLISHING_ENABLED != 'false'" not in text
        assert "vars.PUBLISHING_ENABLED || 'true'" not in text
    assert "Publishing is **opt-in**" in readme
    assert "PUBLISHING_ENABLED" in readme
    assert "reel_2" not in workflow
    scheduler = (ROOT / "content_generator" / "scheduler" / "daily.py").read_text(encoding="utf-8")
    assert '"reel_2": ReelSchema' not in scheduler
    assert "reel_2_day" not in scheduler


def test_unset_publishing_flag_holds_publishing(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("PUBLISHING_ENABLED", raising=False)
    assert daily._publishing_enabled() is False
    monkeypatch.setenv("PUBLISHING_ENABLED", "true")
    assert daily._publishing_enabled() is True
    monkeypatch.setenv("DRY_RUN", "1")
    assert daily._publishing_enabled() is False


def test_generate_dry_run_runs_pipeline_but_skips_publishing_and_commits():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "--dry-run" in workflow
    assert "DRY_RUN: ${{ github.event.inputs.dry_run }}" in workflow
    assert "github.event.inputs.dry_run != 'true'" in workflow

def test_nine_piece_dry_run_holds_story_when_visual_renderer_does_not_pass(monkeypatch, tmp_path):
    from content_generator.core import editorial_engine, publish_bar, product_truth, process_match
    from content_generator.creative import story_video, cinematic_frame, rendered_asset_qa, reel_video, visual_gate
    from content_generator.publisher import youtube
    from content_generator.publisher import story_copy, product_links, instagram
    from content_generator import rotation

    labels = {"instagram_post", "carousel", "growth_reel", "reel_1",
              "facebook_post", "threads_post", "linkedin_post", "yt_short"}
    monkeypatch.setattr(editorial_engine, "get_valid_assets", lambda content: labels)
    monkeypatch.setattr(publish_bar, "quality_block", lambda piece, label: "")
    monkeypatch.setattr(product_truth, "featured_product_name", lambda content: "purica")
    monkeypatch.setattr(product_truth, "piece_copy_text", lambda piece: "Smooth instant coffee")
    monkeypatch.setattr(product_truth, "asset_product_truth_findings", lambda piece, featured=None: [])
    monkeypatch.setattr(process_match, "process_match_findings", lambda text, featured=None: [])
    monkeypatch.setattr(story_video, "build_story_video", lambda **kwargs: None)
    monkeypatch.setattr(story_copy, "resolve_story_copy",
                        lambda content, day=0: {"headline": "Instant coffee in seconds",
                                                "sub": "Shop p3online.in/?utm_source=instagram&utm_medium=story&utm_campaign=pb"})
    monkeypatch.setattr(product_links, "story_link_line", lambda sub: sub)
    monkeypatch.setattr(rotation, "pick", lambda products, day: "purica")
    monkeypatch.setattr(cinematic_frame, "compose_cinematic_frame", lambda **kwargs: "story.jpg")
    monkeypatch.setattr(rendered_asset_qa, "audit_rendered_images", lambda paths: {"ok": True, "issues": []})
    monkeypatch.setattr(reel_video, "build_reel_video", lambda *a, **k: "reel.mp4")
    monkeypatch.setattr(youtube, "_find_video", lambda content: "short.mp4")
    monkeypatch.setattr(youtube, "_create_slideshow_short", lambda content, day: "short.mp4")
    monkeypatch.setattr(visual_gate, "recent_layouts", lambda: [])
    monkeypatch.setattr(visual_gate, "evaluate_video", lambda *a, **k: {"passed": True, "reasons": []})
    monkeypatch.setattr(instagram, "_static_story_visual_hold", lambda path: {"error": "visual_gate_hold"})
    monkeypatch.setattr(daily, "_remember_obstacle", lambda *a, **k: None)

    image_paths = []
    for name in ("ig.jpg", "carousel.jpg", "facebook.jpg"):
        path = tmp_path / name
        path.write_bytes(b"image")
        image_paths.append(str(path))
    piece = {"caption": "Smooth instant coffee", "hook": "Instant coffee in seconds"}
    content = {
        "day_number": 340,
        # Every piece is present; the gates (stubbed above) decide the result.
        "instagram_post": dict(piece), "stories": {"story_1": dict(piece)}, "carousel": dict(piece),
        "growth_reel": dict(piece), "reels": [dict(piece)], "facebook_post": dict(piece),
        "threads_post": dict(piece), "linkedin_post": dict(piece), "yt_short": dict(piece),
        "_creative_audit": {"image_assets": [
            {"platform": "instagram", "path": image_paths[0], "jar_verified": True},
            {"platform": "instagram_carousel", "path": image_paths[1], "jar_verified": True},
            {"platform": "facebook", "path": image_paths[2], "jar_verified": True},
        ]},
    }
    report = daily.dry_run_asset_report(content)
    assert report["passed"] == 8
    assert report["held"] == 1
    story = next(row for row in report["pieces"] if row["piece"] == "ig_story")
    assert story["status"] == "HOLD"
    assert "story_visual_gate_hold:visual_gate_hold" in story["reasons"]


def test_dry_run_youtube_short_below_8_is_held(monkeypatch, tmp_path):
    from content_generator.creative import visual_gate
    from content_generator.publisher import youtube
    from content_generator.creative import ken_burns

    monkeypatch.setattr(youtube, "_find_video", lambda content: "short.mp4")
    monkeypatch.setattr(visual_gate, "recent_layouts", lambda: [])
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: {"passed": False, "reasons": ["aesthetic_below_8.0:6.5"]})
    monkeypatch.setattr(ken_burns, "render_reel", lambda *a, **k: "fallback.mp4")
    monkeypatch.setattr(daily, "_remember_obstacle", lambda *a, **k: None)
    report = daily.dry_run_asset_report({"day_number": 1, "yt_short": {"caption": "Instant coffee"}})
    short = next(row for row in report["pieces"] if row["piece"] == "youtube_short")
    assert short["status"] == "HOLD"
    assert any(r.startswith("youtube_short_visual_gate:") for r in short["reasons"])
