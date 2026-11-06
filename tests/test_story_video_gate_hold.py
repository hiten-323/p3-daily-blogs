"""A story the 8.0 gate rejects must not fall through to an ungated renderer."""
from __future__ import annotations


def _patch_common(monkeypatch):
    monkeypatch.setenv("ENABLE_STORY_VIDEO", "true")
    monkeypatch.setenv("CINEMATIC_VIDEO", "0")
    monkeypatch.setenv("PREMIUM_CARDS", "1")
    monkeypatch.setattr(
        "content_generator.creative.product_reel_templates.select_product_reel",
        lambda **kwargs: None,
    )
    calls = []

    def motion(**kwargs):
        calls.append("motion")
        return {"video": "/tmp/motion.mp4"}

    monkeypatch.setattr("content_generator.creative.story_motion.render_story_motion", motion)
    monkeypatch.setattr("content_generator.creative.visual_gate.recent_layouts", lambda: [])
    monkeypatch.setattr("content_generator.creative.visual_gate.remember_layout", lambda *a, **k: None)
    return calls


def test_a_rejected_premium_story_is_not_replaced(monkeypatch):
    calls = _patch_common(monkeypatch)

    def render(*args, **kwargs):
        calls.append("premium")
        return {"layout": kwargs.get("layout")}

    monkeypatch.setattr("content_generator.creative.premium_cards.render_story_video", render)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *a, **k: {"passed": False, "reasons": ["aesthetic_below_8.0:4.0"]},
    )
    monkeypatch.setattr("content_generator.creative.visual_gate.vision_outage", lambda: False)

    from content_generator.creative.story_video import build_story_video
    assert build_story_video(headline="Turn the jar around", day=1, product="bold") is None
    assert calls.count("premium") == 4
    assert "motion" not in calls


def test_a_vision_outage_holds_the_story(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(
        "content_generator.creative.premium_cards.render_story_video",
        lambda *a, **k: calls.append("premium") or {"layout": "hero"},
    )
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *a, **k: {"passed": False, "reasons": ["vision_unavailable"]},
    )
    monkeypatch.setattr("content_generator.creative.visual_gate.vision_outage", lambda: True)

    from content_generator.creative.story_video import build_story_video
    assert build_story_video(headline="Turn the jar around", day=2, product="bold") is None
    assert calls.count("premium") == 1
    assert "motion" not in calls


def test_a_passing_premium_story_is_returned(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(
        "content_generator.creative.premium_cards.render_story_video",
        lambda *a, **k: calls.append("premium") or {"layout": "hero"},
    )
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate_video",
        lambda *a, **k: {"passed": True, "reasons": []},
    )
    monkeypatch.setattr("content_generator.creative.visual_gate.vision_outage", lambda: False)

    from content_generator.creative.story_video import build_story_video
    path = build_story_video(headline="Turn the jar around", day=3, product="bold")
    assert path and path.endswith("_premium.mp4")
    assert calls.count("premium") == 1
    assert "motion" not in calls


def test_a_broken_premium_renderer_can_still_use_motion(monkeypatch):
    calls = _patch_common(monkeypatch)

    def render(*args, **kwargs):
        calls.append("premium")
        raise RuntimeError("renderer down")

    monkeypatch.setattr("content_generator.creative.premium_cards.render_story_video", render)

    from content_generator.creative.story_video import build_story_video
    assert build_story_video(headline="Turn the jar around", day=4, product="bold") == "/tmp/motion.mp4"
    assert "motion" in calls
