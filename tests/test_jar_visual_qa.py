"""Fail-closed jar QA: a sharp full jar passes; blur and crop do not.

Fixtures are generated beside the test so the threshold is locked to pixels,
not to a live render.
"""
from __future__ import annotations

import json
import os

from PIL import Image, ImageDraw, ImageFilter

from content_generator.creative.jar_frame import (
    JAR_LAPLACIAN_MIN,
    audit_jar_region,
    audit_product_image,
    compose_conversion_frame,
    conversion_copy,
    select_front_asset,
)
from content_generator.publisher import instagram as ig

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "jar_qa")


def _striped_jar(width=900, height=1200, jar_box=(80, 180, 820, 1000)):
    image = Image.new("RGB", (width, height), (22, 14, 10))
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = jar_box
    for y in range(y0, y1):
        color = (240, 236, 228) if (y // 3) % 2 == 0 else (18, 12, 8)
        draw.line([(x0, y), (x1 - 1, y)], fill=color)
    return image


def _write_fixture(name, image, geometry):
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    path = os.path.join(FIXTURE_DIR, name)
    image.save(path, "PNG")
    with open(path + ".jar.json", "w", encoding="utf-8") as handle:
        json.dump(geometry, handle)
    return path


def _ensure_fixtures():
    width, height = 900, 1200
    safe = [40, 40, 860, 1160]
    sharp_box = [80, 180, 820, 1000]
    sharp = _striped_jar(width, height, tuple(sharp_box))
    blurred = sharp.filter(ImageFilter.GaussianBlur(radius=8))
    cropped_box = [80, 180, 820, height - 1]
    cropped = _striped_jar(width, height, tuple(cropped_box))
    common = {"jar_required": True, "text_boxes": [], "safe_zone": safe, "scale": 1.0}
    return {
        "sharp": _write_fixture("sharp_full_jar.png", sharp, {**common, "jar_bbox": sharp_box}),
        "blurred": _write_fixture("blurred_jar.png", blurred, {**common, "jar_bbox": sharp_box}),
        "cropped": _write_fixture("cropped_jar.png", cropped, {**common, "jar_bbox": cropped_box}),
    }


def test_sharp_full_jar_passes():
    path = _ensure_fixtures()["sharp"]
    result = audit_product_image(path)
    assert result["ok"], result
    assert result["sharpness"] >= JAR_LAPLACIAN_MIN


def test_blurred_jar_fails():
    path = _ensure_fixtures()["blurred"]
    result = audit_product_image(path)
    assert not result["ok"]
    assert any("jar_blurred" in issue for issue in result["issues"])
    assert result["sharpness"] < JAR_LAPLACIAN_MIN


def test_cropped_jar_fails():
    path = _ensure_fixtures()["cropped"]
    result = audit_product_image(path)
    assert not result["ok"]
    assert any("jar_cropped" in issue for issue in result["issues"])


def test_missing_geometry_fails_closed(tmp_path):
    path = tmp_path / "orphan.png"
    Image.new("RGB", (1080, 1350), (20, 10, 5)).save(path)
    result = audit_product_image(str(path))
    assert not result["ok"]
    assert any("jar_geometry_missing" in issue for issue in result["issues"])


def test_upscaled_geometry_fails():
    image = _striped_jar()
    result = audit_jar_region(
        image,
        jar_bbox=(80, 180, 820, 1000),
        text_boxes=[],
        safe_zone_box=(40, 40, 860, 1160),
        scale=1.25,
    )
    assert not result["ok"]
    assert "jar_upscaled" in result["issues"]


def test_text_covering_the_jar_fails():
    image = _striped_jar()
    result = audit_jar_region(
        image,
        jar_bbox=(80, 180, 820, 1000),
        text_boxes=[(100, 400, 700, 460)],
        safe_zone_box=(40, 40, 860, 1160),
        scale=1.0,
    )
    assert not result["ok"]
    assert "jar_covered_by_text" in result["issues"]


def test_bold_feed_and_story_pass_and_do_not_upscale(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    feed = compose_conversion_frame(
        headline="CAFE STRENGTH AT HOME",
        product="Bold",
        width=1080,
        height=1350,
        label="feed_bold",
        format_name="feed",
        on_date="2026-10-13",
        out_dir=str(tmp_path),
    )
    story = compose_conversion_frame(
        product="Bold",
        width=1080,
        height=1920,
        label="story_bold",
        format_name="story",
        on_date="2026-10-13",
        out_dir=str(tmp_path),
    )
    assert feed and story
    for path in (feed, story):
        result = audit_product_image(path)
        assert result["ok"], result
        geometry = json.loads(open(path + ".jar.json", encoding="utf-8").read())
        assert geometry["scale"] <= 1.0
        assert "bold_50g_front" in geometry["source_asset"]


def test_bold_uses_the_complete_front_not_the_edge_cropped_100g():
    chosen = select_front_asset("Bold")
    assert chosen is not None
    assert chosen["path"].endswith("puritybeans_bold_50g_front.png")
    assert chosen["margin"] >= 12


def test_ultra_copy_stays_70_30_and_prima_has_no_price():
    ultra = conversion_copy("Ultra Blend")
    blob = " ".join(ultra.values()).upper()
    assert "70%" in blob and "30%" in blob
    assert "ZERO CHICORY" not in blob
    assert "ROASTED ROOT" not in blob
    assert "209" in ultra["offer"]

    prima = conversion_copy("Prima")
    prima_blob = " ".join(prima.values()).upper()
    assert "OUT OF STOCK" in prima_blob
    assert prima["offer"] == ""
    assert "ZERO CHICORY" not in prima_blob

    bold = conversion_copy("Bold")
    assert "239" in bold["offer"]
    assert "ZERO CHICORY" in bold["benefit"].upper()
    assert "P3ONLINE.IN" in bold["cta"]
    assert "FOLLOW" in bold["cta"]


def test_letterbox_keeps_the_top_and_bottom_of_a_story_frame(tmp_path):
    src = tmp_path / "reel_thumb.jpg"
    image = Image.new("RGB", (1080, 1920), (12, 8, 6))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1079, 24), fill=(0, 0, 255))
    draw.rectangle((0, 1890, 1079, 1919), fill=(255, 0, 0))
    image.save(src, "JPEG", quality=95)
    feed = ig.prepare_feed_image(str(src))
    assert feed and feed != str(src)
    with Image.open(feed) as out:
        assert out.size == (1080, 1350)
        top = out.getpixel((out.size[0] // 2, 2))
        bottom = out.getpixel((out.size[0] // 2, out.size[1] - 2))
    assert top[2] > top[0] + 40
    assert bottom[0] > bottom[2] + 40
