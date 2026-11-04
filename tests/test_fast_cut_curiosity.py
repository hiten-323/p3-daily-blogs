"""fast_cut_curiosity template, reference structure, and video fallbacks."""
import json
import logging

import pytest

from content_generator.core.brand_guard import EDITORIAL_THRESHOLD
from content_generator.core.brand_validator import banned_claim_hits
from content_generator.core.fallback_ladder import PASS_FLOOR
from content_generator.core.process_match import process_match_findings
from content_generator.core.product_truth import product_truth_findings
from content_generator.core.viral_gate import PASS_MARK
from content_generator.creative import ai_backgrounds, hf_video, ken_burns, video_fallbacks
from content_generator.creative.growth_reel_templates import (
    DURATION_S,
    REFERENCE_LIBRARY,
    SPOKEN,
    TEMPLATE_ID,
    prompt_block,
    stamp,
    store_link,
)
from content_generator.prompts.growth_reel import GROWTH_FORMATS, build, format_for_day


def _fast_day() -> int:
    for day in range(len(GROWTH_FORMATS) * 4):
        if format_for_day(day) == TEMPLATE_ID:
            return day
    raise AssertionError("fast_cut_curiosity missing from the growth rotation")


def test_gates_stay_at_eight():
    assert PASS_MARK == 8.0
    assert PASS_FLOOR == 8.0
    assert EDITORIAL_THRESHOLD == 8.0
    assert DURATION_S == 34
    assert 30 <= DURATION_S <= 40
    assert DURATION_S <= 35


def test_template_is_in_the_growth_rotation_and_prompt():
    assert TEMPLATE_ID in GROWTH_FORMATS
    day = _fast_day()
    assert format_for_day(day) == TEMPLATE_ID
    # Value-unlock (every 4th day) must not replace this template when both land together.
    span = len(GROWTH_FORMATS)
    collision = GROWTH_FORMATS.index(TEMPLATE_ID)
    while collision % 4 != 0:
        collision += span
    assert format_for_day(collision) == TEMPLATE_ID
    prompt = build(day, "")
    assert "FAST CUT CURIOSITY" in prompt
    assert "utm_source=instagram" in prompt
    assert "utm_medium=growth_reel" in prompt
    assert "utm_campaign=fast_cut_curiosity" in prompt
    assert "Comment CUP" in prompt
    assert "No crossfades" in prompt or "No crossfade" in prompt
    assert "4022" not in prompt
    assert "1572" not in prompt
    link = store_link("cup")
    assert link.startswith("https://p3online.in/?")
    assert "utm_content=cup" in link


def test_spoken_lines_and_prompt_hold_the_claim_rules():
    block = prompt_block()
    spoken = " ".join(SPOKEN.values()) + " " + store_link("cup")
    assert banned_claim_hits(spoken) == []
    for phrase in (
        "100%", "single-origin", "single origin", "lab tested", "lab-tested",
        "zero acidity", "secret discount", "free sample", "don't want you to know",
        "cafes don't want",
    ):
        assert phrase not in spoken.lower()
        assert phrase not in block.lower()
    assert "70% coffee and 30% chicory" in block
    assert "coffee-only jar" in block
    assert "Freeze-dried names Purica and Purista only." in block
    assert "Agglomerated names Bold and Prima only." in block
    assert "reel_2" not in block
    assert "₹" not in block
    assert product_truth_findings(block) == []
    assert process_match_findings(block) == []
    notes = " ".join(REFERENCE_LIBRARY[0]["structure_notes"]).lower()
    assert "spoon" in notes and "hard cut" in notes
    assert banned_claim_hits(notes) == []


def test_reference_library_is_structure_only():
    entry = REFERENCE_LIBRARY[0]
    assert entry["handle"] == "lenabrooks.ai"
    assert entry["url"].endswith("/Db5TJjviR08/")
    assert entry["width"] == 1080 and entry["height"] == 1920
    assert entry["duration_s"] == 37
    assert entry["observed_comments"] > entry["observed_likes"]
    assert entry["publish_source_video"] is False
    assert entry["not_a_performance_sample"] is True
    assert entry["copied"] == {
        "pixels": False, "audio": False, "script": False, "captions": False, "keyword": False,
    }
    blob = json.dumps(entry["structure_notes"])
    assert "HiddenAI" not in blob
    assert "Comment" not in blob or "keyword" not in blob.lower()
    piece = stamp({"caption": "Teach the pour.", "chosen_hook": "Watch the pour."})
    assert piece["growth_template_id"] == TEMPLATE_ID
    assert piece["duration_seconds"] == 34
    assert piece["comment_trigger"] == SPOKEN["cta"]
    assert piece["caption"] == "Teach the pour."
    assert piece["reference_copied"]["script"] is False
    assert "4022" not in json.dumps(piece)


def test_learning_uses_real_views_not_the_reference_counts(tmp_path, monkeypatch):
    from content_generator.core import video_learning as vl
    learn = tmp_path / "learning"
    learn.mkdir()
    monkeypatch.setattr(vl, "_LEARNING_DIR", str(learn))
    monkeypatch.setattr(vl, "_DEFAULT_OUTPUT_DIR", str(tmp_path))
    (learn / "follower_snapshots.json").write_text(json.dumps([
        {"date": "2026-10-28", "count": 40},
        {"date": "2026-11-04", "count": 46},
    ]), encoding="utf-8")
    empty = vl.build_video_learning_directive("instagram")
    assert "No measured views yet for fast_cut_curiosity" in empty
    assert "4022" not in empty
    (learn / "performance_log.json").write_text(json.dumps([
        {
            "hook": "Watch what the spoon does next.",
            "platform": "instagram",
            "format": "fast_cut_curiosity",
            "metrics": {"views": 880, "comments": 40, "follows_gained": 6},
        }
    ]), encoding="utf-8")
    filled = vl.build_video_learning_directive("instagram")
    assert "880 views" in filled
    assert "6 follows" in filled
    assert "46" in filled
    assert "4022" not in filled
    assert "1572" not in filled


def test_provider_order_puts_new_models_after_the_current_ones():
    assert ai_backgrounds.PROVIDER_ORDER == (
        "kaggle_bank", "hf_ltx", "hf_wan", "pixazo", "runway", "pexels", "pixabay",
        "hf_cogvideo", "hf_hunyuan", "hf_wan_i2v",
    )
    assert hf_video.space_call("zai-org/CogVideoX-2B-Space", "steam rising")[0] == "generate"


def test_missing_token_skips_new_providers(monkeypatch):
    from content_generator.creative import kaggle_bank
    ai_backgrounds.reset_session()
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(kaggle_bank, "available", lambda: False)
    called = []
    monkeypatch.setattr(video_fallbacks, "cogvideo", lambda *a, **k: called.append("cog"))
    monkeypatch.setattr(video_fallbacks, "hunyuan", lambda *a, **k: called.append("hunyuan"))
    monkeypatch.setattr(video_fallbacks, "wan_i2v", lambda *a, **k: called.append("i2v"))
    frames, source = ai_backgrounds.fetch_background(
        {"date": "2026-11-04", "format": "reel", "concept": "steam_backlight", "ai_prompt": "steam"},
        "lab", (8, 8), 5,
    )
    assert frames is None and source == "procedural"
    assert called == []


def test_fallback_failure_is_a_lesson_and_hides_the_token(tmp_path, monkeypatch, caplog):
    from content_generator.creative import kaggle_bank
    ai_backgrounds.reset_session()
    caplog.set_level(logging.INFO)
    secret = "hf_super_secret_token_value"
    monkeypatch.setenv("HF_TOKEN", secret)
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(tmp_path / "lessons.json"))
    for name in ("PIXAZO_API_KEY", "RUNWAY_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kaggle_bank, "available", lambda: False)
    monkeypatch.setattr(hf_video, "ltx", lambda *a, **k: None)
    monkeypatch.setattr(hf_video, "wan", lambda *a, **k: None)
    hf_video._AUTH_DEAD = False

    def boom(*_a, **_k):
        raise RuntimeError(secret)

    monkeypatch.setattr(hf_video, "_space", boom)
    monkeypatch.setattr(hf_video, "_inference", lambda *a, **k: ("timeout", secret.encode(), "text/plain"))
    monkeypatch.setattr(hf_video, "_request", lambda *a, **k: ("error", secret.encode(), "text/plain"))
    frames, source = ai_backgrounds.fetch_background(
        {"date": "2026-11-04", "format": "reel", "concept": "steam_backlight", "ai_prompt": "steam"},
        "lab", (8, 8), 5,
    )
    assert frames is None and source == "procedural"
    text = (tmp_path / "lessons.json").read_text(encoding="utf-8")
    assert "hf_cogvideo" in text
    assert "timeout" in text or "RuntimeError" in text
    assert secret not in text
    assert secret not in caplog.text


def test_i2v_payload_is_ambience_not_a_product_photo():
    still = video_fallbacks.ambience_jpeg()
    assert still[:2] == b"\xff\xd8"
    payload = video_fallbacks.i2v_payload(video_fallbacks.safe_prompt({"ai_prompt": "steam"}), still)
    blob = json.dumps(payload)
    assert "approved_photos" not in blob
    assert "no jar" in blob
    assert "packaging" in blob
    assert still.decode("latin1") not in blob or "base64" in blob


def test_shot_plan_is_hard_cuts_with_punch_in():
    plan = ken_burns.shot_plan(34, 4, split=True)
    assert plan[0]["split"] is True
    assert plan[0]["transition"] == "cut"
    total = 0.0
    for shot in plan:
        assert shot["punch_in"] is True
        assert shot["transition"] == "cut"
        assert 1.0 <= shot["seconds"] <= 3.0
        total += shot["seconds"]
    assert 30 <= total <= 40
    graph = ken_burns.filtergraph(2, plan[:2], ["Watch", "the", "pour"], None)
    assert "xfade" not in graph
    assert "zoompan" in graph
    assert "concat" in graph


def test_photo_fallback_renders_a_real_file(tmp_path, monkeypatch):
    from PIL import Image
    one = tmp_path / "jar_a.png"
    two = tmp_path / "jar_b.png"
    Image.new("RGB", (32, 48), (90, 40, 20)).save(one)
    Image.new("RGB", (32, 48), (40, 20, 10)).save(two)
    monkeypatch.setattr(ken_burns, "real_product_paths", lambda sku=None: [str(one), str(two)])
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("KEN_BURNS_FAST_S", "2")
    monkeypatch.setenv("MUSIC_LIBRARY_DIR", str(tmp_path / "nomusic"))
    if ken_burns._ffmpeg() is None:
        pytest.skip("ffmpeg is not installed")
    out = ken_burns.render_reel(
        {"growth_template_id": "fast_cut_curiosity", "chosen_hook": "Watch the pour"},
        3, "growth_reel", "2026-11-04", fast=True,
    )
    assert out and out.endswith(".mp4")
    assert (tmp_path / "growth_reel_day3_2026-11-04.mp4").stat().st_size > 1000
