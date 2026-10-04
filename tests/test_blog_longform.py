"""Long-form blog gates: length, section expansion, schema, and topic rotation."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from content_generator.core.blog_plan import TOPICS, choose_topic
from content_generator.core.blog_quality import article_word_count, assess
from content_generator.core.blog_writer import expand_section, generate_blog_post
from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url


def _long_body() -> str:
    return " ".join(["Purity Beans lists the catalog jar for this section in India."] * 30)


def _llm(counter, *, fail_at: str | None = None):
    def llm(prompt, label="", max_tokens=900):
        counter["n"] += 1
        counter.setdefault("labels", []).append(label)
        if fail_at and str(label) == fail_at:
            raise RuntimeError(f"All LLM providers failed for {label}")
        if "outline" in str(label):
            return {"sections": []}
        if counter["n"] < 4:
            return {"body": "Too short."}
        return {"body": _long_body()}
    return llm


def test_short_sections_are_expanded_and_the_post_passes_gates(tmp_path):
    counter = {"n": 0}
    piece = generate_blog_post(
        4,
        llm_call=_llm(counter),
        output_dir=str(tmp_path),
        on_date="2026-10-04",
        write_files=True,
    )
    assert counter["n"] >= 4
    assert any(label.startswith("blog_section_") for label in counter["labels"])
    assert "blog_outline" in counter["labels"]
    words = article_word_count(piece)
    assert 1000 <= words <= 1500
    assert piece.get("hold_reason") in (None, "")
    assert assess(piece, on_date="2026-10-04", output_dir=str(tmp_path)) == []
    assert 150 <= len(piece["meta_description"]) <= 160
    assert len(piece["title"]) <= 60
    assert 4 <= len(piece["faq"]) <= 6
    assert 2 <= len(piece["internal_links"]) <= 4
    for path in (
        tmp_path / "blog_2026-10-04.json",
        tmp_path / "blog_2026-10-04.md",
        tmp_path / "blog_2026-10-04.html",
        tmp_path / "blog_2026-10-04.llms.txt",
    ):
        assert path.is_file() and path.stat().st_size > 0
    html = (tmp_path / "blog_2026-10-04.html").read_text(encoding="utf-8")
    assert "application/ld+json" in html
    assert "FAQPage" in html
    product = "https://p3online.in/products/purity-beans-bold-instant-coffee"
    assert f"]({product})" in (tmp_path / "blog_2026-10-04.md").read_text(encoding="utf-8")
    assert f'href="{product}"' in html


def test_expand_section_retries_a_short_draft():
    calls = {"n": 0}

    def llm(prompt, label="", max_tokens=900):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"body": "Too short to ship."}
        return {"body": _long_body()}

    text, used, failure = expand_section({"id": "label"}, llm, "Write the section.")
    assert failure is None
    assert used == 3
    assert len(text.split()) >= 120


def test_json_ld_uses_catalog_products_only(tmp_path):
    piece = generate_blog_post(
        1,
        llm_call=_llm({"n": 0}),
        output_dir=str(tmp_path),
        on_date="2026-10-04",
    )
    graph = piece["json_ld"]["@graph"]
    kinds = [node["@type"] for node in graph]
    assert "Article" in kinds
    assert "FAQPage" in kinds
    assert "BreadcrumbList" in kinds
    products = [node for node in graph if node["@type"] == "Product"]
    assert products
    by_url = {product_page_url(product): product for product in SHOPIFY_PRODUCTS.values()}
    for node in products:
        catalog = by_url[node["url"]]
        prices = {int(variant["price"]) for variant in catalog["variants"]}
        assert int(node["offers"]["price"]) in prices
        assert node["offers"]["priceCurrency"] == "INR"


def test_topic_plan_skips_slugs_already_in_output(tmp_path):
    first = TOPICS[0]
    payload = {"blog_post": {"slug": first["slug"], "topic_id": first["id"], "primary_keyword": first["primary"]}}
    (tmp_path / "content_2026-09-01.json").write_text(json.dumps(payload), encoding="utf-8")
    chosen = choose_topic(0, output_dir=str(tmp_path), on_date="2026-10-04")
    assert chosen["id"] != first["id"]
    assert chosen["slug"] != first["slug"]


def test_partial_draft_is_saved_and_a_later_run_resumes(tmp_path):
    def failing(prompt, label="", max_tokens=900):
        if "outline" in str(label):
            return {"sections": []}
        if str(label).endswith("s0"):
            return {"body": _long_body()}
        raise RuntimeError("All LLM providers failed")

    piece = generate_blog_post(
        2,
        llm_call=failing,
        output_dir=str(tmp_path),
        on_date="2026-10-04",
        write_files=False,
    )
    draft_path = tmp_path / "blog_draft_2026-10-04.json"
    assert draft_path.is_file()
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["failed_section_id"] == "s1"
    assert draft["topic_id"] == piece["topic_id"]
    completed = [row for row in draft["sections"] if row.get("complete")]
    assert [row["id"] for row in completed] == ["s0"]
    assert "provider_failure" in piece["hold_reason"]

    resumed = []

    def resume(prompt, label="", max_tokens=900):
        resumed.append(label)
        if "outline" in str(label):
            return {"sections": []}
        return {"body": _long_body()}

    again = generate_blog_post(
        2,
        llm_call=resume,
        output_dir=str(tmp_path),
        on_date="2026-10-04",
        write_files=False,
    )
    assert not any(str(label).endswith("s0") for label in resumed)
    assert any(str(label).endswith("s1") for label in resumed)
    assert again.get("hold_reason") in (None, "")
    assert not draft_path.exists()


def test_failing_section_backs_off_then_uses_the_next_provider(monkeypatch):
    from content_generator.core import blog_writer
    from content_generator.providers import llm_router as router

    sleeps = []
    monkeypatch.setattr(blog_writer.time, "sleep", lambda seconds: sleeps.append(seconds))
    calls = []

    def fail(_prompt, _max_tokens):
        calls.append("nvidia")
        return None, {"status_code": 500, "model": "nim", "error": "down"}

    def ok(_prompt, _max_tokens):
        calls.append("groq")
        return '{"body": "Purity Beans keeps this section on catalog facts."}', {"model": "groq"}

    monkeypatch.setattr(router, "_PROVIDERS", [("nvidia", fail), ("groq", ok)])
    for state in router._STATES.values():
        state.record_success()

    data = blog_writer.call_section_with_fallback("Write the section.", "blog_section_s2")
    assert "Purity Beans" in data["body"]
    assert calls == ["nvidia", "groq"]
    assert sleeps == [2]


def test_provider_failure_keeps_the_draft_and_logs_the_hold(tmp_path, caplog):
    caplog.set_level(logging.ERROR)

    def llm(prompt, label="", max_tokens=900):
        if "outline" in str(label):
            return {"sections": []}
        if str(label).endswith("s0"):
            return {"body": _long_body()}
        raise RuntimeError("All LLM providers failed")

    piece = generate_blog_post(
        2,
        llm_call=llm,
        output_dir=str(tmp_path),
        on_date="2026-10-04",
    )
    assert piece.get("body")
    assert "provider_failure" in str(piece.get("hold_reason"))
    assert "HELD blog_post" in caplog.text
    assert assess(piece, on_date="2026-10-04", output_dir=str(tmp_path))
