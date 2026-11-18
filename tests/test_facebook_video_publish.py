"""Test native Facebook video publishing and slot mirroring."""
import os
import pytest
from unittest.mock import patch, MagicMock

from content_generator.publisher import facebook as fb


def test_post_video_to_page_formats_and_calls_videos_endpoint(tmp_path):
    video_file = tmp_path / "test_growth_reel.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 100)

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "fb_vid_12345"}
        mock_post.return_value = mock_resp

        res = fb._post_video_to_page(
            page_id="122169412904655685",
            token="test_token",
            message="Why 90% of filter coffee isn't pure.",
            video_path=str(video_file),
            title="Pure Coffee Test",
        )

        assert res["success"] is True
        assert res["post_id"] == "fb_vid_12345"
        assert "122169412904655685/videos/fb_vid_12345" in res["url"]

        call_args = mock_post.call_args
        assert call_args[0][0].endswith("/122169412904655685/videos")
        assert "👉 Follow @purepantryprovisions" in call_args[1]["data"]["description"]
        assert "https://p3online.in" in call_args[1]["data"]["description"]


def test_post_content_routes_video_path_to_video_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "122169412904655685")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "test_page_token")

    video_file = tmp_path / "test_growth_reel.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 100)

    content = {
        "day_number": 306,
        "facebook_post": {"hook": "Hook", "body": "Body", "community_question": "Q?", "cta": "CTA"},
    }

    with patch.object(fb, "resolve_page_access_token", return_value="test_page_token"), \
         patch("content_generator.core.publish_bar.quality_block", return_value=""), \
         patch("content_generator.core.product_truth.product_truth_findings", return_value=[]), \
         patch.object(fb, "_post_video_to_page", return_value={"success": True, "post_id": "v123", "url": "http://fb/v123", "error": None}) as mock_vid:

        res = fb.post_content(
            content=content,
            day=306,
            message_override="Fresh roast reel caption #PurityBeans",
            mirror_piece={"hook": "Fresh roast", "video_path": str(video_file), "editorial_score": {"overall": 8.5}},
            mirror_label="growth_reel",
            video_path=str(video_file),
        )

        assert res["success"] is True
        assert res["post_id"] == "v123"
        mock_vid.assert_called_once()
