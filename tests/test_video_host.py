"""Cloudinary video-host failure handling must fail closed and redact secrets."""
import logging

from content_generator.publisher import video_host


def test_video_host_rejects_incomplete_cloudinary_credentials(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://:secret@cloud-name")
    assert video_host._creds() is None
    assert video_host.is_configured() is False


def test_invalid_cloudinary_api_key_fails_closed_without_logging_response_body(
    monkeypatch, tmp_path, caplog
):
    import requests

    video = tmp_path / "test.mp4"
    video.write_bytes(b"video fixture")
    monkeypatch.setenv(
        "CLOUDINARY_URL",
        "cloudinary://test-api-key:do-not-log-this-secret@cloud-name",
    )

    class Response:
        status_code = 401

        def json(self):
            return {"error": {"message": "Invalid api_key test-api-key"}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())
    with caplog.at_level(logging.WARNING):
        result = video_host.upload_video(str(video))

    assert result is None
    assert "HTTP 401" in caplog.text
    assert "test-api-key" not in caplog.text
    assert "do-not-log-this-secret" not in caplog.text


def test_video_host_only_returns_public_https_url(monkeypatch, tmp_path):
    import requests

    video = tmp_path / "test.mp4"
    video.write_bytes(b"video fixture")
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://test-key:test-secret@cloud-name")

    class Response:
        status_code = 200

        def json(self):
            return {"secure_url": "http://insecure.example/video.mp4"}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())
    assert video_host.upload_video(str(video)) is None
