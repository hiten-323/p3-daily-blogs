"""Lifestyle plates rotate, and a flat backdrop cannot publish."""
from __future__ import annotations

import json

from PIL import Image, ImageDraw

from content_generator.creative.jar_frame import audit_product_image, compose_conversion_frame
from content_generator.creative.lifestyle_scene import (
    floor_disc_delta,
    frame_props,
    props_overlap,
    scene_by_id,
    scene_for_day,
)
from content_generator.creative.scene_natural import grade_to_scene, naturalism_issues


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


def test_a_hard_shadow_strip_fails():
    image = Image.new("RGB", (800, 1100), (150, 118, 96))
    draw = ImageDraw.Draw(image)
    draw.rectangle((220, 280, 560, 820), fill=(130, 80, 160))
    draw.rectangle((160, 822, 640, 868), fill=(48, 36, 28))
    from content_generator.creative.lifestyle_scene import realism_issues
    issues = realism_issues(image, (220, 280, 560, 820), "cafe_table")
    assert "shadow_hard_edge" in issues


def test_a_feathered_ellipse_is_not_a_hard_edge():
    from content_generator.creative.scene_natural import paint_contact_shadow, shadow_hard_edge
    plate = Image.new("RGB", (800, 1100), (150, 118, 96))
    painted = paint_contact_shadow(plate, 400, 820, 260, "left")
    assert shadow_hard_edge(painted, (220, 280, 560, 820)) is False


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


def test_jar_sits_beside_scene_props(tmp_path, monkeypatch):
    import content_generator.creative.jar_frame as jar_frame
    monkeypatch.setattr(jar_frame, "_OUT_DIR", str(tmp_path))
    cases = (
        (285, 1080, 1920, "story"),
        (286, 1080, 1920, "story"),
        (287, 1080, 1920, "story"),
        (284, 1080, 1350, "feed"),
    )
    for day, width, height, fmt in cases:
        path = compose_conversion_frame(
            product="Bold",
            day=day,
            width=width,
            height=height,
            label=f"prop_{day}_{fmt}",
            format_name=fmt,
            on_date="2026-10-13",
            out_dir=str(tmp_path),
        )
        assert path
        result = audit_product_image(path)
        assert result["ok"], result
        geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
        props = frame_props(scene_by_id(geometry["scene_id"]), width, height)
        assert props_overlap(geometry["jar_bbox"], props) == []


def test_a_jar_covering_the_cup_fails(tmp_path):
    scene = scene_by_id("cafe_table")
    props = frame_props(scene, 1080, 1920)
    cup = props[0]["box"]
    path = tmp_path / "cover.png"
    image = Image.new("RGB", (1080, 1920), (36, 28, 22))
    ImageDraw.Draw(image).rectangle((80, 400, 1000, 1500), fill=(90, 70, 52))
    image.save(path)
    with open(str(path) + ".jar.json", "w", encoding="utf-8") as handle:
        json.dump({
            "jar_required": True,
            "jar_bbox": list(cup),
            "text_boxes": [],
            "safe_zone": [40, 40, 1040, 1880],
            "scale": 1.0,
            "lifestyle_required": True,
            "contact_shadow": True,
            "scene_id": "cafe_table",
        }, handle)
    result = audit_product_image(str(path))
    assert not result["ok"]
    assert any("prop_overlap" in issue for issue in result["issues"])


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


def _hue(rgb) -> float | None:
    red, green, blue = [float(v) for v in rgb]
    high, low = max(red, green, blue), min(red, green, blue)
    span = high - low
    if span < 8:
        return None
    if high == red:
        sector = ((green - blue) / span) % 6
    elif high == green:
        sector = (blue - red) / span + 2
    else:
        sector = (red - green) / span + 4
    return sector * 60


def test_jar_shorter_than_the_cup_fails():
    scene = scene_by_id("cafe_table")
    width, height = 1080, 1080
    cup = frame_props(scene, width, height)[0]["box"]
    cup_h = cup[3] - cup[1]
    jar_h = min(int(height * 0.33), cup_h - 8)
    image = Image.new("RGB", (width, height), (96, 74, 54))
    top = int(height * 0.40)
    issues = naturalism_issues(image, (220, top, 480, top + jar_h), scene)
    assert jar_h < cup_h
    assert "smaller_than_prop" in issues


def test_tiny_jar_is_not_the_hero():
    image = Image.new("RGB", (1080, 1920), (96, 74, 54))
    issues = naturalism_issues(image, (240, 900, 480, 1284), scene_by_id("kitchen_morning"))
    assert "jar_not_hero" in issues


def test_flat_label_fails_sharpness():
    image = Image.new("RGB", (1080, 1920), (96, 74, 54))
    issues = naturalism_issues(image, (240, 620, 720, 1426), scene_by_id("kitchen_morning"))
    assert "label_soft" in issues


def test_jar_against_the_frame_edge_fails():
    image = Image.new("RGB", (1080, 1920), (90, 70, 55))
    ImageDraw.Draw(image).rectangle((20, 980, 250, 1360), fill=(170, 140, 180))
    issues = naturalism_issues(image, (20, 980, 250, 1360), scene_by_id("cafe_table"))
    assert "jar_at_frame_edge" in issues


def test_a_faded_side_fails_the_label_check():
    from content_generator.creative.label_color import label_color_issues
    reference = Image.new("RGB", (160, 120), (168, 48, 196))
    rendered = reference.copy()
    ImageDraw.Draw(rendered).rectangle((0, 0, 80, 120), fill=(110, 90, 130))
    issues = label_color_issues(rendered, reference)
    assert "label_uneven" in issues or "label_color_drift" in issues


def test_grade_is_uniform_and_keeps_chroma():
    jar = Image.new("RGBA", (180, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(jar)
    draw.rectangle((10, 8, 170, 292), fill=(168, 48, 196, 255))
    plate = Image.new("RGB", (800, 1200), (110, 78, 52))
    graded = grade_to_scene(jar, plate, (260, 700, 480, 1080), "left")
    left = graded.getpixel((40, 150))[:3]
    right = graded.getpixel((140, 150))[:3]
    assert left == right
    before = max(168, 48, 196) - min(168, 48, 196)
    after = max(left) - min(left)
    assert after >= before * 0.90


def test_grade_does_not_rotate_label_hue():
    jar = Image.new("RGBA", (180, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(jar)
    draw.rectangle((10, 8, 170, 48), fill=(168, 168, 172, 255))
    draw.rectangle((16, 90, 164, 250), fill=(168, 48, 196, 255))
    plate = Image.new("RGB", (800, 1200), (110, 78, 52))
    graded = grade_to_scene(jar, plate, (260, 700, 480, 1080), "left")
    before = jar.crop((16, 90, 164, 250)).getpixel((40, 40))[:3]
    after = graded.crop((16, 90, 164, 250)).getpixel((40, 40))[:3]
    start, end = _hue(before), _hue(after)
    assert start is not None and end is not None
    delta = abs(start - end)
    assert min(delta, 360 - delta) < 12
