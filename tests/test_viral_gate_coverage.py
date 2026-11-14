"""Every publishing route must consult the shared editorial + viral bar.

These lock two real bypasses found on 2026-11-14:

* an autonomous Instagram Story was excluded from the editorial loop, so a
  generated ``stories.story_1`` was never scored and ``post_story`` let it
  publish with no verdict (or only when another path happened to score it);
* publisher modules are the last line of defence and each must reference the
  shared bar rather than carrying its own threshold.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLISHERS = ROOT / "content_generator" / "publisher"


@pytest.mark.parametrize("module", [
    "instagram.py", "facebook.py", "threads.py", "linkedin.py",
    "youtube.py", "shopify_blog.py", "prepublish_gate.py",
])
def test_publisher_consults_the_shared_bar(module):
    source = (PUBLISHERS / module).read_text(encoding="utf-8")
    assert "quality_block" in source or "authorize_publish" in source, (
        f"{module} can publish without the shared editorial + viral bar"
    )


def test_generated_story_is_scored_in_the_editorial_loop(monkeypatch):
    from content_generator.agents import editorial
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(
        editorial, "review_content",
        lambda piece, label="content": {
            "shareability": 9.2, "saveability": 9.2, "emotion_pull": 9.2,
            "hook_strength": 9.2, "brand_clarity": 9.2,
            "overall": 9.2, "verdict": "PASS", "feedback": "holds",
        },
    )
    monkeypatch.setattr(
        "content_generator.core.viral_gate.evaluate",
        lambda label, piece, call=None: {
            "passed": True, "overall": 9.2, "scores": {}, "honesty": [], "pass_mark": 9.0,
        },
    )
    monkeypatch.setattr("content_generator.core.viral_gate.enabled", lambda: True)
    monkeypatch.setattr(daily, "_growth_gate_reason", lambda *a, **k: "")
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "1")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "1")

    content = {
        "day_number": 340,
        "stories": {"story_1": {"headline": "Filter coffee or instant on a weekday?",
                                "subtext": "Pure Coffee. Tap to vote."}},
    }
    daily._do_editorial(content, only={"stories"})

    story = content["stories"]["story_1"]
    assert story["editorial_score"]["overall"] == 9.2
    assert story["viral_potential"]["overall"] == 9.2
    assert story["viral_potential"]["passed"] is True


def test_unscored_generated_story_is_not_published(monkeypatch):
    from content_generator.publisher import instagram

    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    content = {
        "day_number": 341,
        "stories": {"story_1": {"headline": "Filter coffee or instant on a weekday?",
                                "subtext": "Pure Coffee. Tap to vote."}},
    }
    result = instagram.post_story(content, day=341)
    assert result["success"] is False
    assert result["attempted"] is False
    assert result.get("skipped") is True
    assert result["error"].startswith("prepublish_gate:")
    # Missing scores fail closed, exactly like every other generated asset.
    assert "editorial_below_8" in result["error"] or "llm_viral" in result["error"]


def test_retry_approval_fails_closed_when_shared_gate_raises(monkeypatch):
    from content_generator.core import editorial_engine
    from content_generator.publisher import prepublish_gate
    from content_generator.scheduler import retry_unposted

    monkeypatch.setattr(
        editorial_engine, "approved_assets",
        lambda content: {"linkedin_post": {"body": "approved by editorial only"}},
    )
    def broken_gate(*_args, **_kwargs):
        raise RuntimeError("shared viral gate unavailable")
    monkeypatch.setattr(prepublish_gate, "authorize_publish", broken_gate)
    assert retry_unposted._approved({}) == {}


def test_generated_story_below_the_viral_bar_is_not_published(monkeypatch):
    from content_generator.publisher import instagram

    monkeypatch.setattr(instagram, "is_configured", lambda: True)
    monkeypatch.delenv("VIRAL_GATE", raising=False)
    content = {
        "day_number": 342,
        "stories": {"story_1": {
            "headline": "Filter coffee or instant on a weekday?",
            "subtext": "Tap to vote.",
            "editorial_score": {"overall": 9.2, "verdict": "PASS"},
            "viral_potential": {"passed": True, "overall": 8.9, "honesty": []},
        }},
    }
    result = instagram.post_story(content, day=342)
    assert result["success"] is False
    assert result["error"] == "prepublish_gate:llm_viral_readiness_failed"
