"""A static Instagram Story must clear the same 8.0 visual gate as the video.

The 2026-10-27 retry-unposted run held every motion render, then published
the cinematic still. That still only passed broken-render QA.
"""
import json

from content_generator.creative.visual_gate import AESTHETIC_PASS


def _frame(tmp_path, name="story_day299.jpg"):
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xd9")
    return str(path)


def _drive(monkeypatch, tmp_path, *, video=None, verdict=None, poster=None):
    from content_generator.publisher import instagram

    frame = _frame(tmp_path)
    uploads = []
    gated = []
    posts = []

    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    monkeypatch.setattr(
        "content_generator.creative.cinematic_frame.compose_cinematic_frame",
        lambda **kwargs: frame,
    )
    monkeypatch.setattr(
        "content_generator.creative.rendered_asset_qa.audit_rendered_images",
        lambda paths: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        "content_generator.creative.story_video.build_story_video",
        lambda **kwargs: video,
    )

    def evaluate(meta, recent_layouts=(), vision=None):
        gated.append(dict(meta))
        return dict(verdict or {"passed": False, "reasons": ["aesthetic_below_8.0:4.0"]})

    monkeypatch.setattr("content_generator.creative.visual_gate.evaluate", evaluate)
    monkeypatch.setattr("content_generator.creative.visual_gate.recent_layouts", lambda: [])

    def upload(path):
        uploads.append(path)
        return "https://i.ibb.co/story.jpg"

    monkeypatch.setattr(instagram, "_upload_to_public_url", upload)

    def graph(method, url, params=None, timeout=30):
        payload = dict(params or {})
        posts.append(payload)
        if str(url).endswith("/media_publish"):
            return {"id": "published-story"}
        return {"id": "container-story"}

    monkeypatch.setattr("content_generator.publisher.meta_graph.graph_request", graph)
    monkeypatch.setattr("content_generator.publisher.meta_graph.wait_for_container", lambda *a, **k: None)
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: type("R", (), {"json": lambda self: {"permalink": "https://instagram.com/stories/x/"}})(),
    )
    if video and poster:
        open(poster, "wb").write(b"\xff\xd8\xff\xd9")
    return instagram, frame, uploads, gated, posts


def test_bar_stays_at_8():
    assert AESTHETIC_PASS == 8.0


def test_held_video_and_failing_static_story_is_not_posted(monkeypatch, tmp_path):
    lessons = tmp_path / "lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(lessons))
    instagram, frame, uploads, gated, posts = _drive(
        monkeypatch, tmp_path,
        video=None,
        verdict={"passed": False, "reasons": ["aesthetic_below_8.0:4.0"]},
    )
    from content_generator.publisher import publishing_ledger as ledger

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    content = {"date": "2026-10-27", "generation_id": "run-40455948697", "day_number": 299}
    result = instagram.post_story(content, day=299)

    assert result["success"] is False
    assert result.get("held") is True
    assert result.get("attempted") is False
    assert result["error"].startswith("prepublish_gate:visual_gate:")
    assert "aesthetic_below_8.0:4.0" in result["error"]
    assert uploads == []
    assert posts == []
    assert gated and gated[0]["path"] == frame

    ticket = ledger.begin_attempt(content, "instagram_story", "morning", 299)
    record = ledger.finish_attempt(ticket, result)
    assert record["status"] == "FAILED"
    assert record["error"].startswith("prepublish_gate:visual_gate:")
    assert record.get("remote_id") in ("", None)
    assert record.get("published") is not True

    stored = json.loads(lessons.read_text(encoding="utf-8"))
    row = stored["lessons"][-1]
    assert row["platform"] == "instagram_story"
    assert row["label"] == "stories"
    assert row["gate"] == "aesthetic"
    assert "aesthetic_below_8.0:4.0" in row["reason"]


def test_static_story_posts_when_visual_gate_passes(monkeypatch, tmp_path):
    instagram, frame, uploads, gated, posts = _drive(
        monkeypatch, tmp_path,
        video=None,
        verdict={"passed": True, "reasons": [], "vision": {"score": 8.4}},
    )
    result = instagram.post_story({"date": "2026-10-27", "day_number": 299}, day=299)

    assert result["success"] is True
    assert result.get("format") == "image"
    assert result.get("media_id") == "published-story"
    assert uploads == [frame]
    assert gated and gated[0]["path"] == frame
    assert any(p.get("media_type") == "STORIES" and p.get("image_url") for p in posts)


def test_poster_fallback_is_held_when_visual_gate_fails(monkeypatch, tmp_path):
    from content_generator.publisher import instagram

    video = str(tmp_path / "story_video.mp4")
    poster = str(tmp_path / "story_video_poster.jpg")
    open(video, "wb").write(b"videobytes")
    instagram_mod, _frame, uploads, gated, posts = _drive(
        monkeypatch, tmp_path,
        video=video,
        poster=poster,
        verdict={"passed": False, "reasons": ["aesthetic_below_8.0:5.0"]},
    )
    monkeypatch.setattr(
        instagram_mod,
        "_post_story_direct_binary",
        lambda path: {"success": False, "media_id": "", "error": "resumable_transfer_failed: 400"},
    )
    result = instagram.post_story({"date": "2026-10-27", "day_number": 299}, day=299)

    assert result["success"] is False
    assert result.get("held") is True
    assert "aesthetic_below_8.0:5.0" in result["error"]
    assert uploads == []
    assert posts == []
    assert gated[-1]["path"] == poster


def test_poster_fallback_posts_when_visual_gate_passes(monkeypatch, tmp_path):
    from content_generator.publisher import instagram

    video = str(tmp_path / "story_video.mp4")
    poster = str(tmp_path / "story_video_poster.jpg")
    open(video, "wb").write(b"videobytes")
    instagram_mod, _frame, uploads, gated, posts = _drive(
        monkeypatch, tmp_path,
        video=video,
        poster=poster,
        verdict={"passed": True, "reasons": [], "vision": {"score": 8.6}},
    )
    monkeypatch.setattr(
        instagram_mod,
        "_post_story_direct_binary",
        lambda path: {"success": False, "media_id": "", "error": "resumable_transfer_failed: 400"},
    )
    result = instagram.post_story({"date": "2026-10-27", "day_number": 299}, day=299)

    assert result["success"] is True
    assert result.get("format") == "image"
    assert uploads == [poster]
    assert gated[-1]["path"] == poster
    assert any(p.get("media_type") == "STORIES" and p.get("image_url") for p in posts)


def test_local_story_image_is_held_unless_visual_gate_passes(monkeypatch, tmp_path):
    """Prepared-story poster fallback publishes through post_local_story."""
    from content_generator.publisher import instagram

    image = _frame(tmp_path, "poster.jpg")
    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_jar_provenance",
        lambda path: {"verified": True},
    )
    uploads = []
    monkeypatch.setattr(instagram, "_upload_to_public_url", lambda path: uploads.append(path) or "https://i.ibb.co/p.jpg")
    monkeypatch.setattr("content_generator.creative.visual_gate.recent_layouts", lambda: [])
    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate",
        lambda meta, recent_layouts=(), vision=None: {"passed": False, "reasons": ["aesthetic_below_8.0:4.0"]},
    )
    held = instagram.post_local_story(image)
    assert held["success"] is False
    assert held.get("held") is True
    assert "aesthetic_below_8.0:4.0" in held["error"]
    assert uploads == []

    monkeypatch.setattr(
        "content_generator.creative.visual_gate.evaluate",
        lambda meta, recent_layouts=(), vision=None: {"passed": True, "reasons": [], "vision": {"score": 8.2}},
    )
    monkeypatch.setattr("content_generator.publisher.meta_graph.graph_request", lambda *a, **k: {"id": "local-story"})
    monkeypatch.setattr("content_generator.publisher.meta_graph.wait_for_container", lambda *a, **k: None)
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: type("R", (), {"json": lambda self: {"permalink": "https://instagram.com/stories/local/"}})(),
    )
    posted = instagram.post_local_story(image)
    assert posted["success"] is True
    assert posted.get("media_id") == "local-story"
    assert uploads == [image]
