"""Publish bar and obstacle lessons.

The 2026-10-22 morning Facebook post went live after the viral judge scored
7.0 and the fallback ladder logged exhaustion. These tests lock the hold.
"""
from __future__ import annotations

import json

import pytest

from content_generator.core import obstacle_lessons, publish_bar


def _piece(editorial=8.6, viral=8.4, passed=True, honesty=None):
    return {
        "hook": "Why the label matters",
        "body": "Bold is pure coffee with zero chicory.",
        "editorial_score": {"overall": editorial, "verdict": "PASS"},
        "viral_potential": {
            "passed": passed,
            "overall": viral,
            "honesty": list(honesty or []),
            "feedback": "specific",
        },
    }


@pytest.mark.parametrize("label", [
    "facebook_post", "threads_post", "linkedin_post", "yt_short", "carousel", "reel_1",
])
def test_quality_block_rejects_viral_seven(label):
    piece = _piece(editorial=8.6, viral=7.0, passed=False)
    block = publish_bar.quality_block(piece, label)
    assert "7.0/10" in block
    assert publish_bar.reason_code(block) == "llm_viral_readiness_failed"


def test_editorial_below_threshold_fails_before_viral():
    block = publish_bar.quality_block(_piece(editorial=7.4, viral=9.0), "facebook_post")
    assert block.startswith("editorial gate")
    assert publish_bar.reason_code(block) == "editorial_below_8"


def test_missing_viral_score_fails_closed(monkeypatch):
    monkeypatch.delenv("VIRAL_GATE", raising=False)
    piece = _piece()
    piece.pop("viral_potential")
    assert "no LLM viral score" in publish_bar.quality_block(piece, "facebook_post")


def test_viral_gate_off_allows_editorial_only(monkeypatch):
    monkeypatch.setenv("VIRAL_GATE", "0")
    piece = _piece()
    piece.pop("viral_potential")
    assert publish_bar.quality_block(piece, "threads_post") == ""


def test_exhausted_ladder_blocks_even_with_passing_scores():
    piece = _piece()
    publish_bar.hold_exhausted(piece, "viral 7.0")
    assert piece["needs_regen"] is True
    assert piece["publish_blocked"] == "ladder_exhausted"
    assert publish_bar.quality_block(piece, "facebook_post").startswith("FALLBACK LADDER")
    publish_bar.clear_ladder_hold(piece)
    assert publish_bar.quality_block(piece, "facebook_post") == ""
    assert "ladder_exhausted" not in piece


def test_authorize_publish_blocks_viral_seven(monkeypatch):
    from tests.test_universal_pre_publish_gate import _passing_native_gates
    from content_generator.publisher.prepublish_gate import authorize_publish

    _passing_native_gates(monkeypatch)
    piece = _piece(editorial=8.6, viral=7.0, passed=False)
    result = authorize_publish({"facebook_post": piece}, "facebook")
    assert result["allowed"] is False
    assert result["reason"] == "llm_viral_readiness_failed"


def test_facebook_morning_does_not_post_a_rejected_piece(monkeypatch):
    from content_generator.publisher import facebook

    calls = []
    monkeypatch.setattr(facebook, "is_configured", lambda: True)
    monkeypatch.setattr(facebook, "_post_to_page", lambda *a, **k: calls.append(a) or {"success": True})
    monkeypatch.setattr(
        "content_generator.publisher.prepublish_gate.authorize_publish",
        lambda content, platform: {"allowed": False, "reason": "llm_viral_readiness_failed", "asset_key": "facebook_post", "checks": {}},
    )
    result = facebook.post_content({"facebook_post": _piece(viral=7.0, passed=False)}, day=1)
    assert result["success"] is False
    assert "llm_viral_readiness_failed" in result["error"]
    assert calls == []


def test_evening_mirror_requires_the_source_piece(monkeypatch):
    from content_generator.publisher import facebook

    monkeypatch.setattr(facebook, "is_configured", lambda: True)
    monkeypatch.setattr(facebook, "_post_to_page", lambda *a, **k: {"success": True, "post_id": "1"})
    missing = facebook.post_content(
        {"facebook_post": {}}, day=1, message_override="A reel caption about Bold.",
    )
    assert missing["error"] == "prepublish_gate:mirror_source_missing"

    rejected = facebook.post_content(
        {},
        day=1,
        message_override="A reel caption about Bold.",
        mirror_piece=_piece(viral=7.0, passed=False),
        mirror_label="reel_1",
    )
    assert "llm_viral_readiness_failed" in rejected["error"]


def test_campaign_publish_skips_viral_seven(monkeypatch):
    from content_generator.campaigns import trial_diwali_push as push

    calls = []
    monkeypatch.setattr(
        "content_generator.publisher.publishing_ledger.publish_with_ledger",
        lambda *a, **k: calls.append(a) or {"success": True},
    )
    content = {"sales_push": {"active": True, "slug": "bold", "reel": {
        "video_path": "/tmp/reel.mp4",
        "poster_path": "/tmp/poster.jpg",
        "visual_gate": {"passed": True},
        "variety_gate": {"passed": True},
        "caption": "Bold is agglomerated pure coffee.",
        "editorial_score": {"overall": 9.0, "verdict": "PASS"},
        "viral_potential": {"passed": False, "overall": 7.0, "honesty": []},
    }}}
    monkeypatch.setattr(push, "copy_problems", lambda *a, **k: [])
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_jar_provenance",
        lambda path: {"verified": True},
    )
    result = push.publish_for_slot(content, "evening", 1)
    assert result.get("skipped") is True
    assert calls == []


def test_lessons_dedupe_and_cap_prompt(tmp_path, monkeypatch):
    path = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(path))
    obstacle_lessons.record(
        "facebook", "facebook_post", "generation", "llm_viral",
        "viral 7.0 late product reveal", "Purista reveal arrives late",
    )
    obstacle_lessons.record(
        "facebook", "facebook_post", "generation", "llm_viral",
        "viral 7.0 late product reveal", "Purista reveal arrives late",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["lessons"]) == 1
    assert data["lessons"][0]["count"] == 2
    for i in range(12):
        obstacle_lessons.record(
            "facebook", "facebook_post", "generation", "editorial",
            f"distinct miss {i} " + ("word " * 40), "feedback " * 30,
        )
    block = obstacle_lessons.prompt_block("facebook_post")
    assert len(block) <= 900
    assert "late product reveal" in block or "distinct miss" in block


def test_generation_prompts_include_a_recorded_lesson(tmp_path, monkeypatch):
    path = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(path))
    obstacle_lessons.record(
        "facebook", "facebook_post", "generation", "process_match",
        "blog-shaped Facebook post", "name the jar in the first sentences",
        fix="Name the jar early and give a specific follow reason.",
        status="gate_holding",
    )
    from content_generator.prompts.facebook import regeneration_prompt
    from content_generator.prompts.growth_engine.platforms import prompt_block

    regen = regeneration_prompt({"featured_product": "Bold"}, "too generic", 8.0, "BRAND")
    block = prompt_block("facebook_post", "Bold", 1)
    assert "blog-shaped" in regen
    assert "Name the jar early" in regen
    assert "blog-shaped" in block


def test_external_lessons_stay_out_of_prompts(tmp_path, monkeypatch):
    path = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(path))
    obstacle_lessons.record(
        "linkedin", "linkedin_post", "publish", "provider",
        "HTTP 401 expired token", "", status="external",
    )
    assert obstacle_lessons.prompt_block("linkedin_post") == ""


def test_threads_trim_and_facebook_brand_fact():
    from content_generator.core.piece_integrity import ensure_structural_fields

    threads = {"text": ("Check the jar. " * 40).strip()}
    ensure_structural_fields(threads, "threads_post")
    assert len(threads["text"]) <= 480
    assert threads["text"].endswith(".")

    facebook = {
        "hook": "Morning cup, same jar.",
        "body": "I keep this jar by the kettle and still read the label twice.",
        "featured_product": "Bold",
        "cta": "Follow along.",
    }
    ensure_structural_fields(facebook, "facebook_post")
    joined = " ".join(str(facebook.get(k) or "") for k in ("hook", "body", "cta"))
    assert "Purity Beans" in joined
    assert "agglomerated pure coffee" in joined
    assert "not freeze-dried" not in joined.lower()
    assert "p3online.in" in joined


def test_secrets_are_scrubbed(tmp_path, monkeypatch):
    path = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(path))
    obstacle_lessons.record(
        "youtube", "yt_short", "publish", "provider",
        "HTTP 401 Bearer EAAFAKESECRETTOKEN and sk-livekey",
        "api_key=supersecret",
    )
    raw = path.read_text(encoding="utf-8")
    assert "EAAFAKE" not in raw
    assert "sk-livekey" not in raw
    assert "supersecret" not in raw
