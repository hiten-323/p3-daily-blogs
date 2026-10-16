"""Operational alignment regression checks.

These checks prevent the two recurring forms of drift found in the 2026-08-12
re-audit: publishing times documented differently from the live registry, and
the founder policy using a different editorial threshold from the constitution.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_editorial_threshold_is_constitutional() -> None:
    from content_generator.core.brand_guard import EDITORIAL_THRESHOLD
    from content_generator.core.founder_policy import policy
    from content_generator.core.editorial_engine import get_current_pass_score

    assert EDITORIAL_THRESHOLD == 8.0
    assert float(policy().get("minimum_score")) == 8.0
    assert get_current_pass_score() == 8.0


def test_registry_is_0613_0953_2153_ist() -> None:
    from content_generator.core.slot_registry import SLOTS

    assert [(s["id"], s["ist"]) for s in SLOTS] == [
        ("generate", "06:13"),
        ("morning", "09:53"),
        ("evening", "21:53"),
    ]


def test_readme_documents_live_schedule() -> None:
    readme = open("README.md", encoding="utf-8").read()
    assert "09:53 IST  MORNING" in readme
    assert "21:53 IST  EVENING" in readme
    assert "08:00 IST  MORNING" not in readme
    assert "20:00 IST  EVENING" not in readme


def test_architecture_documents_live_schedule_and_threshold() -> None:
    architecture = open("ARCHITECTURE.md", encoding="utf-8").read()
    assert "09:53  MORNING" in architecture
    assert "21:53  EVENING" in architecture
    assert "editorial gate (8.0)" in architecture
    assert "08:00  MORNING" not in architecture
    assert "20:00  EVENING" not in architecture


def test_learning_store_is_tracked() -> None:
    expected = {
        "output/learning/performance_log.json",
        "output/learning/published_posts.json",
        "output/learning/account_metrics.json",
        "output/learning/follower_snapshots.json",
    }
    missing = [path for path in expected if not os.path.exists(path)]
    assert not missing, f"tracked learning state missing: {missing}"
