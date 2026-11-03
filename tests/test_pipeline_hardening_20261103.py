"""Regression tests for 3 Nov 2026 pipeline hardening and video learning loop."""
import ast
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_slot_contract_growth_reel_morning_reel_1_evening():
    from content_generator.core.reel_schedule import (
        REEL_SLOT,
        RETIRED_REELS,
        MAX_REELS_PER_DAY,
        MIN_REEL_GAP_HOURS,
        reel_for_slot,
        slot_for_reel,
    )
    assert REEL_SLOT["growth_reel"] == "morning"
    assert REEL_SLOT["reel_1"] == "evening"
    assert "reel_2" not in REEL_SLOT
    assert "reel_2" in RETIRED_REELS
    assert MAX_REELS_PER_DAY == 2
    assert MIN_REEL_GAP_HOURS >= 3
    assert reel_for_slot("morning") == "growth_reel"
    assert reel_for_slot("evening") == "reel_1"
    assert slot_for_reel("growth_reel") == "morning"
    assert slot_for_reel("reel_1") == "evening"


def test_no_reel_2_anywhere_in_generation_or_schema():
    from content_generator.core.editorial_engine import REQUIRED_DAILY_ASSETS
    assert "reel_2" not in REQUIRED_DAILY_ASSETS

    gen_src = (ROOT / "content_generator/pipeline/generator.py").read_text(encoding="utf-8")
    tree = ast.parse(gen_src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "reel_2" not in names
    assert "arch_2" not in names


def test_retry_unposted_matches_by_asset_and_refuses_permanent_claims():
    from content_generator.scheduler import retry_unposted as ru

    # 1. Matching by asset, not only slot
    rec_r1 = {"slot": "evening", "platform": "instagram_reel", "status": "PUBLISHED", "asset": "reel_1"}
    assert ru._asset_matches(rec_r1, "reel_1") is True
    assert ru._asset_matches(rec_r1, "growth_reel") is False

    # 2. Permanent claim rejection stops retry loop
    rec_skipped = [{
        "slot": "morning",
        "platform": "instagram_story",
        "asset": "ig_story",
        "status": "SKIPPED",
        "error": "prepublish_gate: process_match_failed",
    }]
    assert ru.target_refuses_retry(rec_skipped, "ig_story") is True

    # 3. Transitory error remains retryable
    rec_transitory = [{
        "slot": "morning",
        "platform": "instagram_story",
        "asset": "ig_story",
        "status": "FAILED",
        "attempt_count": 1,
        "error": "network_timeout",
    }]
    assert ru.target_refuses_retry(rec_transitory, "ig_story") is False


def test_approved_photos_priority_studio_cutouts():
    from content_generator.creative import approved_photos as ap
    src = (ROOT / "content_generator/creative/approved_photos.py").read_text(encoding="utf-8")
    # Verify no artificial 'reals' override bypassing cutout QA
    assert "reals = [i for i in pool if i.get(\"type\") == \"real_photo\"]" not in src


def test_story_copy_normalization_and_process_match():
    from content_generator.prompts import stories
    from content_generator.core.process_match import process_match_findings

    prompt = stories.build(day=1)
    assert "Purista: freeze-dried vs Bold: agglomerated" in prompt
    assert "Always name the product with each process" in prompt

    # An untied comparison on Purista day fails process match
    untied = process_match_findings("FREEZE-DRIED VS AGGLOMERATED\nWhich process makes a cleaner cup?", featured="Purista")
    assert untied
    assert "agglomerated mention must match Bold" in untied[0]["reason"]

    # A comparison naming the product with each process passes process match cleanly
    tied = process_match_findings("PURISTA: FREEZE-DRIED VS BOLD: AGGLOMERATED\nWhich process makes a cleaner cup?", featured="Purista")
    assert tied == []


def test_story_exposure_check_present():
    daily_src = (ROOT / "content_generator/scheduler/daily.py").read_text(encoding="utf-8")
    assert "audit_rendered_images([story_frame])" in daily_src
    assert "exposure_boost=True" in daily_src
