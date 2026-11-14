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
