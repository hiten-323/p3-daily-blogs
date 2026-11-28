"""Tests for PR C: Daily feedback adaptation block and prompt injection."""
import json
import pytest
from pathlib import Path

from content_generator.core import daily_feedback


def test_daily_feedback_with_measured_metrics(monkeypatch, tmp_path):
    """Seed yesterday's LinkedIn post (hook A, 40 reactions) and day-before (hook B, 2 reactions).
    Assert built feedback block contains hook A as top performer, hook B as bottom, and metric counts.
    """
    tracker_file = tmp_path / "published_posts.json"
    monkeypatch.setattr(daily_feedback, "_POSTS_PATH", tracker_file)

    sample_posts = [
        {
            "media_id": "urn:li:share:111",
            "platform": "linkedin",
            "published_at": "2026-11-27T10:00:00",
            "hook": "Hook A: The hidden chicory scandal in office pantries",
            "angle": "pantry_economics",
            "measurement_snapshots": [
                {
                    "window": "24h",
                    "metrics": {"likes": 35, "comments": 5},
                }
            ],
        },
        {
            "media_id": "urn:li:share:222",
            "platform": "linkedin",
            "published_at": "2026-11-26T10:00:00",
            "hook": "Hook B: Why coffee cups matter",
            "angle": "cup_size",
            "measurement_snapshots": [
                {
                    "window": "24h",
                    "metrics": {"likes": 2, "comments": 0},
                }
            ],
        },
    ]
    tracker_file.write_text(json.dumps(sample_posts), encoding="utf-8")

    block = daily_feedback.build_feedback_block("linkedin", today="2026-11-28")
    assert "TOP PERFORMER: \"Hook A: The hidden chicory scandal" in block
    assert "BOTTOM PERFORMER: \"Hook B: Why coffee cups matter\"" in block
    assert "'likes': 35" in block or "35" in block
    assert len(block) <= 900


def test_daily_feedback_with_zero_metrics_reports_no_reliable_metrics(monkeypatch, tmp_path):
    """When all metrics are zero or missing, report 'no reliable metrics yet' and do not list winners."""
    tracker_file = tmp_path / "published_posts.json"
    monkeypatch.setattr(daily_feedback, "_POSTS_PATH", tracker_file)

    sample_posts = [
        {
            "media_id": "urn:li:share:333",
            "platform": "linkedin",
            "published_at": "2026-11-27T10:00:00",
            "hook": "Hook C: Zero signal post",
            "angle": "testing",
            "measurement_snapshots": [
                {
                    "window": "24h",
                    "metrics": {"likes": 0, "comments": 0},
                }
            ],
        }
    ]
    tracker_file.write_text(json.dumps(sample_posts), encoding="utf-8")

    block = daily_feedback.build_feedback_block("linkedin", today="2026-11-28")
    assert "no reliable metrics yet — use gate feedback below" in block
    assert "TOP PERFORMER" not in block
    assert len(block) <= 900


def test_daily_feedback_digest_and_do_not_repeat(monkeypatch, tmp_path):
    """Assert recurring weakest dimensions from lessons and recent hooks are included."""
    tracker_file = tmp_path / "published_posts.json"
    lessons_file = tmp_path / "obstacle_lessons.json"
    monkeypatch.setattr(daily_feedback, "_POSTS_PATH", tracker_file)
    monkeypatch.setattr(daily_feedback, "_LESSONS_PATH", lessons_file)

    lessons_data = {
        "version": 1,
        "lessons": [
            {
                "platform": "linkedin",
                "code": "generic_hook",
                "count": 9,
                "fix": "Open with specific office pantry dilemma",
            },
            {
                "platform": "linkedin",
                "code": "relatability",
                "count": 6,
            },
            {
                "platform": "linkedin",
                "code": "follow_cta",
                "count": 4,
            },
        ],
    }
    tracker_file.write_text(json.dumps([]), encoding="utf-8")
    lessons_file.write_text(json.dumps(lessons_data), encoding="utf-8")

    block = daily_feedback.build_feedback_block("linkedin", today="2026-11-28")
    assert "GATE FEEDBACK DIGEST: top recurring weaknesses: generic_hook 9x, relatability 6x, follow_cta 4x" in block
    assert "Open with specific office pantry dilemma" in block
    assert len(block) <= 900
