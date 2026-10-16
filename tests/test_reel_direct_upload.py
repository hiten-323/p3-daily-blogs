from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reel_uses_direct_upload_without_video_host():
    src = (ROOT / "content_generator/scheduler/slots.py").read_text()
    assert "_post_reel_direct_binary(video_path, caption)" in src


def test_cloudinary_url_pasted_with_prefix(monkeypatch):
    from content_generator.publisher import video_host
    monkeypatch.setenv("CLOUDINARY_URL", ' CLOUDINARY_URL="cloudinary://k:s@demo"\n')
    assert video_host._creds() == ("k", "s", "demo")
