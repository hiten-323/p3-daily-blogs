from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reel_uses_direct_upload_without_video_host():
    src = (ROOT / "content_generator/scheduler/slots.py").read_text()
    assert "_post_reel_direct_binary(video_path, caption)" in src
    assert "video_host" not in src
    assert "CLOUDINARY" not in src
    assert "post_reel_video" not in src


def test_story_video_uses_resumable_upload_in_source():
    src = (ROOT / "content_generator/publisher/instagram.py").read_text()
    assert "def _post_story_direct_binary" in src
    assert "_post_story_direct_binary(video_path)" in src
    assert "video_host" not in src
