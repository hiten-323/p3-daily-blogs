"""Non-Mini days borrow Gourmet Duo Mini craft without posting that file."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _silence_music(monkeypatch, tmp_path):
    empty = tmp_path / "no-music"
    empty.mkdir()
    monkeypatch.setenv("MUSIC_LIBRARY_DIR", str(empty))
    monkeypatch.setenv("REEL_MUSIC_FILE", "")
    monkeypatch.setenv("STORY_MUSIC_FILE", "")


def test_mini_day_still_uses_the_template_file(tmp_path, monkeypatch):
    from content_generator.creative.jar_composer import build_reel_hook_prompt
    from content_generator.creative.product_reel_templates import (
        TEMPLATE_ID, TEMPLATE_PATH, attach_product_reel, resolve_reusable_reel,
    )
    from content_generator.creative.reel_video import build_reel_video

    _silence_music(monkeypatch, tmp_path)
    piece = {
        "product": "Gourmet Duo Mini",
        "hook_text": "TWO JARS",
        "caption": "Gourmet Duo Mini is Purista 50g and Purica 50g.",
    }
    selected = attach_product_reel(piece, featured_product="Ultra Blend")
    assert selected["template_id"] == TEMPLATE_ID
    assert piece["reference_reel_path"].endswith("gourmet_duo_mini.mp4")
    assert piece["product_slug"] == "gourmet_duo_mini"
    assert "reel_inspiration" not in piece
    assert resolve_reusable_reel(piece).endswith("gourmet_duo_mini.mp4")

    hooked = build_reel_hook_prompt(
        product="Gourmet Duo Mini",
        text="Gourmet Duo Mini",
        style_for="Ultra Blend",
        day=3,
    )
    assert hooked["reference_reel_template_id"] == TEMPLATE_ID
    assert hooked["reference_reel_path"].endswith("gourmet_duo_mini.mp4")
    assert "reel_inspiration" not in hooked

    monkeypatch.setenv("ENABLE_REEL_VIDEO", "true")
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    source = ROOT / TEMPLATE_PATH
    before = source.read_bytes()
    rendered = build_reel_video(
        piece, day=8, label="reel_1_video", on_date=date(2026, 10, 12),
    )
    assert rendered is not None
    assert rendered.endswith("reel_1_video_day8_2026-10-12.mp4")
    assert Path(rendered).read_bytes() == before
    assert source.read_bytes() == before
    assert os.path.basename(rendered) != "gourmet_duo_mini.mp4"


def test_non_mini_day_receives_style_cues_without_publishing_the_mini_file(tmp_path, monkeypatch):
    import sys

    from content_generator.creative.jar_composer import build_reel_hook_prompt
    from content_generator.creative.product_reel_templates import (
        TEMPLATE_PATH, attach_product_reels, resolve_reusable_reel,
    )
    from content_generator.creative.reel_video import build_reel_video
    from content_generator.creative.story_video import build_story_video

    source = ROOT / TEMPLATE_PATH
    before = source.stat().st_size
    caption = "Purista is pure Robusta."
    reel = {"product": "Purista", "hook_text": "READ THE LABEL", "caption": caption}
    content = {
        "featured_product": "Purista",
        "reels": [reel],
        "growth_reel": {"caption": "Why cafe coffee and home coffee differ."},
        "instagram_post": {"caption": caption, "product": "Purista"},
    }
    attach_product_reels(content, featured_product="Purista")

    inspiration = reel["reel_inspiration"]
    assert inspiration["mode"] == "style_cues"
    assert inspiration["publish_source_video"] is False
    assert inspiration["copied"] == {"pixels": False, "audio": False, "sku": False}
    assert inspiration["source_filename"] == "gourmet_duo_mini.mp4"
    assert inspiration["featured_product"] == "Purista"
    assert {cue["id"] for cue in inspiration["cues"]} == {
        "pacing", "framing", "storytelling", "aesthetic",
    }
    cue_text = " ".join(cue["cue"] for cue in inspiration["cues"]).lower()
    assert "jar-forward" in cue_text or "jar forward" in cue_text
    assert "two moods" in cue_text
    assert "zero chicory" not in cue_text
    assert "pure coffee" not in cue_text
    assert reel["caption"] == caption
    assert "reference_reel_path" not in reel
    assert reel.get("product_slug") != "gourmet_duo_mini"
    assert "reel_inspiration" not in content["growth_reel"]
    assert content["instagram_post"]["reel_inspiration"]["publish_source_video"] is False
    assert resolve_reusable_reel(reel) is None
    # A later brand-injection pass reads the piece again. Inspiration text must
    # not be mistaken for a Mini caption and swapped in as the posted file.
    attach_product_reels(content, featured_product="Purista")
    assert "reference_reel_path" not in reel
    assert reel.get("product_slug") != "gourmet_duo_mini"
    assert reel["reel_inspiration"]["publish_source_video"] is False

    unlabeled = {"hook_text": "READ THE LABEL", "caption": "Read the jar before you buy it."}
    unlabeled_day = {"reels": [unlabeled]}
    attach_product_reels(unlabeled_day, featured_product="Bold")
    attach_product_reels(unlabeled_day, featured_product="Bold")
    assert "reference_reel_path" not in unlabeled
    assert unlabeled.get("product_slug") != "gourmet_duo_mini"
    assert unlabeled["reel_inspiration"]["publish_source_video"] is False
    assert unlabeled["reel_inspiration"]["featured_product"] == "Bold"

    hooked = build_reel_hook_prompt(
        product="Ultra Blend",
        text="Gourmet Duo Mini is pure coffee. Ultra Blend is 70% coffee and 30% chicory.",
        style_for="Ultra Blend",
        day=2,
    )
    assert "reference_reel_template_id" not in hooked
    assert "reference_reel_path" not in hooked
    assert hooked["reel_inspiration"]["publish_source_video"] is False
    assert "two moods of Ultra Blend" in hooked["image_prompt"]
    assert "gourmet_duo_mini.mp4" not in hooked["image_prompt"]
    assert "gourmet_duo_mini.mp4" not in hooked["motion_prompt"]

    def fail_materialize(*_args, **_kwargs):
        raise AssertionError("non-mini render materialized the mini template")

    monkeypatch.setattr(
        "content_generator.creative.product_reel_templates.materialize_template",
        fail_materialize,
    )
    monkeypatch.setenv("ENABLE_REEL_VIDEO", "true")
    monkeypatch.setenv("ENABLE_STORY_VIDEO", "true")
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("REEL_MUSIC_FILE", "")
    monkeypatch.setitem(sys.modules, "moviepy", None)

    rendered = build_reel_video(
        reel, day=9, label="reel_1_video", on_date=date(2026, 10, 12),
    )
    assert rendered is None
    assert list(tmp_path.glob("*.mp4")) == []
    assert source.stat().st_size == before
    # A non-mini story would encode a 10s zoompan. ffmpeg without -nostdin
    # waits on pytest's stdin, so the suite never finishes. This test only
    # checks that the mini file is not what gets published.
    monkeypatch.setattr(
        "content_generator.creative.premium_cards.render_story_video",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("encode skipped")),
    )
    monkeypatch.setattr(
        "content_generator.creative.story_motion.render_story_motion",
        lambda *_a, **_k: None,
    )
    story = build_story_video(
        headline="PURISTA",
        day=9,
        on_date=date(2026, 10, 12),
        reference_text=caption,
    )
    # A non-mini day may render its own motion story, but never the mini file.
    assert story is None or (Path(story).stat().st_size != before and "gourmet_duo_mini" not in story)
    assert source.stat().st_size == before


def test_ultra_blend_zero_chicory_still_fails_and_is_not_stamped_by_inspiration():
    from content_generator.core.claim_verifier import verify_claims
    from content_generator.core.product_truth import product_truth_findings
    from content_generator.creative.product_reel_templates import (
        attach_product_reels, inspiration_prompt_block,
    )

    assert inspiration_prompt_block("Gourmet Duo Mini") == ""
    block = inspiration_prompt_block("Ultra Blend")
    assert "CREATIVE REFERENCE — STYLE ONLY" in block
    assert "Do not post that file" in block
    assert "gourmet_duo_mini.mp4" in block
    assert "digital silence" in block
    assert product_truth_findings(block) == []
    lowered = block.lower()
    assert "zero chicory" not in lowered
    assert "zero-chicory" not in lowered
    assert "no chicory" not in lowered
    assert "pure coffee" not in lowered
    assert "70% coffee" in block
    assert "30% chicory" in block

    findings = product_truth_findings("Ultra Blend is zero-chicory.")
    assert findings
    assert any("70% coffee" in item["reason"] and "30% chicory" in item["reason"] for item in findings)
    flagged = verify_claims("Ultra Blend is pure coffee with no chicory.")
    assert any(item["type"] == "product_truth" for item in flagged)
    assert product_truth_findings("Ultra Blend is 70% coffee and 30% chicory.") == []

    caption = "Ultra Blend is 70% coffee and 30% chicory."
    content = {"reels": [{"product": "Ultra Blend", "caption": caption}]}
    attach_product_reels(content, featured_product="Ultra Blend")
    reel = content["reels"][0]
    assert reel["caption"] == caption
    assert product_truth_findings(reel["caption"]) == []
    assert "reference_reel_path" not in reel
    assert reel.get("product_slug") != "gourmet_duo_mini"
    stamped = " ".join(cue["cue"] for cue in reel["reel_inspiration"]["cues"])
    assert product_truth_findings(caption + "\n" + stamped + "\n" + block) == []


def test_daily_generation_prompt_borrows_style_for_the_featured_sku(monkeypatch):
    from content_generator.pipeline import generator

    monkeypatch.setenv("ENABLE_USAGE_LOG", "false")
    monkeypatch.setattr(generator, "_extended_content_enabled", lambda: False)
    seen: list[tuple[str, str]] = []

    def fake_llm_call(prompt: str, label: str, max_tokens: int = 3000) -> dict:
        seen.append((label, prompt))
        if label == "video_prompts":
            return {"video_prompts": {}}
        return {"id": label, "caption": "Read the jar."}

    monkeypatch.setattr(generator, "llm_call", fake_llm_call)
    result = generator.generate_daily_content(day_number=0, research_context={})

    assert result["featured_product"] == "Ultra Blend"
    assert result["reel_inspiration"]["publish_source_video"] is False
    assert result["reel_inspiration"]["source_filename"] == "gourmet_duo_mini.mp4"
    assert result["reels"][0]["reel_inspiration"]["featured_product"] == "Ultra Blend"
    assert "reference_reel_path" not in result["reels"][0]
    assert result["reels"][0].get("product_slug") != "gourmet_duo_mini"
    assert "reel_inspiration" not in result["growth_reel"]

    prompts = [prompt for label, prompt in seen if label in {"reel_1", "video_prompts"}]
    assert len(prompts) == 2
    for prompt in prompts:
        assert "CREATIVE REFERENCE — STYLE ONLY" in prompt
        assert "Do not post that file" in prompt
        assert "gourmet_duo_mini.mp4" in prompt
        assert "Ultra Blend is 70% coffee and 30% chicory." in prompt
