"""Regression tests for learning evidence and commercial objective ordering."""
from __future__ import annotations

from content_generator.core.learning_engine import _MIN_LEARNING_SAMPLES, is_teachable
from content_generator.core.reward import score


def test_learning_requires_minimum_sample_count() -> None:
    assert _MIN_LEARNING_SAMPLES >= 5


def test_attributed_rupee_does_not_outrank_audience_growth() -> None:
    """A day-level revenue split must not beat real follows.

    GOAL_HIERARCHY.md blocks selling harder at the expense of reach. An order
    is different evidence and still outranks engagement via ORDER_HIERARCHY.
    No revenue prefix can satisfy both "Rs 1 beats 10,000 follows" and
    "100 follows beat Rs 1", so the founder rule is the one that holds.
    """
    engagement = {
        "views": 200_000,
        "follows_gained": 10_000,
        "shares": 2_000,
    }
    attributed = {
        "views": 1_000,
        "follows_gained": 10,
        "revenue": 1,
    }
    assert score(engagement, "followers") > score(attributed, "followers")


def test_orders_beat_noncommercial_engagement() -> None:
    engagement = {"views": 200_000, "follows_gained": 10_000}
    order = {"views": 1_000, "orders": 1}
    assert score(order, "followers") > score(engagement, "followers")


def test_unmeasured_entry_is_not_teachable() -> None:
    assert not is_teachable({"metrics": {}})
    assert not is_teachable({"metrics": {"reach": 100}})
