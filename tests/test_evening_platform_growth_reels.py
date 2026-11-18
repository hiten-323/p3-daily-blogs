"""Unit tests for evening platform-specific growth reels and history benchmark engine."""
import datetime as dt
import json
import pytest

from content_generator.core import history_benchmark as hb
from content_generator.core import reel_schedule as rs
from content_generator.core.editorial_engine import approved_assets, get_valid_assets
from content_generator.prompts import evening_growth_reels as egr
from content_generator.scheduler import retry_unposted as ru
from content_generator.scheduler import slots as sl


def test_evening_growth_targets_triad():
    """Verify that evening growth targets include Instagram, Facebook, and YouTube Shorts."""
    targets = rs.evening_growth_targets()
    assert "reel_1" in targets
    assert "growth_reel_fb" in targets
    assert "evening_yt_short" in targets
    # Preserve 2 reels a day maximum on Instagram
    assert rs.MAX_REELS_PER_DAY == 2
    assert rs.reel_for_slot("evening") == "reel_1"
    assert rs.reel_for_slot("morning") == "growth_reel"


def test_history_benchmark_extraction():
    """Test extracting platform history from learning logs and pack."""
    history_yt = hb.extract_platform_history("youtube")
    assert history_yt["platform"] == "youtube"
    assert "obstacle_lessons" in history_yt
    assert "audit_recommendations" in history_yt

    history_fb = hb.extract_platform_history("facebook")
    assert history_fb["platform"] == "facebook"
    assert "prior_hook" in history_fb

    history_ig = hb.extract_platform_history("instagram")
    assert history_ig["platform"] == "instagram"


def test_history_benchmark_prompt_injection():
    """Test that benchmark prompts contain the prior baseline and explicit improvement rules."""
    prompt_yt = hb.build_history_benchmark_prompt("youtube", 316)
    assert "HISTORICAL BENCHMARK & PRIOR GENERATION ANALYSIS" in prompt_yt
    assert "YOUTUBE SHORTS ALGORITHM OPTIMIZATION" in prompt_yt
    assert "Prior Hook:" in prompt_yt
    assert "Target Viral Quality Score: MUST EXCEED 8.0" in prompt_yt

    prompt_fb = hb.build_history_benchmark_prompt("facebook", 316)
    assert "FACEBOOK REELS & WATCH OPTIMIZATION" in prompt_fb
    assert "High-comment debate driver" in prompt_fb

    prompt_ig = hb.build_history_benchmark_prompt("instagram", 316)
    assert "INSTAGRAM EXPLORE & REELS OPTIMIZATION" in prompt_ig
    assert "Aesthetic 9:16 vertical cinematography" in prompt_ig


def test_verify_better_than_previous_guards():
    """Test that verify_better_than_previous rejects empty or repeated hooks."""
    # Empty piece
    ok, reason = hb.verify_better_than_previous({}, "youtube")
    assert not ok
    assert "empty_piece" in reason

    # Hook repeated from earlier generation
    history = hb.extract_platform_history("youtube")
    prior_hook = history["prior_hook"]
    repeated_piece = {
        "hook": prior_hook,
        "title": "Title #shorts",
        "scenes": [{"scene": 1}],
    }
    ok, reason = hb.verify_better_than_previous(repeated_piece, "youtube")
    assert not ok
    assert "hook_repeated" in reason

    # Superior new piece with distinct hook and required fields
    new_piece_yt = {
        "hook": "Why pouring 100°C water directly on instant coffee destroys the delicate aromatics",
        "title": "Water Temperature Coffee Secret #shorts",
        "scenes": [{"scene": 1, "duration_s": 3}],
    }
    ok, reason = hb.verify_better_than_previous(new_piece_yt, "youtube")
    assert ok
    assert "verified_superior" in reason


def test_prompt_builders_generate_valid_contracts():
    """Verify that evening prompt builders incorporate history context and produce contracts."""
    prompt_ig = egr.build_instagram_evening_growth(316, "Purica")
    assert "INSTAGRAM EVENING GROWTH REEL" in prompt_ig
    assert "craft_block" not in prompt_ig  # craft block was expanded
    assert "Purica" in prompt_ig

    prompt_fb = egr.build_facebook_evening_growth(316, "Ultra Blend")
    assert "FACEBOOK EVENING GROWTH REEL" in prompt_fb
    assert "community_question" in prompt_fb

    prompt_yt = egr.build_youtube_evening_growth(316, "Bold")
    assert "YOUTUBE SHORTS EVENING GROWTH REEL" in prompt_yt
    assert "loop_mechanic" in prompt_yt


def test_editorial_engine_validates_evening_triad():
    """Verify editorial engine validates growth_reel_fb and evening_yt_short."""
    content = {
        "growth_reel_fb": {
            "hook": "Do you boil your milk with instant coffee or pour it over? Most Indian homes do it backwards.",
            "caption": "A cup of coffee should never taste flat or burnt. The difference is pure freeze-dried Arabica with zero chicory from Purity Beans. Learn how to brew it right.",
            "community_question": "Which way do you brew at home?",
            "cta": "Follow @purepantryprovisions for daily brewing guides at p3online.in",
            "editorial_score": {"overall": 8.5},
        },
        "evening_yt_short": {
            "product": "Purica",
            "tagline": "Pure freeze-dried coffee without chicory by Purity Beans",
            "title": "The Big Coffee Temperature Mistake #shorts",
            "hook": "Why pouring boiling water ruins pure coffee crystals instantly",
            "scenes": [
                {"scene": 1, "type": "hook", "duration_s": 2, "on_screen": "DON'T BOIL", "spoken": "Stop boiling pure coffee.", "visual_direction": "Steam kettle"},
                {"scene": 2, "type": "tension", "duration_s": 3, "on_screen": "THE REASON", "spoken": "The reason is boiling water scalds delicate freeze dried arabica oils.", "visual_direction": "Thermometer at 100C"},
                {"scene": 3, "type": "solution", "duration_s": 4, "on_screen": "USE 85°C", "spoken": "Let the kettle rest 60 seconds to protect the ingredient.", "visual_direction": "Pouring at 85C"},
                {"scene": 4, "type": "payoff", "duration_s": 3, "on_screen": "SMOOTH TASTE", "spoken": "The difference is silky smooth coffee without chicory.", "visual_direction": "Golden crema swirl"},
                {"scene": 5, "type": "loop", "duration_s": 3, "on_screen": "SUBSCRIBE", "spoken": "Read the label next time you brew.", "visual_direction": "Loop back"},
            ],
            "description": "Brew Purity Beans coffee with 85C water. Guides at p3online.in",
            "cta": "Follow @purepantryprovisions and check p3online.in",
            "editorial_score": {"overall": 8.5},
        },
    }
    valid = get_valid_assets(content)
    assert "growth_reel_fb" in valid
    assert "evening_yt_short" in valid


def test_retry_unposted_includes_evening_targets():
    """Verify retry_unposted recognizes evening_fb and evening_youtube."""
    assert "evening_fb" in ru.TARGETS
    assert "evening_youtube" in ru.TARGETS
    assert ru.TARGETS["evening_fb"][0] == "evening"
    assert ru.TARGETS["evening_youtube"][0] == "evening"
    assert ru.PIECE_ASSET["evening_fb"] == "growth_reel_fb"
    assert ru.PIECE_ASSET["evening_youtube"] == "evening_yt_short"
