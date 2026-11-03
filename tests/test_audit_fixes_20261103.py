"""Regression tests for the 3 Nov 2026 audit fixes."""
import ast
import pathlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_generator_has_no_reel_2_archetype_reference():
    """reel_2 is retired; generate_daily_content must not touch its archetype (NameError)."""
    src = (ROOT / "content_generator/pipeline/generator.py").read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert "arch_2" not in names


def test_facebook_video_shop_link_carries_utm_campaign(tmp_path):
    from content_generator.publisher import facebook as fb
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 16)
    resp = mock.Mock()
    resp.json.return_value = {"id": "123"}
    with mock.patch("requests.post", return_value=resp) as post:
        out = fb._post_video_to_page("page", "tok", "Hook line", str(video), title="t")
    assert out["success"]
    desc = post.call_args.kwargs["data"]["description"]
    assert "utm_source=facebook" in desc and "utm_campaign=" in desc
    low = desc.lower()
    for banned in ("single-origin", "single origin", "100%", "pure instant coffee", "sludge"):
        assert banned not in low


def test_story_frame_exposure_qa_is_wired():
    src = (ROOT / "content_generator/scheduler/daily.py").read_text(encoding="utf-8")
    assert "audit_rendered_images([story_frame])" in src
    assert "exposure_boost=True" in src
