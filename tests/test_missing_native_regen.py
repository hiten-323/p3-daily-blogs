"""Targeted regen must create facebook_post, threads_post, and yt_short when the pack omitted them.

Emergency evergreen packs never carried those keys. mark_fresh incremented a
counter and _do_editorial skipped the empty slot, so the 8.0 gate never saw a
piece. These tests keep that gate where it is.
"""
from __future__ import annotations

import json


def _score_reject():
    return {
        "overall": 7.2,
        "verdict": "REJECT",
        "feedback": "sharper hook",
        "shareability": 7.2,
        "saveability": 7.2,
        "emotion_pull": 7.2,
        "hook_strength": 7.2,
        "brand_clarity": 7.2,
    }


def _refuse_llm(*_args, **_kwargs):
    raise AssertionError("unexpected LLM call")


def _install_editorial_fakes(monkeypatch, regen):
    from content_generator.agents import editorial
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(llm_router, "call", _refuse_llm)
    monkeypatch.setattr(editorial, "review_content", lambda content, label="content": _score_reject())
    monkeypatch.setattr(daily, "_regenerate_piece", regen)
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "0")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "1")
    monkeypatch.delenv("BLOG_ENABLED", raising=False)


def _regen(label, piece, feedback, content, from_scratch=False):
    return {
        "type": label,
        "hook": f"hook-{label}",
        "body": f"body for {label} about the morning jar at home",
        "text": f"text for {label} about the morning jar",
        "script": "A short voiceover that names the jar and nothing medical or urgent.",
        "cta": "Follow for the next cup",
    }


def test_gates_stay_at_eight():
    from content_generator.core.editorial_engine import get_current_pass_score
    from content_generator.core.fallback_ladder import PASS_FLOOR
    from content_generator.core.viral_gate import PASS_MARK

    assert PASS_FLOOR == 8.0
    assert PASS_MARK == 8.0
    assert get_current_pass_score() == 8.0


def test_mark_fresh_seeds_missing_natives_and_editorial_fills_them(monkeypatch):
    from content_generator.scheduler import daily, retry_unposted as ru

    calls = []

    def regen(label, piece, feedback, content, from_scratch=False):
        calls.append((label, from_scratch))
        return _regen(label, piece, feedback, content, from_scratch)

    _install_editorial_fakes(monkeypatch, regen)
    content = {
        "day_number": 249,
        "_source": "emergency_fallback_evergreen",
        "_recycled": True,
        "featured_product": "Ultra Blend",
        "carousel": {"hook": "kept"},
        "reels": [{"hook": "reel one"}],
    }
    marked = ru.mark_fresh(content, ["facebook_post", "threads_post", "yt_short", "reel_2"])
    assert marked == ["facebook_post", "threads_post", "yt_short", "reel_2"]
    for label in ("facebook_post", "threads_post", "yt_short"):
        assert content[label]["needs_regen"] is True
        assert content[label]["type"] == label
        assert content[label]["featured_product"] == "Ultra Blend"
        assert "hook" not in content[label]
    assert content["reels"][1]["type"] == "reel_2"
    assert content["reels"][0]["hook"] == "reel one"
    assert content["mandatory_regen_rounds"]["facebook_post"] == 1

    daily._do_editorial(content, only={"facebook_post", "threads_post", "yt_short"})

    fb = content["facebook_post"]
    assert isinstance(fb, dict) and fb.get("hook") == "hook-facebook_post"
    assert "body" in fb
    assert content["threads_post"].get("hook") == "hook-threads_post"
    assert content["yt_short"].get("hook") == "hook-yt_short"
    assert ("facebook_post", True) in calls
    assert content["carousel"]["hook"] == "kept"
    assert "blog_post" not in content


def test_editorial_only_creates_missing_facebook_without_mark_fresh(monkeypatch):
    from content_generator.scheduler import daily

    _install_editorial_fakes(monkeypatch, _regen)
    content = {"day_number": 249, "featured_product": "Bold", "_source": "emergency_fallback_evergreen"}
    daily._do_editorial(content, only={"facebook_post"})
    assert isinstance(content.get("facebook_post"), dict) and content["facebook_post"]
    assert content["facebook_post"]["hook"] == "hook-facebook_post"
    assert "threads_post" not in content
    assert "yt_short" not in content


def test_untargeted_editorial_does_not_invent_missing_natives(monkeypatch):
    from content_generator.scheduler import daily

    _install_editorial_fakes(monkeypatch, _regen)
    content = {"day_number": 249, "featured_product": "Bold", "linkedin_post": {"hook": "h", "body": "b"}}
    daily._do_editorial(content)
    assert "facebook_post" not in content
    assert "threads_post" not in content
    assert "yt_short" not in content


def test_targeted_editorial_does_not_create_blog(monkeypatch):
    from content_generator.scheduler import daily

    _install_editorial_fakes(monkeypatch, _regen)
    monkeypatch.setenv("BLOG_ENABLED", "true")
    content = {"day_number": 249, "featured_product": "Bold"}
    daily._do_editorial(content, only={"blog_post"})
    assert not content.get("blog_post")


def test_platform_builder_used_when_regen_returns_nothing(monkeypatch):
    from content_generator.agents import editorial
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(editorial, "review_content", lambda content, label="content": _score_reject())
    monkeypatch.setattr(daily, "_regenerate_piece", lambda *a, **k: None)
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "0")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "1")
    seen = {}

    def fake_call(prompt, label, max_tokens=3000):
        seen["label"] = label
        seen["prompt"] = prompt
        return {"hook": "Who makes the coffee in your house?", "body": "A household question about the jar."}

    monkeypatch.setattr(llm_router, "call", fake_call)
    content = {"day_number": 4, "featured_product": "Bold"}
    daily._do_editorial(content, only={"facebook_post"})
    piece = content["facebook_post"]
    assert piece.get("hook") == "Who makes the coffee in your house?"
    assert seen["label"] == "facebook_post"
    assert "Facebook" in seen["prompt"]


def test_evergreen_and_save_seed_stubs_without_copy(tmp_path):
    from content_generator.pipeline.generator import save_content
    from content_generator.scheduler.fallback import _from_evergreen

    content = _from_evergreen(249)
    for label in ("facebook_post", "threads_post", "yt_short"):
        piece = content[label]
        assert piece["needs_regen"] is True
        assert piece["type"] == label
        assert not any(piece.get(k) for k in ("hook", "body", "text", "script", "caption"))

    path = save_content(
        {"day_number": 249, "_source": "emergency_fallback_evergreen", "featured_product": "Purista", "reels": []},
        output_dir=str(tmp_path),
    )
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["facebook_post"]["needs_regen"] is True
    assert data["threads_post"]["type"] == "threads_post"
    assert data["yt_short"]["featured_product"] == "Purista"
    assert "hook" not in data["facebook_post"]
