"""The real-photo FFmpeg fallback is last and never bypasses the 8.0 gate."""

from content_generator.creative import ken_burns, reel_video, visual_gate


def test_local_ffmpeg_photo_fallback_is_held_below_8(monkeypatch, tmp_path):
    path = str(tmp_path / "reel.mp4")
    monkeypatch.setattr(ken_burns, "render_reel", lambda *a, **k: path)
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: {"passed": False, "reasons": ["aesthetic_below_8.0:6.5"]})
    monkeypatch.setattr("content_generator.scheduler.daily._remember_obstacle", lambda *a, **k: None)
    assert reel_video._photo_fallback({}, 340, "growth_reel", None, fast=True) is None


def test_local_ffmpeg_photo_fallback_returns_only_after_8_gate(monkeypatch, tmp_path):
    path = str(tmp_path / "reel.mp4")
    monkeypatch.setattr(ken_burns, "render_reel", lambda *a, **k: path)
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: {"passed": True, "reasons": []})
    assert reel_video._photo_fallback({}, 340, "reel_1", None, fast=False) == path


def test_fast_cut_uses_cinematic_provider_chain_before_local_ffmpeg(monkeypatch):
    monkeypatch.setenv("ENABLE_REEL_VIDEO", "true")
    monkeypatch.setattr("content_generator.creative.product_reel_templates.resolve_reusable_reel",
                        lambda reel: None)
    calls = []
    monkeypatch.setattr(reel_video, "_cinematic",
                        lambda *a, **k: calls.append("provider_chain") or None)
    monkeypatch.setattr(reel_video, "_photo_fallback",
                        lambda *a, **k: calls.append("local_ffmpeg") or "approved.mp4")
    result = reel_video.build_reel_video(
        {"growth_template_id": "fast_cut_curiosity", "product": "purica",
         "hook_text": "Watch what the spoon does next."},
        340, "growth_reel",
    )
    assert result == "approved.mp4"
    assert calls == ["provider_chain", "local_ffmpeg"]
