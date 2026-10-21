"""Video and image hosting must not depend on Cloudinary or log upload bodies."""
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cloudinary_is_not_referenced_in_publish_code_or_workflows():
    roots = [ROOT / "content_generator", ROOT / ".github" / "workflows"]
    hits = []
    for base in roots:
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".py", ".yml", ".yaml", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if "cloudinary" in text:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []
    assert not (ROOT / "content_generator" / "publisher" / "video_host.py").exists()


def test_reel_resumable_failure_does_not_log_upload_body(monkeypatch, tmp_path, caplog):
    from content_generator.publisher import instagram, meta_graph

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "ig-1")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-token-do-not-log")
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key:do-not-log-this-secret@cloud")

    seen = {}

    def fake_graph(method, url, params=None, timeout=30):
        seen["params"] = dict(params or {})
        return {"id": "container-1", "uri": "https://rupload.facebook.com/ig-api-upload/container-1"}

    class Response:
        status_code = 401
        text = "rupload-session-secret-do-not-log"

        def json(self):
            return {"debug": "rupload-session-secret-do-not-log"}

    monkeypatch.setattr(meta_graph, "graph_request", fake_graph)
    monkeypatch.setattr("requests.post", lambda *a, **k: Response())

    with caplog.at_level(logging.DEBUG):
        result = instagram._post_reel_direct_binary(str(video), "caption")

    assert result["success"] is False
    assert result["error"] == "resumable_transfer_failed: 401"
    assert seen["params"]["media_type"] == "REELS"
    assert seen["params"]["upload_type"] == "resumable"
    assert "video_url" not in seen["params"]
    blob = caplog.text + str(result)
    assert "do-not-log-this-secret" not in blob
    assert "rupload-session-secret" not in blob
    assert "ig-token-do-not-log" not in caplog.text


def test_story_video_uses_resumable_upload(monkeypatch, tmp_path):
    from content_generator.publisher import instagram, meta_graph

    video = tmp_path / "story.mp4"
    video.write_bytes(b"story-bytes")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "ig-1")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-token")

    seen = {}

    def fake_graph(method, url, params=None, timeout=30):
        params = dict(params or {})
        seen.setdefault("calls", []).append(params)
        if params.get("media_type"):
            seen["params"] = params
        if str(url).endswith("/media_publish"):
            return {"id": "published-story"}
        return {"id": "container-story", "uri": "https://rupload.facebook.com/ig-api-upload/container-story"}

    class Response:
        status_code = 200
        text = "ok"

    monkeypatch.setattr(meta_graph, "graph_request", fake_graph)
    monkeypatch.setattr(meta_graph, "wait_for_container", lambda *a, **k: None)
    monkeypatch.setattr("requests.post", lambda *a, **k: Response())
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: type("R", (), {"json": lambda self: {"permalink": "https://www.instagram.com/stories/x/"}})(),
    )

    result = instagram._post_story_direct_binary(str(video))
    assert result["success"] is True
    assert result["media_id"] == "published-story"
    assert seen["params"]["media_type"] == "STORIES"
    assert seen["params"]["upload_type"] == "resumable"
    assert "video_url" not in seen["params"]


def test_prepared_story_falls_back_to_poster_when_resumable_fails(monkeypatch, tmp_path):
    from content_generator.publisher import instagram

    poster = tmp_path / "poster.jpg"
    video = tmp_path / "story.mp4"
    poster.write_bytes(b"img")
    video.write_bytes(b"vid")
    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_jar_provenance",
        lambda path: {"verified": True},
    )
    monkeypatch.setattr(
        instagram,
        "_post_story_direct_binary",
        lambda path: {"success": False, "media_id": "", "error": "resumable_transfer_failed: 400"},
    )
    seen = {}

    def local(path):
        seen["poster"] = path
        return {"success": True, "media_id": "poster-id"}

    monkeypatch.setattr(instagram, "post_local_story", local)
    result = instagram.post_prepared_story(str(poster), str(video))
    assert result["media_id"] == "poster-id"
    assert seen["poster"] == str(poster)


def test_image_host_ignores_cloudinary_env(monkeypatch, tmp_path):
    from content_generator.publisher import instagram

    image = tmp_path / "frame.jpg"
    image.write_bytes(b"jpeg-bytes")
    monkeypatch.setenv("IMGBB_API_KEY", "imgbb-key")
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key:secret@cloud")
    calls = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": {"url": "https://i.ibb.co/abc/photo.jpg"}}

    def post(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr("requests.post", post)
    url = instagram._upload_to_public_url(str(image))
    assert url == "https://i.ibb.co/abc/photo.jpg"
    assert calls == ["https://api.imgbb.com/1/upload"]
    assert not hasattr(instagram, "_cloudinary_upload")
