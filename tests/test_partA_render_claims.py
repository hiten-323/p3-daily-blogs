"""Part A: on-image claim guard, Threads polling, blog dedupe, mandatory slots."""
import ast
import pathlib
import re
import urllib.error

import pytest

from content_generator.creative import render_claims as rc

CREATIVE = pathlib.Path(__file__).resolve().parents[1] / "content_generator" / "creative"


def test_hundred_percent_never_survives():
    for sku in ("pure", "ultra", "unknown"):
        out = rc.guard("100% PURE COFFEE \u2022 ZERO CHICORY", sku)
        assert "100" not in out


def test_ultra_never_pure_or_zero_chicory():
    for t in ("PURITY STORY \u2022 ZERO CHICORY", "PURE COFFEE | p3online.in", "no chicory", "chicory-free"):
        assert rc.guard(t, "ultra") == rc.ULTRA_STRIP
    assert rc.strip_for("ultra_blend") == "Coffee + chicory blend"
    assert "PURE" not in rc.footer_for("ultra blend").upper().replace("PURITY", "")


def test_pure_sku_keeps_honest_strip():
    assert rc.strip_for("bold") == "Pure coffee \u2022 Zero chicory"
    assert rc.guard("Pure coffee \u2022 Zero chicory", "pure") == "Pure coffee \u2022 Zero chicory"


def test_no_template_literal_says_100_percent():
    bad = []
    for f in CREATIVE.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.search(r"\b100\s*%\s*(pure|coffee|arabica|robusta)", node.value, re.I):
                    bad.append((f.name, node.value[:60]))
    assert not bad, bad


def _capture(monkeypatch):
    from PIL import ImageDraw
    seen = []
    orig = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *a, **k):
        seen.append((str(text), rc.current()))
        return orig(self, xy, text, *a, **k)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    return seen


@pytest.mark.parametrize("product,sku", [("ultra_blend", "ultra"), ("bold", "pure"), ("purica", "pure")])
def test_rendered_post_text_is_claim_safe(monkeypatch, tmp_path, product, sku):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    seen = _capture(monkeypatch)
    from content_generator.creative.real_jar_composer import compose_post_image
    compose_post_image(headline="100% PURE COFFEE ZERO CHICORY", body="Pure Coffee. Zero Chicory.",
                       day=3, idx=0, product=product, label="t")
    assert seen
    for t, active in seen:
        assert active is not None, t
        assert not rc.violations(t, active), t


def test_rendered_carousel_text_is_claim_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    seen = _capture(monkeypatch)
    from content_generator.creative.real_jar_composer import compose_carousel_slide
    for i in range(3):
        compose_carousel_slide(heading="The 100% pure standard", body="zero chicory always", day=5, idx=i,
                               total_slides=3, product="ultra_blend", label=f"c{i}")
    for t, active in seen:
        assert active is not None, t
        assert not rc.violations(t, active), t


def test_threads_waits_for_finished_then_retries_media_not_found():
    from content_generator.publisher import threads
    statuses = iter(["IN_PROGRESS", "FINISHED", "FINISHED"])
    calls = {"n": 0}

    def post(url, params):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(url, 400, "Media Not Found", {}, None)
        return {"id": "42"}
    pid = threads.publish_thread_container("u", "t", "c", sleep=lambda s: None,
                                           status_fn=lambda c, t: next(statuses), post_fn=post)
    assert pid == "42" and calls["n"] == 2


def test_blog_dedupes_headings_and_disclosure():
    from content_generator.core.blog_writer import dedupe_sections
    d = "Ultra Blend is 70% coffee and 30% chicory."
    secs = [{"heading": "Why?", "body": f"A. {d}", "h3": "Tip", "h3_body": "same"},
            {"heading": "Why?", "body": "dup", "h3": "Tip", "h3_body": "same"},
            {"heading": "How?", "body": f"B. {d}", "h3": "Tip", "h3_body": "same"}]
    out = dedupe_sections(secs)
    assert [s["heading"] for s in out] == ["Why?", "How?"]
    assert sum(s["body"].count("70% coffee") for s in out) == 1
    assert out[1]["h3"] == ""


def test_blog_sections_use_router(monkeypatch):
    from content_generator.core import blog_writer
    from content_generator.providers import llm_router
    got = {}
    monkeypatch.setattr(llm_router, "call", lambda p, label, max_tokens: got.setdefault("label", label) and {"body": "x"})
    blog_writer.call_section_with_fallback("p", "blog_section_s1")
    assert got["label"].startswith("blog")


def test_mandatory_slots_first_and_marked_fresh():
    from content_generator.scheduler import retry_unposted as ru
    assert ru.prioritise(["linkedin", "ig_reel", "blog", "ig_feed"])[:2] == ["ig_reel", "ig_feed"]
    content = {"carousel": {"slides": []}, "reels": [{"hook": "a"}, {"hook": "b"}]}
    ru.mark_fresh(content, ["carousel", "reel_2"])
    assert content["carousel"]["needs_regen"] and content["reels"][1]["needs_regen"]
    assert content["mandatory_regen_rounds"]["reel_2"] == 1
