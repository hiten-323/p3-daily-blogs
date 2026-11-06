"""A story the 8.0 visual gate rejected must not fall through to an ungated video.

2026-11-01 removed the hold after premium re-renders failed, so build_story_video
continued into motion and Ken Burns. Those paths never call visual_gate, and
post_story publishes whatever MP4 comes back.
"""
from datetime import date


def _patch_common(monkeypatch, tmp_path):
    from content_generator.creative import story_video, visual_gate

    visual_gate._OUTAGE["n"] = 0

    monkeypatch.setenv("CINEMATIC_VIDEO", "0")
    monkeypatch.setenv("PREMIUM_CARDS", "1")
    monkeypatch.setenv("ENABLE_STORY_VIDEO", "true")
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "content_generator.creative.product_reel_templates.select_product_reel",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("content_generator.creative.visual_gate.recent_layouts", lambda: [])
    monkeypatch.setattr("content_generator.creative.visual_gate.remember_layout", lambda *a, **k: None)
    calls = {"premium": 0, "motion": 0, "ken": 0}

    def render_story(*args, **kwargs):
        calls["premium"] += 1
        return {"layout": "hero_center"}

    def motion(*args, **kwargs):
        calls["motion"] += 1
        path = tmp_path / "ungated.mp4"
        path.write_bytes(b"ungated")
        return {"video": str(path)}

    def ken(*args, **kwargs):
        calls["ken"] += 1
        return str(tmp_path / "ken.mp4")

    monkeypatch.setattr("content_generator.creative.premium_cards.render_story_video", render_story)
    monkeypatch.setattr("content_generator.creative.story_motion.render_story_motion", motion)
    monkeypatch.setattr(story_video, "_ken_burns", ken)
    return story_video, calls


def test_rejected_story_does_not_fall_through_to_ungated_video(monkeypatch, tmp_path):
    story_video, calls = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr("content_generator.creative.visual_gate.vision_outage", lambda: False)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *args, **kwargs: {"passed": False, "reasons": ["aesthetic_below_8.0:4.0"]},
    )

    result = story_video.build_story_video(
        image_path=str(tmp_path / "still.jpg"),
        headline="READ THE LABEL",
        sub="Check the jar.",
        day=299,
        label="story_video",
        on_date=date(2026, 10, 27),
    )

    assert result is None
    assert calls["premium"] == 4
    assert calls["motion"] == 0
    assert calls["ken"] == 0


def test_vision_outage_holds_the_story(monkeypatch, tmp_path):
    story_video, calls = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr("content_generator.creative.visual_gate.vision_outage", lambda: True)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *args, **kwargs: {"passed": False, "reasons": ["vision_score_unavailable"]},
    )

    result = story_video.build_story_video(
        headline="READ THE LABEL",
        day=299,
        on_date=date(2026, 10, 27),
    )

    assert result is None
    assert calls["premium"] == 1
    assert calls["motion"] == 0
    assert calls["ken"] == 0


def test_premium_story_that_passes_the_gate_is_returned(monkeypatch, tmp_path):
    story_video, calls = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *args, **kwargs: {"passed": True, "reasons": []},
    )

    result = story_video.build_story_video(
        headline="READ THE LABEL",
        day=299,
        label="story_video",
        on_date=date(2026, 10, 27),
    )

    assert result.endswith("_premium.mp4")
    assert calls["premium"] == 1
    assert calls["motion"] == 0
    assert calls["ken"] == 0
