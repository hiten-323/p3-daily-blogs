"""Process mentions have to match the featured or linked jar."""
from __future__ import annotations


def _reasons(text: str, featured: str | None = None) -> list[str]:
    from content_generator.core.product_truth import product_truth_findings

    return [item["reason"] for item in product_truth_findings(text, featured=featured)]


def test_bold_is_agglomerated_and_not_freeze_dried():
    assert _reasons("Bold is agglomerated pure coffee.") == []
    assert any("not freeze-dried" in reason for reason in _reasons("Bold is freeze-dried pure coffee."))
    assert any("not freeze-dried" in reason for reason in _reasons("This freeze-dried Bold jar dissolves fast."))


def test_freeze_dried_jars_and_ultra_blend_process_silence():
    assert _reasons("Purica is freeze-dried pure Arabica.") == []
    assert _reasons("Purista is freeze-dried pure Robusta.") == []
    assert _reasons("Gourmet Duo Mini is freeze-dried pure coffee.") == []
    assert any("no process" in reason for reason in _reasons("Ultra Blend is agglomerated."))
    assert any("no process" in reason for reason in _reasons("Ultra Blend is freeze-dried."))
    assert _reasons("Ultra Blend is 70% coffee and 30% chicory.") == []
    assert _reasons("Premium Agglomerate is pure Arabica.") == []
    assert _reasons("Prima is agglomerated, not freeze-dried.") == []


def test_granules_as_process_are_not_the_word_granules():
    assert _reasons("Look at the granules: crystals or powder.") == []
    assert _reasons("Moisture ruins granules if the spoon is wet.") == []
    assert _reasons("Purica uses a granule process.") == []
    assert any("granule" in reason for reason in _reasons("Bold is made into granules."))


def test_comparison_may_link_bold_without_calling_it_freeze_dried():
    comparison = (
        "Freeze-drying keeps aroma in the cold step. "
        "Agglomeration is the other method. "
        "Bold is agglomerated pure coffee."
    )
    assert _reasons(comparison, featured="Bold") == []
    mismatch = (
        "Freeze-drying keeps aroma in the cold step. "
        "Bold is the jar this post is about."
    )
    assert any("Bold" in reason for reason in _reasons(mismatch, featured="Bold"))
    called = "Bold is freeze-dried, and agglomeration is the other word for it."
    assert any("not freeze-dried" in reason for reason in _reasons(called, featured="Bold"))


def test_process_education_link_follows_the_product_url():
    bold_url = "https://p3online.in/products/purity-beans-bold-instant-coffee"
    purica_url = "https://p3online.in/products/purity-beans-purica-gourmet-instant-coffee-granules"
    essay = "Freeze-drying works cold, so more aroma survives."
    assert any("not freeze-dried" in reason for reason in _reasons(f"{essay} {bold_url}"))
    assert _reasons(f"{essay} Purica is freeze-dried pure Arabica. {purica_url}") == []
    assert _reasons(
        "Purica is freeze-dried pure Arabica.",
        featured="Purica",
    ) == []
    assert any("Bold" in reason for reason in _reasons(
        "Purica is freeze-dried pure Arabica.",
        featured="Bold",
    ))


def test_rewrite_fixes_a_direct_mislable_and_leaves_the_gate_clear():
    from content_generator.core.process_match import align_process_piece, rewrite_process_text

    rewritten = rewrite_process_text("Bold is freeze-dried pure coffee.")
    assert rewritten == "Bold is agglomerated pure coffee."
    assert _reasons(rewritten) == []
    ultra = rewrite_process_text("Ultra Blend is agglomerated.")
    assert "70% coffee" in ultra
    assert _reasons(ultra) == []

    piece = {
        "product": "Purica",
        "description": "Freeze-dried and agglomerated variants.",
        "tags": ["freeze dried coffee", "agglomerated coffee"],
    }
    align_process_piece(piece, "Purica")
    assert "agglomerat" not in piece["description"].lower()
    assert "freeze-dried" in piece["description"].lower()
    assert all("agglomerat" not in tag.lower() for tag in piece["tags"])
    assert _reasons(piece["description"], featured="Purica") == []

    comparison = {
        "caption": "Purica is freeze-dried pure Arabica. Bold is agglomerated pure coffee.",
    }
    align_process_piece(comparison, "Purica")
    assert "Bold is agglomerated" in comparison["caption"]
    assert _reasons(comparison["caption"], featured="Purica") == []


def test_existing_gates_still_fail_closed():
    assert _reasons("Ultra Blend is zero chicory.")
    assert _reasons("Prima is freeze-dried pure Robusta.")
    assert _reasons("Bold is a Robusta coffee.")
    assert _reasons("Bold is 100% coffee.")


def test_catalog_and_prompts_state_the_process_match():
    from content_generator.core.process_match import PROCESS_MATCH_RULE
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, format_catalog_for_prompt
    from content_generator.prompts.brand import brand_block
    from content_generator.prompts.growth_engine.platforms import generation_preface, prompt_block
    from content_generator.prompts.threads import build as threads_build

    assert SHOPIFY_PRODUCTS["bold"]["process"] == "Agglomerated instant coffee"
    assert "Freeze" not in SHOPIFY_PRODUCTS["bold"]["process"]
    assert SHOPIFY_PRODUCTS["ultra_blend"]["process"] == "Do not name a process"
    assert "agglomerat" not in SHOPIFY_PRODUCTS["ultra_blend"]["process"].lower()
    assert SHOPIFY_PRODUCTS["purica"]["process"] == "Freeze-dried granules"
    assert SHOPIFY_PRODUCTS["purista"]["process"] == "Freeze-dried granules"
    catalog = format_catalog_for_prompt()
    brand = brand_block()
    preface = generation_preface("Bold", 286)
    threads = threads_build(("LABEL", "read the jar"), day=286)
    carousel = prompt_block("carousel", "Bold", 286)
    assert PROCESS_MATCH_RULE in catalog
    assert PROCESS_MATCH_RULE in preface
    assert PROCESS_MATCH_RULE in carousel
    assert "Bold is agglomerated" in brand
    assert "not freeze-dried" in brand
    assert "Do not name a process for Ultra Blend" in brand
    assert "must not call Bold freeze-dried" in threads or "not freeze-dried" in threads
    assert "campaign push" in PROCESS_MATCH_RULE
