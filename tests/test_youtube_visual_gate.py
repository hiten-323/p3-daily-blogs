"""YouTube Shorts must pass the same 8.0 visual gate before upload."""

from content_generator.publisher import youtube
from content_generator.creative import visual_gate


def test_youtube_short_visual_gate_holds_below_8(monkeypatch):
    monkeypatch.setattr(visual_gate, "recent_layouts", lambda: [])
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: {"passed": False, "reasons": ["aesthetic_below_8.0:6.5"]})
    monkeypatch.setattr("content_generator.scheduler.daily._remember_obstacle", lambda *a, **k: None)
    assert youtube._visual_gate_video("short.mp4") is False


def test_youtube_short_visual_gate_accepts_8_plus(monkeypatch):
    monkeypatch.setattr(visual_gate, "recent_layouts", lambda: [])
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: {"passed": True, "reasons": []})
    assert youtube._visual_gate_video("short.mp4") is True


def test_youtube_short_visual_gate_fails_closed_on_provider_outage(monkeypatch):
    monkeypatch.setattr(visual_gate, "recent_layouts", lambda: [])
    monkeypatch.setattr(visual_gate, "evaluate_video",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("vision unavailable")))
    assert youtube._visual_gate_video("short.mp4") is False


def test_post_content_holds_upload_when_visual_gate_fails(monkeypatch):
    """Text checks run first, but a sub-8.0 Short still never reaches Google."""
    def boom(*_a, **_k):
        raise AssertionError("Google must not be called when the visual gate holds")

    monkeypatch.setattr(youtube, "is_configured", lambda: True)
    monkeypatch.setattr(youtube, "_find_video", lambda _content: "/tmp/short.mp4")
    monkeypatch.setattr(youtube, "_refresh_access_token", boom)
    monkeypatch.setattr(youtube, "_upload_video", boom)
    monkeypatch.setattr(youtube, "_visual_gate_video", lambda *a, **k: False)
    monkeypatch.setattr(
        "content_generator.publisher.dispatcher.editorial_disposition",
        lambda content, key: "approved",
    )
    monkeypatch.setattr("content_generator.core.publish_bar.quality_block", lambda *a, **k: None)
    monkeypatch.setattr("content_generator.core.product_truth.product_truth_findings", lambda *a, **k: [])
    monkeypatch.setattr("content_generator.publisher.prepublish_gate.authorize_publish",
                        lambda *a, **k: {"allowed": True, "reason": ""})
    res = youtube.post_content({"yt_short": {
        "title": "Read the label",
        "description": "Purica is freeze-dried instant coffee. Shop at p3online.in.",
        "hook": "Read the jar before you brew.",
        "script": "Purica is freeze-dried instant coffee.",
        "cta": "Shop at p3online.in",
    }}, day=1)
    assert res.get("success") is False
    assert res.get("error") == "visual_gate_hold_or_vision_unavailable"
