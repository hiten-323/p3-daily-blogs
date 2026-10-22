import json

from content_generator.core.brand_validator import banned_claim_hits, validate_asset_copy


def test_flags_fresh_lab_tested_zero_acidity():
    assert banned_claim_hits("Keep it fresh. Lab-tested. Zero acidity.") == ["fresh", "lab-tested", "zero acidity"]
    assert banned_claim_hits("Freshly opened. Lab tested. Zero acid.") == ["freshly", "lab tested", "zero acid"]
    assert "freshness" in banned_claim_hits("The freshness is the whole point.")


def test_refresh_is_not_flagged():
    assert banned_claim_hits("Refresh your shelf at p3online.in") == []


def test_validator_rejects_fresh_copy():
    ok, issues = validate_asset_copy("Purity Beans pure coffee tastes as fresh as the first cup.",
                                     check_brand_facts=False, check_length=False)
    assert not ok and any("banned claim" in i for i in issues)


def test_generation_prompts_state_the_ban():
    from content_generator.prompts.brand import brand_block
    from content_generator.prompts.growth_engine.platforms import generation_preface

    brand = brand_block().lower()
    preface = generation_preface("Bold", 1).lower()
    for text in (brand, preface):
        assert "zero acidity" in text
        assert "lab tested" in text
        assert "freshly" in text
        assert "refresh is allowed" in text


def test_banned_claim_lesson_stays_in_the_prompt(tmp_path, monkeypatch):
    from content_generator.core import obstacle_lessons
    from content_generator.prompts.facebook import regeneration_prompt
    from content_generator.prompts.growth_engine.platforms import prompt_block

    path = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(path))
    obstacle_lessons.record(
        "facebook", "facebook_post", "generation", "banned_claim",
        "Copy used a banned claim: fresh, freshly, freshness, lab tested, or zero acidity.",
        "The copy gate rejects those phrases.",
        fix="Never write fresh, freshly, freshness, lab tested, or zero acidity. refresh is allowed.",
        status="gate_holding",
        first_seen="2026-10-01",
        last_seen="2026-10-01",
    )
    for i in range(12):
        obstacle_lessons.record(
            "facebook", "facebook_post", "generation", "editorial",
            f"distinct miss {i} " + ("word " * 20),
            "",
            count=50,
            last_seen="2026-10-22",
        )
    block = obstacle_lessons.prompt_block("facebook_post")
    assert len(block) <= 900
    assert "banned_claim" in block
    assert "zero acidity" in block
    regen = regeneration_prompt({"featured_product": "Bold"}, "too generic", 8.0, "BRAND")
    assert "zero acidity" in regen
    assert "banned_claim" in prompt_block("facebook_post", "Bold", 1)


def test_seeded_lessons_cover_generation_platforms():
    lessons = json.loads(
        open("output/learning/obstacle_lessons.json", encoding="utf-8").read()
    )["lessons"]
    covered = {
        row["platform"] for row in lessons
        if row.get("gate") == "banned_claim" and row.get("status") != "external"
    }
    assert {
        "facebook", "instagram", "threads", "linkedin", "youtube", "shopify",
        "instagram_story", "instagram_campaign",
    } <= covered
