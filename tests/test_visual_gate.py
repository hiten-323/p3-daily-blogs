"""Visual QA is mandatory for every scene and format, then fail-closed."""
from __future__ import annotations

import json

from PIL import Image, ImageDraw

from content_generator.creative.jar_frame import audit_product_image, compose_conversion_frame
from content_generator.creative.lifestyle_scene import SCENES
from content_generator.creative.visual_gate import (
    FORMATS,
    enforce_visual_gate,
    render_passing_frame,
)

# 284 % 4 == 0, so each scene is one day apart.
_SCENE_DAY = {scene["id"]: 284 + index for index, scene in enumerate(SCENES)}


def test_every_scene_and_format_passes_visual_qa(tmp_path):
    for scene in SCENES:
        day = _SCENE_DAY[scene["id"]]
        for name, (width, height) in FORMATS.items():
            path = compose_conversion_frame(
                product="Bold",
                day=day,
                width=width,
                height=height,
                label=f"{scene['id']}_{name}",
                format_name=name if name != "yt" else "feed",
                on_date="2026-10-13",
                out_dir=str(tmp_path),
            )
            assert path, (scene["id"], name)
            result = audit_product_image(path)
            assert result["ok"], (scene["id"], name, result)
            geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
            assert geometry["mask_ok"] is True
            assert "purepantryprovisions" in geometry["on_image"]["cta"].lower()
            assert geometry["scene_id"] == scene["id"]


def _geometry_frame(tmp_path, on_image, **extra):
    path = tmp_path / "frame.png"
    image = Image.new("RGB", (1080, 1350), (40, 30, 22))
    ImageDraw.Draw(image).rectangle((80, 200, 1000, 1100), fill=(120, 90, 60))
    image.save(path)
    payload = {
        "jar_required": True,
        "jar_bbox": [360, 500, 700, 1000],
        "text_boxes": [],
        "safe_zone": [40, 40, 1040, 1280],
        "scale": 1.0,
        "lifestyle_required": True,
        "contact_shadow": True,
        "scene_id": "kitchen_morning",
        "mask_ok": True,
        "mask_issues": [],
        "product": "bold",
        "on_image": on_image,
    }
    payload.update(extra)
    with open(str(path) + ".jar.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return str(path)


def test_wrong_handle_fails(tmp_path):
    path = _geometry_frame(tmp_path, {
        "hook": "Turn the jar around",
        "benefit": "100% Robusta. Zero chicory.",
        "offer": "50g Rs 239",
        "cta": "Follow @puritybeans",
    })
    result = audit_product_image(path)
    assert not result["ok"]
    assert any("wrong_handle" in issue for issue in result["issues"])


def test_unverified_stat_hook_fails(tmp_path):
    path = _geometry_frame(tmp_path, {
        "hook": "Most people waste Rs 200 every week",
        "benefit": "100% Robusta.",
        "offer": "50g Rs 239",
        "cta": "Follow @purepantryprovisions",
    })
    result = audit_product_image(path)
    assert not result["ok"]
    assert any("unverified_stat_hook" in issue for issue in result["issues"])


def test_mask_integrity_failure_is_closed(tmp_path):
    path = _geometry_frame(tmp_path, {
        "hook": "Turn the jar around",
        "benefit": "100% Robusta. Zero chicory.",
        "offer": "",
        "cta": "Follow @purepantryprovisions",
    }, mask_ok=False, mask_issues=["jagged_edge"])
    result = audit_product_image(path)
    assert not result["ok"]
    assert any("mask_integrity" in issue for issue in result["issues"])
    assert any("jagged_edge" in issue for issue in result["issues"])


def test_failing_frame_retries_then_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_MAX_REGEN", "2")
    calls = []

    def fake_render(content, day, surface, attempt, label, out_dir):
        path = str(tmp_path / f"try{attempt}.jpg")
        Image.new("RGB", (32, 32), (4, 4, 4)).save(path)
        calls.append(attempt)
        return path

    monkeypatch.setattr("content_generator.creative.visual_gate._render_frame", fake_render)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate._audit",
        lambda path: {"ok": False, "issues": ["prop_overlap"]},
    )
    result = render_passing_frame(
        {"featured_product": "Bold"}, 285, "feed", label="feed", out_dir=str(tmp_path),
    )
    assert result["decision"] == "BLOCKED"
    assert calls == [0, 1, 2]
    assert not (tmp_path / "try2.jpg").exists()
    assert (tmp_path / "_blocked" / "try2.jpg").exists()


def test_next_placement_can_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_MAX_REGEN", "2")

    def fake_render(content, day, surface, attempt, label, out_dir):
        path = str(tmp_path / f"try{attempt}.jpg")
        Image.new("RGB", (32, 32), (4, 4, 4)).save(path)
        return path

    monkeypatch.setattr("content_generator.creative.visual_gate._render_frame", fake_render)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate._audit",
        lambda path: {"ok": path.endswith("try1.jpg"), "issues": [] if path.endswith("try1.jpg") else ["prop_overlap"]},
    )
    result = render_passing_frame({"featured_product": "Bold"}, 285, "story", label="story", out_dir=str(tmp_path))
    assert result["decision"] == "PASS"
    assert result["attempts"] == 2
    assert result["path"].endswith("try1.jpg")


def test_blocked_platform_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_MAX_REGEN", "0")
    frame = tmp_path / "facebook_post_day285_2026-10-13.jpg"
    Image.new("RGB", (32, 32), (4, 4, 4)).save(frame)

    def fake_render(content, day, surface, attempt, label, out_dir):
        path = str(tmp_path / f"{surface['id']}.jpg")
        Image.new("RGB", (32, 32), (4, 4, 4)).save(path)
        return path

    monkeypatch.setattr("content_generator.creative.visual_gate._render_frame", fake_render)
    monkeypatch.setattr(
        "content_generator.creative.visual_gate._audit",
        lambda path: {"ok": False, "issues": ["prop_overlap"]},
    )
    summary = enforce_visual_gate(
        {"featured_product": "Bold", "carousel": {}},
        {"facebook_post": str(frame)},
        285,
    )
    facebook = next(row for row in summary["surfaces"] if row["id"] == "facebook")
    assert facebook["decision"] == "BLOCKED"
    assert "facebook" in summary["blocked_platforms"]
    assert not frame.exists()
