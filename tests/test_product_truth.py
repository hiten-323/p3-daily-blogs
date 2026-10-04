"""Product-truth, blog SEO, and the checks that were blocking CI."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ultra_blend_cannot_inherit_pure_jar_claims():
    from content_generator.core.claim_verifier import verify_claims

    flagged = verify_claims("Ultra Blend is 100% coffee with zero chicory.")
    assert any(item["type"] == "product_truth" for item in flagged)

    clean = verify_claims("Ultra Blend is 70% coffee, so a lower-caffeine cup is fair.")
    assert clean == []


def test_low_caffeine_is_only_for_ultra_blend():
    from content_generator.core.product_truth import product_truth_findings

    assert product_truth_findings("Bold is a lower caffeine coffee.")
    assert product_truth_findings("Ultra Blend is lower caffeine.") == []


def test_negation_does_not_hide_a_later_pure_claim():
    from content_generator.core.product_truth import product_truth_findings

    assert product_truth_findings("Ultra Blend is not 100% coffee.") == []
    assert product_truth_findings("Ultra Blend is not chicory-free.") == []
    assert product_truth_findings(
        "Ultra Blend is not a compromise and it is 100% coffee with zero chicory."
    )
    assert product_truth_findings("Ultra Blend doesn't contain chicory.")
    assert product_truth_findings(
        "Ultra Blend is 70% coffee, Bold is 100% coffee with zero chicory."
    ) == []


def test_prima_is_agglomerated_arabica():
    from content_generator.core.product_truth import product_truth_findings

    assert product_truth_findings("Prima is freeze-dried 100% Robusta.")
    assert product_truth_findings("Premium Agglomerate is 100% Arabica.") == []
    assert product_truth_findings(
        "Ultra Blend is 70% coffee, while Bold is 100% coffee with zero chicory."
    ) == []


def test_true_jar_percentages_are_kept_and_mixed_stats_are_not():
    from content_generator.scheduler.daily import _strip_unsupported_stats as strip

    kept = "Ultra Blend is 70% coffee."
    assert strip(kept) == kept
    arabica = "Prima is 100% Arabica."
    assert strip(arabica) == arabica
    assert strip("We sell 100% coffee and 40% chicory.").strip() == ""


def test_pure_coffee_catalog_excludes_ultra_and_the_variety_box():
    from content_generator.core.shopify_catalog import (
        SHOPIFY_PRODUCTS,
        format_catalog_for_prompt,
        get_pure_coffee_products,
    )

    slugs = {p["slug"] for p in get_pure_coffee_products()}
    assert "prima" in slugs
    assert "purica" in slugs
    assert "ultra_blend" not in slugs
    assert "variety_box" not in slugs
    assert SHOPIFY_PRODUCTS["prima"]["process"] == "Premium Agglomerate"
    assert "Freeze" not in SHOPIFY_PRODUCTS["prima"]["process"]
    assert SHOPIFY_PRODUCTS["ultra_blend"]["coffee_percent"] == 70
    prompt = format_catalog_for_prompt()
    assert "70% coffee" in prompt
    assert "hand-selected" not in prompt
    assert "OUT OF STOCK" in prompt


def test_brand_prompt_does_not_invent_purity_multiplier():
    from content_generator.prompts.brand import brand_block

    text = brand_block()
    assert "100x purer" not in text
    assert "70% coffee" in text
    assert "Premium Agglomerate" in text


def test_blog_links_lose_glued_punctuation_and_duplicates_are_caught(tmp_path):
    from content_generator.core.blog_quality import assess, normalize_text

    raw = "Shop at https://p3online.in.</p>"
    assert normalize_text(raw) == "Shop at https://p3online.in</p>"
    day = tmp_path / "content_2026-09-01.json"
    day.write_text(
        '{"blog_post": {"slug": "already-used", "title": "Already used title for the blog"}}',
        encoding="utf-8",
    )
    issues = assess(
        {
            "title": "A specific title about reading the coffee label",
            "meta_description": "P" * 140,
            "slug": "already-used",
            "body": "Purica is freeze-dried 100% Arabica.",
        },
        on_date="2026-10-04",
        output_dir=str(tmp_path),
    )
    assert any("already-used" in item for item in issues)


def test_shopify_article_body_uses_plain_text_body():
    from content_generator.publisher.shopify_blog import _article_body

    html_out = _article_body({
        "body": "Shop at https://p3online.in.\n\nBold is 100% Robusta.",
        "introduction": "Read the jar.",
    })
    assert "<p>Shop at https://p3online.in</p>" in html_out
    assert "<p>Read the jar.</p>" in html_out
    assert "&lt;" not in html_out or "<script>" not in html_out
    escaped = _article_body({"body": "A <b>bold</b> claim"})
    assert "<b>" not in escaped
    assert "&lt;b&gt;" in escaped


def test_blog_requires_slug_and_meta_when_it_has_copy():
    from content_generator.core.blog_quality import assess

    issues = assess({"title": "How to read an instant coffee label", "body": "Purica is 100% Arabica."})
    assert any("slug" in item for item in issues)
    assert any("meta" in item for item in issues)


def test_live_content_file_is_not_the_generation_fixture():
    text = (ROOT / "tests" / "test_generation_validation.py").read_text(encoding="utf-8")
    assert "tests/fixtures/day275_pre_repair.json" in text
    assert 'output" / "content_2026-10-03.json' not in text


def test_one_time_repair_workflow_is_gone():
    assert not (ROOT / ".github" / "workflows" / "repair_once.yml").exists()


def test_save_content_assigns_generation_id_to_fallback(tmp_path):
    import json
    from content_generator.pipeline.generator import save_content

    payload = {"day_number": 249, "_source": "emergency_fallback_evergreen", "reels": []}
    path = save_content(payload, output_dir=str(tmp_path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["generation_id"].startswith("fallback_")
    assert data["day_number"] == 249
    assert data["date"]


def test_default_hashtags_do_not_call_every_jar_freeze_dried():
    names = (
        "content_generator/scheduler/daily.py",
        "content_generator/core/piece_integrity.py",
        "content_generator/publisher/instagram.py",
        "content_generator/prompts/reels.py",
        "content_generator/analytics/hashtag_bank.py",
    )
    for name in names:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "FreezeDriedCoffee" not in text, name
        assert "SingleOrigin" not in text, name


def test_day_number_uses_ist():
    text = (ROOT / "content_generator" / "rotation.py").read_text(encoding="utf-8")
    assert "today_ist()" in text
    lock = (ROOT / "content_generator" / "scheduler" / "run_lock.py").read_text(encoding="utf-8")
    assert "date.today()" not in lock


def test_hashtag_typo_is_gone():
    daily = (ROOT / "content_generator" / "scheduler" / "daily.py").read_text(encoding="utf-8")
    brand = (ROOT / "config" / "brand_config.py").read_text(encoding="utf-8")
    assert "NoCicory" not in daily
    assert "NoCicory" not in brand
    assert "NoChicory" in daily
