"""Gourmet Duo Mini reel template is discoverable and claim-safe."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _silence_music(monkeypatch, tmp_path):
    empty = tmp_path / "no-music"
    empty.mkdir()
    monkeypatch.setenv("MUSIC_LIBRARY_DIR", str(empty))
    monkeypatch.setenv("REEL_MUSIC_FILE", "")
    monkeypatch.setenv("STORY_MUSIC_FILE", "")


def test_template_file_is_a_reusable_vertical_mp4():
    from content_generator.creative.product_reel_templates import TEMPLATE_PATH, template_record

    record = template_record()
    assert record is not None
    path = ROOT / record["path"]
    assert path.is_file()
    assert Path(record["path"]) == Path(TEMPLATE_PATH)
    assert "hero_videos" not in Path(record["path"]).parts
    assert path.stat().st_size > 1_000_000
    assert b"ftyp" in path.read_bytes()[:32]
    assert record["reusable"] is True
    assert record["audio_embedded"] is False
    assert record["width"] == 1080
    assert record["height"] == 1920
    assert record["duration_s"] == 10
    probe = shutil.which("ffprobe")
    if not probe:
        return
    import json
    import subprocess
    proc = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode == 0
    info = json.loads(proc.stdout)
    video = next(stream for stream in info["streams"] if stream.get("codec_type") == "video")
    assert int(video["width"]) == 1080
    assert int(video["height"]) == 1920
    assert abs(float(info["format"]["duration"]) - 10) < 0.2


def test_pipeline_selects_the_template_for_the_mini_sku_only():
    from content_generator.creative.jar_composer import build_reel_hook_prompt
    from content_generator.creative.product_reel_templates import (
        TEMPLATE_ID, attach_product_reels, select_product_reel,
    )
    from content_generator.scheduler.slots import _HERO_DIR

    mini = select_product_reel(product="Gourmet Duo Mini")
    assert mini["template_id"] == TEMPLATE_ID
    assert mini["sku"] == "PB-GOURMET-DUO-50"
    assert mini["price_inr"] == 570
    assert mini["compare_at_inr"] == 648
    sku = select_product_reel(text="PB-GOURMET-DUO-50 on p3online.in")
    assert sku["path"] == mini["path"]
    assert select_product_reel(product="Gourmet Duo") is None
    assert select_product_reel(product="Purista") is None
    assert select_product_reel(text="Purista 50g granules") is None
    assert select_product_reel(product="Ultra Blend", text="Gourmet Duo Mini is pure coffee") is None
    assert select_product_reel(text="Ultra Blend is zero-chicory. Gourmet Duo Mini is pure coffee.") is None

    hero = os.path.abspath(_HERO_DIR)
    asset = os.path.abspath(mini["path"])
    assert os.path.commonpath([hero, asset]) != hero

    hooked = build_reel_hook_prompt(product="Gourmet Duo Mini", day=3)
    assert hooked["reference_reel_template_id"] == TEMPLATE_ID
    assert hooked["reference_reel_audio_embedded"] is False
    assert "reference_reel_template_id" not in build_reel_hook_prompt(product="Ultra Blend", day=3)

    content = {
        "reels": [{
            "hook_text": "TWO JARS",
            "caption": "Gourmet Duo Mini is Purista 50g and Purica 50g. Pure coffee, no chicory.",
        }],
        "growth_reel": {"caption": "Ultra Blend is 70% coffee and 30% chicory."},
        "stories": {"story_1": {"headline": "GOURMET DUO MINI", "subtext": "pure coffee, no chicory."}},
    }
    attach_product_reels(content)
    assert content["reels"][0]["reference_reel_template_id"] == TEMPLATE_ID
    assert content["reels"][0]["product_slug"] == "gourmet_duo_mini"
    assert all("ultra" not in path for path in content["reels"][0]["reference_jar_paths"])
    assert "reference_reel_path" not in content["growth_reel"]
    assert content["stories"]["story_1"]["reference_reel_template_id"] == TEMPLATE_ID

    stolen = {
        "product": "Ultra Blend",
        "caption": "Ultra Blend is 70% coffee.",
        "reference_reel_template_id": TEMPLATE_ID,
        "reference_reel_path": mini["path"],
        "product_slug": "gourmet_duo_mini",
    }
    attach_product_reels({"reels": [stolen]})
    assert "reference_reel_path" not in stolen
    assert stolen.get("product_slug") != "gourmet_duo_mini"


def test_jar_references_follow_the_duo_and_not_ultra_blend():
    from content_generator.core.brand_guard import get_product_references

    mini = get_product_references("Gourmet Duo Mini | Purista 50g + Purica 50g")
    assert mini
    assert all("purista_50g" in path or "purica_50g" in path for path in mini)
    assert not any("ultra" in path or "100g" in path for path in mini)

    full = get_product_references("Gourmet Duo 100g gift")
    assert full
    assert all("100g" in path for path in full)
    assert any("purista" in path for path in full)
    assert not any("ultra" in path for path in full)

    ultra = get_product_references("Ultra Blend morning jar")
    assert ultra and all("ultra_blend" in path for path in ultra)

    both = get_product_references("Gourmet Duo Mini next to Ultra Blend")
    assert any("purista_50g" in path or "purica_50g" in path for path in both)
    assert any("ultra_blend" in path for path in both)


def test_claims_allow_zero_chicory_on_the_duo_and_reject_it_on_ultra_blend():
    from content_generator.core.claim_verifier import verify_claims
    from content_generator.core.product_truth import product_truth_findings
    from content_generator.core.shopify_catalog import format_catalog_for_prompt
    from content_generator.creative.audio_director import get_audio_plan
    from content_generator.creative.product_reel_templates import allowed_claim_text

    text = allowed_claim_text()
    assert "pure coffee" in text
    assert "no chicory" in text
    assert "lead-free" in text.lower()
    assert "food grade" in text.lower()
    assert "₹570" in text
    assert "₹648" in text
    assert "https://p3online.in" in text
    assert "12% off" not in text
    assert "Ultra Blend" not in text
    assert verify_claims(text) == []
    assert product_truth_findings("Gourmet Duo Mini is zero-chicory.") == []
    assert product_truth_findings("Gourmet Duo Mini is pure coffee with no chicory.") == []
    assert product_truth_findings("Gourmet Duo Mini is lower caffeine.")
    assert product_truth_findings("Gourmet Duo Mini is pure Arabica.")
    assert product_truth_findings("Gourmet Duo Mini is 30% chicory.")
    assert product_truth_findings("Purica is pure Arabica.") == []

    flagged = verify_claims("Ultra Blend is pure coffee with no chicory.")
    assert any(item["type"] == "product_truth" for item in flagged)
    assert product_truth_findings("Ultra Blend is zero-chicory.")
    assert product_truth_findings("Ultra Blend is 70% coffee and 30% chicory.") == []

    prompt = format_catalog_for_prompt()
    assert "Gourmet Duo Mini" in prompt
    assert "Do not describe Ultra Blend as zero chicory" in prompt

    plan = get_audio_plan(text, day=1)
    assert plan["trend_status"] == "not_live_verified"
    assert plan["audio_name"] is None
    assert plan["audio_attached"] is False
    assert plan["rights_check_required"] is True


def test_daily_render_reuses_the_template_without_posting_or_consuming_it(tmp_path, monkeypatch):
    from datetime import date

    from content_generator.creative.product_reel_templates import (
        TEMPLATE_PATH, resolve_reusable_reel, template_record,
    )
    from content_generator.creative.reel_video import build_reel_video
    from content_generator.creative.story_video import build_story_video

    _silence_music(monkeypatch, tmp_path)
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    source = ROOT / TEMPLATE_PATH
    before = source.stat().st_size

    monkeypatch.setenv("ENABLE_REEL_VIDEO", "false")
    assert build_reel_video({"product": "Gourmet Duo Mini"}, day=4, on_date=date(2026, 10, 12)) is None

    monkeypatch.setenv("ENABLE_REEL_VIDEO", "true")
    rendered = build_reel_video(
        {"product": "Gourmet Duo Mini", "hook_text": "TWO GOURMET JARS"},
        day=4,
        label="reel_1_video",
        on_date=date(2026, 10, 12),
    )
    assert rendered is not None
    assert rendered.endswith("reel_1_video_day4_2026-10-12.mp4")
    assert Path(rendered).is_file()
    assert Path(rendered).stat().st_size == before
    assert source.stat().st_size == before
    assert os.path.abspath(rendered) != os.path.abspath(source)

    assert resolve_reusable_reel({"product": "Ultra Blend", "hook_text": "70% coffee"}) is None

    story = build_story_video(
        headline="GOURMET DUO MINI",
        day=4,
        label="story_video",
        on_date=date(2026, 10, 12),
        reference_text="Gourmet Duo Mini. Pure coffee, no chicory.",
    )
    assert story is not None
    assert story.endswith("story_video_day4_2026-10-12.mp4")
    other = build_story_video(headline="READ THE LABEL", day=4, reference_text="Read the jar.")
    # Non-mini days get their own motion story (or nothing) — never the mini file.
    assert other is None or Path(other).stat().st_size != before
    assert template_record()["audio_embedded"] is False
