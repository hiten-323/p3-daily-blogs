"""Lifestyle plates rotate, and a flat backdrop cannot publish."""
from __future__ import annotations

import json

from PIL import Image, ImageDraw

from content_generator.creative.jar_frame import audit_product_image, compose_conversion_frame
from content_generator.creative.lifestyle_scene import floor_disc_delta, scene_for_day


def test_scenes_rotate_by_day():
    assert scene_for_day(285)["id"] == "cafe_table"
    assert scene_for_day(286)["id"] == "work_desk"
    assert scene_for_day(285)["id"] != scene_for_day(286)["id"]


def test_conversion_frame_uses_a_lifestyle_plate(tmp_path, monkeypatch):
    import content_generator.creative.jar_frame as jar_frame
    monkeypatch.setattr(jar_frame, "_OUT_DIR", str(tmp_path))
    path = compose_conversion_frame(
        headline="CAFE STRENGTH AT HOME",
        product="Bold",
        day=285,
        width=1080,
        height=1350,
        label="life",
        format_name="feed",
        on_date="2026-10-13",
        out_dir=str(tmp_path),
    )
    assert path
    result = audit_product_image(path)
    assert result["ok"], result
    geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
    assert geometry["scene_id"] == "cafe_table"
    assert geometry["contact_shadow"] is True
    assert geometry["scale"] <= 1.0
    assert "bold_50g_front" in geometry["source_asset"]


def test_balcony_sunrise_still_has_counter_texture(tmp_path, monkeypatch):
    import content_generator.creative.jar_frame as jar_frame
    monkeypatch.setattr(jar_frame, "_OUT_DIR", str(tmp_path))
    path = compose_conversion_frame(
        headline="SUNRISE THEN COFFEE",
        product="Bold",
        day=287,
        width=1080,
        height=1350,
        label="balcony",
        format_name="feed",
        on_date="2026-10-13",
        out_dir=str(tmp_path),
    )
    assert path
    result = audit_product_image(path)
    assert result["ok"], result
    geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
    assert geometry["scene_id"] == "balcony_sunrise"
    assert geometry["scale"] <= 1.0


def test_story_has_no_floor_ellipse(tmp_path, monkeypatch):
    import content_generator.creative.jar_frame as jar_frame
    monkeypatch.setattr(jar_frame, "_OUT_DIR", str(tmp_path))
    path = compose_conversion_frame(
        headline="TURN THE JAR AROUND",
        product="Bold",
        day=285,
        width=1080,
        height=1920,
        label="story",
        format_name="story",
        on_date="2026-10-13",
        out_dir=str(tmp_path),
    )
    assert path
    result = audit_product_image(path)
    assert result["ok"], result
    geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
    assert floor_disc_delta(Image.open(path), geometry["jar_bbox"]) <= 18


def test_a_light_ellipse_under_the_jar_fails(tmp_path):
    path = tmp_path / "ellipse.png"
    image = Image.new("RGB", (900, 1200), (48, 36, 28))
    draw = ImageDraw.Draw(image)
    draw.rectangle((280, 360, 620, 860), fill=(210, 200, 186))
    draw.ellipse((180, 860, 720, 940), fill=(226, 222, 214))
    image.save(path)
    with open(str(path) + ".jar.json", "w", encoding="utf-8") as handle:
        json.dump({
            "jar_required": True,
            "jar_bbox": [280, 360, 620, 860],
            "text_boxes": [],
            "safe_zone": [40, 40, 860, 1160],
            "scale": 1.0,
            "lifestyle_required": True,
            "contact_shadow": True,
            "scene_id": "cafe_table",
        }, handle)
    result = audit_product_image(str(path))
    assert not result["ok"]
    assert any("floor_disc" in issue for issue in result["issues"])


def test_flat_backdrop_fails_realism(tmp_path):
    path = tmp_path / "flat.png"
    image = Image.new("RGB", (900, 1200), (24, 16, 12))
    ImageDraw.Draw(image).rectangle((80, 180, 820, 1000), fill=(230, 220, 200))
    image.save(path)
    with open(str(path) + ".jar.json", "w", encoding="utf-8") as handle:
        json.dump({
            "jar_required": True,
            "jar_bbox": [80, 180, 820, 1000],
            "text_boxes": [],
            "safe_zone": [40, 40, 860, 1160],
            "scale": 1.0,
            "lifestyle_required": True,
            "contact_shadow": True,
            "scene_id": "cafe_table",
        }, handle)
    result = audit_product_image(str(path))
    assert not result["ok"]
    assert any("flat_background" in issue for issue in result["issues"])
