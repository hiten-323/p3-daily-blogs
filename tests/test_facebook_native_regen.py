"""Facebook regen must return a native post, not a blog excerpt.

2026-10-22 retry runs 39750328684 and 39745778845 exhausted the ladder because
the facebook_post candidate was a truncated article (introduction, sections,
carousel) and the 8.0 editorial and viral gates scored that article. The gates
stay where they are.
"""
from __future__ import annotations

NATIVE_BODY = (
    "Most houses have one person who measures the spoon and another who says it is too strong. "
    "Purity Beans Purista is freeze-dried pure Robusta with zero chicory, so the jar matches the cup. "
    "Read the label once and the morning argument gets shorter."
)

NATIVE = {
    "angle": "household",
    "hook": "Who makes the coffee in your house, and who complains about it?",
    "body": NATIVE_BODY,
    "community_question": "Who makes the coffee in your house?",
    "cta": "Follow @purepantryprovisions for the next honest cup. https://p3online.in",
    "hashtags": "#PurityBeans #IndianCoffee #MorningCoffee",
}


def _polluted() -> dict:
    return {
        "featured_product": "Purista",
        "needs_regen": True,
        "caption": "Who make",
        "_shape": ["blog_post", "carousel", "carousel_slides", "introduction", "sections", "caption"],
        "blog_post": {
            "introduction": "UNIQUE_BLOG_INTRO_MARKER When you step into a kitchen in the morning.",
            "sections": [
                {"heading": "Four", "content": "create a cafe-style layer of mic"},
            ],
        },
        "carousel_slides": [{"heading": "Slide", "body": ""}],
        "instagram_post": "Read the jar. Purity Beans Purista is 100% pure gourmet Robusta.",
        "facebook_post": (
            "Who makes the coffee in your house? Purity Beans Purista is freeze-dried pure Robusta "
            "with zero chicory. Shop https://p3online.in"
        ),
    }


def test_gates_stay_at_eight():
    from content_generator.core.editorial_engine import get_current_pass_score
    from content_generator.core.fallback_ladder import PASS_FLOOR
    from content_generator.core.viral_gate import PASS_MARK

    assert PASS_FLOOR == 8.0
    assert PASS_MARK == 8.0
    assert get_current_pass_score() == 8.0


def test_scratch_prompt_asks_for_a_native_facebook_post_not_the_blog_shape():
    from content_generator.core.fallback_ladder import scratch_prompt

    prompt = scratch_prompt("facebook_post", _polluted(), "reads like an article excerpt", 8.0, "BRAND")
    keys = prompt.split("Return ONE JSON object", 1)[-1]
    assert "blog_post" not in keys
    assert "sections" not in keys
    assert "carousel" not in keys
    assert "introduction" not in keys
    assert '"hook"' in prompt and '"body"' in prompt and '"community_question"' in prompt
    assert "not a blog" in prompt.lower()
    assert "Reel frames" not in prompt
    assert "UNIQUE_BLOG_INTRO_MARKER" not in prompt
    assert "omit the figure" in prompt
    assert "800 words" not in prompt


def test_rewrite_prompt_does_not_ask_for_an_article_or_feed_the_blog(monkeypatch):
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    seen = {}

    def fake_call(prompt, label, max_tokens=3000):
        seen["prompt"] = prompt
        seen["label"] = label
        seen["max_tokens"] = max_tokens
        return dict(NATIVE)

    monkeypatch.setattr(llm_router, "call", fake_call)
    result = daily._regenerate_piece(
        "facebook_post", _polluted(), "The blog post cuts off mid-sentence.", {"day_number": 294},
        from_scratch=False,
    )
    assert seen["label"] == "regen_facebook_post"
    assert seen["max_tokens"] >= 800
    assert "800 words" not in seen["prompt"]
    assert "Blog: introduction" not in seen["prompt"]
    assert "UNIQUE_BLOG_INTRO_MARKER" not in seen["prompt"]
    assert "not a blog" in seen["prompt"].lower()
    assert result["body"] == NATIVE_BODY
    assert "blog_post" not in result
    assert "sections" not in result


def test_blog_pack_is_rejected_instead_of_stored(monkeypatch):
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    def fake_call(prompt, label, max_tokens=3000):
        return {
            "blog_post": {
                "introduction": "When you step into a kitchen in the morning.",
                "sections": [{"heading": "Four", "content": "create a cafe-style layer of mic"}],
            },
            "carousel_slides": [{"heading": "", "body": ""}],
            "caption": "Who make",
        }

    monkeypatch.setattr(llm_router, "call", fake_call)
    assert daily._regenerate_piece(
        "facebook_post", _polluted(), "article excerpt", {"featured_product": "Purista"},
        from_scratch=True,
    ) is None
    assert daily._apply_regeneration("facebook_post", {"featured_product": "Purista"}, fake_call("", "")) is None


def test_native_rewrite_replaces_a_long_article_body():
    from content_generator.scheduler import daily

    original = {
        "featured_product": "Purista",
        "body": ("This introduction keeps going. " * 80).strip(),
        "blog_post": {"introduction": "old article", "sections": [{"heading": "S", "content": "x"}]},
        "carousel": {"slides": [{"heading": "h", "body": "b"}]},
    }
    improved = dict(NATIVE, blog_post={"introduction": "still an article", "sections": [{"heading": "S"}]})
    # The pack still carries article keys, so it is not a native Facebook post.
    assert daily._apply_regeneration("facebook_post", original, improved) is None

    merged = daily._apply_regeneration("facebook_post", original, dict(NATIVE))
    assert merged["body"] == NATIVE_BODY
    assert merged["hook"] == NATIVE["hook"]
    packed = __import__("json").dumps(merged)
    assert "chicory disguised" not in packed.lower()
    assert "#NoChicory" not in packed
    assert "blog_post" not in merged
    assert "sections" not in merged
    assert "carousel" not in merged
    assert "introduction" not in merged


def test_saved_article_pack_is_not_what_the_scorer_reads():
    from content_generator.core.piece_integrity import ensure_structural_fields

    piece = _polluted()
    ensure_structural_fields(piece, "facebook_post")
    blob = __import__("json").dumps(piece)
    assert "blog_post" not in piece
    assert "sections" not in piece
    assert "carousel_slides" not in piece
    assert "instagram_post" not in piece
    assert "UNIQUE_BLOG_INTRO_MARKER" not in blob
    assert piece.get("caption") in (None, "")
    assert "Who make\"" not in blob
    assert "freeze-dried pure Robusta" in piece.get("body", "")
    assert piece["body"].rstrip().endswith("p3online.in") or piece["body"].rstrip().endswith(".")


def test_brand_fact_gate_is_unchanged_for_native_facebook_copy():
    from content_generator.core.brand_validator import validate_asset

    missing = {
        "hook": "How is the morning going in your kitchen today?",
        "body": "Just a note about the kettle and the weather and the mug on the counter, nothing else at all.",
        "cta": "See the site https://p3online.in",
        "featured_product": "Purista",
    }
    ok, issues = validate_asset("facebook_post", missing)
    assert ok is False
    assert "Missing required brand facts" in issues

    passed, passed_issues = validate_asset("facebook_post", dict(NATIVE, featured_product="Purista"))
    assert passed, passed_issues
