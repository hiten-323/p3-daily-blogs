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

    for invalid_url in [
        "http://insecure.example/video.mp4",
        "https://localhost/video.mp4",
        "https://127.0.0.1/video.mp4",
        "https://10.0.0.1/video.mp4",
        "https://192.168.1.1/video.mp4",
        "https://172.16.0.1/video.mp4",
        "https://169.254.169.254/video.mp4",
        "https://[::1]/video.mp4",
        "https://internal-service/video.mp4",
        "https://backend.local/video.mp4",
        "https://backend.internal/video.mp4",
    ]:
        class BadResponse:
            status_code = 200

            def json(self):
                return {"secure_url": invalid_url}

        monkeypatch.setattr(requests, "post", lambda *a, **k: BadResponse())
        assert video_host.upload_video(str(video)) is None, f"Should have rejected {invalid_url}"

    class GoodResponse:
        status_code = 200

        def json(self):
            return {"secure_url": "https://res.cloudinary.com/cloud-name/video/upload/v1/sample.mp4"}

    monkeypatch.setattr(requests, "post", lambda *a, **k: GoodResponse())
    assert video_host.upload_video(str(video)) == "https://res.cloudinary.com/cloud-name/video/upload/v1/sample.mp4"




def test_invalid_cloudinary_image_api_key_is_redacted(monkeypatch, tmp_path, caplog):
    import logging
    import requests
    from content_generator.publisher import instagram

    image = tmp_path / "test.jpg"
    image.write_bytes(b"image fixture")
    monkeypatch.setenv(
        "CLOUDINARY_URL",
        "cloudinary://test-image-key:do-not-log-image-secret@cloud-name",
    )

    class Response:
        status_code = 401

        def json(self):
            return {"error": {"message": "Invalid api_key test-image-key"}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())
    with caplog.at_level(logging.WARNING):
        result = instagram._cloudinary_upload(str(image))

    assert result is None
    assert "HTTP 401" in caplog.text
    assert "test-image-key" not in caplog.text
    assert "do-not-log-image-secret" not in caplog.text
