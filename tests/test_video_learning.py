"""Test video learning and cross-platform viral growth engine."""
import os
import json
import pytest

from content_generator.core import video_learning as vl
from content_generator.core import growth_director as gd
from content_generator.prompts import growth_reel as gr_prompt
from content_generator.prompts import reels as reels_prompt
from content_generator.prompts import yt_short as yt_prompt


def test_video_outcomes_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "_DEFAULT_OUTPUT_DIR", str(tmp_path))
    
    # Create mock content files
    f1 = tmp_path / "content_2026-11-01.json"
    f1.write_text(json.dumps({
        "date": "2026-11-01",
        "growth_reel": {"hook": "The freeze-dried coffee test you need to see.", "editorial_score": {"overall": 9.0}},
        "reel_1": {"hook": "Why your cup tastes like chicory.", "editorial_score": {"overall": 8.7}},
        "yt_short": {"title": "Burnt beans vs pure beans.", "editorial_score": {"overall": 8.8}},
    }), encoding="utf-8")
    
    f2 = tmp_path / "content_2026-11-02.json"
    f2.write_text(json.dumps({
        "date": "2026-11-02",
        "growth_reel": {"hook": "Most people calculate the cost of a jar wrong.", "editorial_score": {"overall": 6.5}},
        "reel_1": {"hook": "Coffee is pure when the label says so.", "editorial_score": {"overall": 8.9}},
        "yt_short": {"title": "Watch the crystals melt.", "editorial_score": {"overall": 7.5}},
    }), encoding="utf-8")

    outcomes = vl.get_recent_video_outcomes(max_days=7)
    assert len(outcomes) == 2
    assert outcomes[0]["growth_reel"]["score"] == 9.0
    assert outcomes[1]["growth_reel"]["score"] == 6.5


def test_build_video_learning_directive_categorizes_winners_and_losers(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "_DEFAULT_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(vl, "_LEARNING_DIR", str(tmp_path / "learning"))
    (tmp_path / "learning").mkdir(parents=True, exist_ok=True)
    
    f1 = tmp_path / "content_2026-11-01.json"
    f1.write_text(json.dumps({
        "date": "2026-11-01",
        "growth_reel": {"hook": "The freeze-dried coffee test you need to see.", "editorial_score": {"overall": 9.0}},
        "reel_1": {"hook": "Why your cup tastes like chicory.", "editorial_score": {"overall": 8.7}},
        "yt_short": {"title": "Burnt beans vs pure beans.", "editorial_score": {"overall": 8.8}},
    }), encoding="utf-8")
    
    f2 = tmp_path / "content_2026-11-02.json"
    f2.write_text(json.dumps({
        "date": "2026-11-02",
        "growth_reel": {"hook": "Most people calculate the cost of a jar wrong.", "editorial_score": {"overall": 6.5}},
        "reel_1": {"hook": "Coffee is pure when the label says so.", "editorial_score": {"overall": 8.9}},
        "yt_short": {"title": "Watch the crystals melt.", "editorial_score": {"overall": 7.5}},
    }), encoding="utf-8")

    directive = vl.build_video_learning_directive(platform="all")
    assert "HIGH-RETENTION PROVEN HOOKS" in directive
    assert "The freeze-dried coffee test" in directive
    assert "FAILED / REJECTED HOOK PATTERNS" in directive
    assert "calculate the cost" in directive
    assert "INSTAGRAM" in directive
    assert "FACEBOOK" in directive
    assert "YOUTUBE SHORTS" in directive
    assert "single-origin" not in directive
    assert "sludge" not in directive


def test_real_platform_metrics_integration(tmp_path, monkeypatch):
    learn_dir = tmp_path / "learning"
    learn_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vl, "_LEARNING_DIR", str(learn_dir))
    monkeypatch.setattr(vl, "_DEFAULT_OUTPUT_DIR", str(tmp_path))
    
    # Write mock follower_snapshots.json
    (learn_dir / "follower_snapshots.json").write_text(json.dumps([
        {"date": "2026-10-27T00:00:00", "count": 100},
        {"date": "2026-11-03T00:00:00", "count": 125},
    ]), encoding="utf-8")
    
    # Write mock performance_log.json
    (learn_dir / "performance_log.json").write_text(json.dumps([
        {
            "hook": "Real coffee has zero chicory.",
            "platform": "instagram",
            "metrics": {"views": 1500, "shares": 30, "comments": 15}
        }
    ]), encoding="utf-8")
    
    metrics = vl.get_real_platform_metrics()
    assert metrics["follower_count"] == 125
    assert metrics["follower_delta_7d"] == 25
    assert len(metrics["top_posts_by_reach"]) == 1
    assert metrics["top_posts_by_reach"][0]["views"] == 1500

    directive = vl.build_video_learning_directive(platform="instagram")
    assert "LIVE FOLLOWER DATA: 125 followers" in directive
    assert "Real coffee has zero chicory." in directive


def test_strategy_brief_includes_video_learning():
    brief = gd.get_strategy_brief(306)
    assert "VIDEO LEARNING & OUTCOMES FEEDBACK" in brief
    assert "HIGH-RETENTION" in brief or "CRITICAL OWNER MANDATE" in brief


def test_video_prompts_include_video_learning():
    # 1. Growth Reel
    gr = gr_prompt.build(1)
    assert "VIDEO LEARNING & OUTCOMES FEEDBACK" in gr
    assert "INSTAGRAM" in gr

    # 2. Reel 1
    r1 = reels_prompt.build("reel_1", ("tension", "Tension hook"), "09:53", "HASHTAG_25", "", 1)
    assert "VIDEO LEARNING & OUTCOMES FEEDBACK" in r1
    assert "INSTAGRAM" in r1

    # 3. YouTube Short
    yt = yt_prompt.build("Bold", 1)
    assert "VIDEO LEARNING & OUTCOMES FEEDBACK" in yt
    assert "YOUTUBE SHORTS" in yt
