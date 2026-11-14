"""Measured post-publish performance drives durable hook retirement.

Retirement is deliberately conservative: it needs at least five measurable,
same-objective observations, and only the strictly losing bottom slice. A
missing metric is never a loser, and a single post is never a rule.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from content_generator.core import hook_retirement


def _entry(hook: str, views: int, shares: int, **extra) -> dict:
    from content_generator.core.reward import get_active_kpi
    row = {
        "asset_id": hook, "hook": hook, "platform": "instagram",
        "format": "story", "kpi": get_active_kpi(),
        "metrics": {"views": views, "shares": shares},
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def _isolated_learning_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARNING_DIR", str(tmp_path / "learning"))
    return tmp_path / "learning"


def _state_path() -> pathlib.Path:
    return pathlib.Path(hook_retirement._path())


def test_missing_metrics_never_retire():
    entries = [_entry(f"hook-{i}", 0, 0) for i in range(10)]
    for entry in entries:
        entry["metrics"] = {}
    result = hook_retirement.retire_from_learning(entries)
    assert result["added_hooks"] == []
    assert result["added_strategies"] == []
    assert not _state_path().exists()


def test_four_observations_are_not_enough():
    entries = [_entry(f"hook-{i}", 1000 - i * 10, 20 - i) for i in range(4)]
    result = hook_retirement.retire_from_learning(entries)
    assert result["losers"] == 0
    assert hook_retirement.retired_hooks() == set()


def test_different_platform_and_format_samples_are_not_pooled():
    entries = []
    for i in range(3):
        entries.append(_entry(f"story-{i}", 1000 - i * 10, 20 - i,
                              platform="instagram", format="story"))
        entries.append(_entry(f"linkedin-{i}", 1000 - i * 10, 20 - i,
                              platform="linkedin", format="linkedin_post"))
    result = hook_retirement.retire_from_learning(entries)
    assert result["losers"] == 0
    assert hook_retirement.retired_hooks() == set()


def test_bottom_of_measured_posts_is_retired_and_persisted():
    # Ten measurable posts: the last two are clearly the losers.
    entries = [_entry(f"hook-{i}", 1000 - i * 10, 20 - i,
                      hook_strategy="question", attention_mechanism="curiosity")
               for i in range(10)]
    result = hook_retirement.retire_from_learning(entries, now="2026-11-14T10:00:00")
    assert result["losers"] >= 1
    retired = hook_retirement.retired_hooks()
    assert hook_retirement.normalize("hook-9") in retired
    assert hook_retirement.normalize("hook-0") not in retired

    state = json.loads(_state_path().read_text(encoding="utf-8"))
    assert hook_retirement.normalize("hook-9") in state["hooks"]
    assert state["updated_at"] == "2026-11-14T10:00:00"
    record = state["hooks"][hook_retirement.normalize("hook-9")]
    assert record["source_asset"] == "hook-9"
    assert record["retired_at"] == "2026-11-14T10:00:00"
    assert hook_retirement.normalize("question") not in hook_retirement.retired_strategies("instagram", "story")
    assert hook_retirement.normalize("curiosity") not in hook_retirement.retired_strategies("instagram", "story")


def test_strategy_retirement_requires_repeated_same_surface_evidence():
    entries = []
    for i in range(5):
        entries.append(_entry(f"weak-{i}", 100 + i, 1 + i,
                              hook_strategy="question", attention_mechanism="curiosity"))
    for i in range(5):
        entries.append(_entry(f"strong-{i}", 1000 + i * 100, 20 + i,
                              hook_strategy="story", attention_mechanism="surprise"))
    hook_retirement.retire_from_learning(entries)
    assert hook_retirement.normalize("question") in hook_retirement.retired_strategies("instagram", "story")
    assert hook_retirement.normalize("curiosity") in hook_retirement.retired_strategies("instagram", "story")
    assert hook_retirement.normalize("question") not in hook_retirement.retired_strategies("linkedin", "linkedin_post")


def test_other_objective_evidence_is_not_retired_here():
    from content_generator.core.reward import WEIGHT_PROFILES, get_active_kpi

    other = next(k for k in WEIGHT_PROFILES if k != get_active_kpi())
    entries = [_entry(f"hook-{i}", 1000 - i * 10, 20 - i, kpi=other)
               for i in range(10)]
    result = hook_retirement.retire_from_learning(entries)
    assert result["losers"] == 0
    assert hook_retirement.retired_hooks() == set()


def test_retirement_is_idempotent():
    entries = [_entry(f"hook-{i}", 1000 - i * 10, 20 - i) for i in range(10)]
    first = hook_retirement.retire_from_learning(entries, now="2026-11-14T10:00:00")
    second = hook_retirement.retire_from_learning(entries, now="2026-11-14T10:05:00")
    assert first["added_hooks"]
    assert second["added_hooks"] == []
    assert second["added_strategies"] == []


def test_retired_hook_and_strategy_filter_the_template_pool():
    from content_generator.core import viral_gate

    templates = list(viral_gate.HOOK_TEMPLATES["story"])
    hook_retirement.retire_from_learning(
        [_entry(templates[0], 100, 1)] + [_entry(f"hook-{i}", 1000 - i * 10, 20 - i)
                                          for i in range(9)]
    )
    assert templates[0] not in hook_retirement.active_templates(templates)
    assert hook_retirement.active_templates(templates)

    state = json.loads(_state_path().read_text(encoding="utf-8"))
    state["strategies"]["instagram::story::follow::hook_strategy::question"] = {
        "score": 0.1, "source_asset": "x", "retired_at": "2026-11-14T10:00:00",
        "platform": "instagram", "format": "story", "kpi": "follow",
        "strategy": "question", "field": "hook_strategy",
    }
    _state_path().write_text(json.dumps(state), encoding="utf-8")
    scoped_template = "Which coffee ritual is yours?"
    assert "question" in hook_retirement.template_tags(scoped_template)
    assert scoped_template not in hook_retirement.active_templates([scoped_template], "instagram", "story")
    assert scoped_template in hook_retirement.active_templates([scoped_template], "linkedin", "linkedin_post")


def test_corrupt_retirement_store_fails_closed_for_template_selection():
    from content_generator.core import viral_gate

    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text("{not-json", encoding="utf-8")
    templates = list(viral_gate.HOOK_TEMPLATES["story"])
    with pytest.raises(ValueError, match="corrupt retirement state"):
        hook_retirement.active_templates(templates, "instagram", "story")
    assert "original hook pattern" in viral_gate.choose_template("stories", 0)
    assert "no non-retired templates" in viral_gate.hook_block("stories")


def test_fatigue_block_carries_permanent_retirements():
    from content_generator.analytics import hook_selector

    hook_retirement.retire_from_learning(
        [_entry(f"hook-{i}", 1000 - i * 10, 20 - i) for i in range(10)]
    )
    block = hook_selector.get_fatigue_block()
    assert "PERMANENTLY RETIRED BY MEASURED PERFORMANCE" in block
    assert "hook-9" in block


def test_all_retired_templates_are_never_offered_again(monkeypatch):
    from content_generator.core import viral_gate

    monkeypatch.setattr(hook_retirement, "active_templates", lambda templates: [])
    chosen = viral_gate.choose_template("reel_1", 0)
    block = viral_gate.hook_block("reel_1")
    assert "original hook pattern" in chosen
    assert "no non-retired templates" in block
    assert all(template not in chosen for template in viral_gate.HOOK_TEMPLATES["reel"])
    assert all(template not in block for template in viral_gate.HOOK_TEMPLATES["reel"])
