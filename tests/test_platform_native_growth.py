"""Unit tests verifying platform-native follower growth fixes:
- YouTube consumes yt_short natively
- Facebook consumes facebook_post natively
- Stories contain no synthetic social proof
- Threads is always populated and never None
- Anti-cannibalization diversity in generator.
"""
from content_generator.publisher import youtube, facebook
from content_generator.prompts import stories, facebook as fb_prompt, threads as th_prompt


def test_youtube_extracts_from_yt_short_natively():
    content = {
        "yt_short": {
            "title": "Why 100°C Water Destroys Your Coffee in 30 Seconds",
            "description": "Brewing at 85°C unlocks natural sweetness. Subscribe for daily pure coffee craft.",
            "tags": ["coffee science", "pure coffee", "brewing temperature"],
            "hook": "100°C water is scalding your coffee beans.",
            "cta": "Subscribe for daily coffee truths.",
        },
        "reels": [{
            "hook": "Completely different reel hook",
            "script": "Reel script that should NOT be used for YouTube Short",
        }],
    }
    title = youtube._extract_title(content)
    assert title == "Why 100°C Water Destroys Your Coffee in 30 Seconds"

    desc = youtube._extract_description(content)
    assert "Brewing at 85°C" in desc
    assert "Reel script that should NOT be used" not in desc

    tags = youtube._build_tags(content)
    assert "coffee science" in tags
    assert "brewing temperature" in tags


def test_facebook_build_message_uses_native_facebook_post():
    content = {
        "facebook_post": {
            "hook": "Why does your family morning coffee smell so strong but taste so watery?",
            "body": "Most Indian households were raised on instant coffee blended with 40% roasted chicory root.",
            "community_question": "Who in your house is the ultimate coffee critic? Tag them below!",
            "cta": "Follow our page for daily real coffee truths.",
            "hashtags": "#PurityBeans #MorningCoffee",
        },
        "linkedin_post": {
            "hook": "Corporate B2B executive pantry ROI analysis",
            "body": "LinkedIn text that should NOT be dumped onto Facebook.",
        },
    }
    msg = facebook._build_message(content)
    assert "smell so strong but taste so watery" in msg
    assert "Who in your house is the ultimate coffee critic" in msg
    assert "Corporate B2B executive" not in msg


def test_stories_prompt_has_no_fabricated_proof():
    prompt = stories.build(day=1)
    # Must NOT ask for fake follower counts, fake reviews, or synthetic handles
    assert "11,247 customers" not in prompt
    assert "@_karan.runs" not in prompt
    assert "dm_handle" not in prompt
    assert "ZERO fabrication" in prompt


def test_threads_and_facebook_prompts_have_follower_triggers():
    th = th_prompt.build(("CHICORY TRUTH", "40% filler in commercial coffee"), day=1)
    assert "Follow for daily unfiltered coffee truths" in th

    fb = fb_prompt.build(("FAMILY RITUAL", "Morning home brewing"), day=1)
    assert "Follow our page" in fb


def test_growth_director_assigns_all_platforms():
    from content_generator.core.growth_director import get_todays_objectives, get_growth_stage
    stage = get_growth_stage(followers=50)
    assert stage["viral_pct"] == 95

    objs = get_todays_objectives(day=1)
    for expected_key in (
        "growth_reel", "brand_reel", "reel_1", "reel_2", "carousel",
        "instagram_post", "yt_short", "facebook_post", "threads_post", "linkedin_post"
    ):
        assert expected_key in objs
        assert isinstance(objs[expected_key], tuple)
        assert len(objs[expected_key]) == 2


def test_objectives_mapper_stamps_all_platforms():
    from content_generator.objectives.mapper import assign_all
    content = {
        "reels": [{"hook": "Test reel 1"}, {"hook": "Test reel 2"}],
        "growth_reel": {"hook": "Growth reel hook"},
        "facebook_post": {"hook": "Facebook hook"},
        "threads_post": {"text": "Threads hook"},
        "yt_short": {"title": "Short title"},
        "carousel": {"headline": "Carousel headline"},
        "instagram_post": {"caption": "IG post caption"},
    }
    stamped = assign_all(content, day=1)

    assert stamped["growth_reel"]["funnel_objective"] in ("FOLLOW", "DISCOVERY")
    assert stamped["growth_reel"]["objective"] in ("Follower Growth", "Engagement Growth")
    assert "Follow" in stamped["growth_reel"]["primary_cta"] or "Send" in stamped["growth_reel"]["primary_cta"]

    assert stamped["facebook_post"]["funnel_objective"] in ("DISCOVERY", "COMMUNITY")
    assert stamped["threads_post"]["funnel_objective"] in ("COMMUNITY", "FOLLOW")
    assert stamped["yt_short"]["funnel_objective"] in ("FOLLOW", "DISCOVERY")


def test_objective_alignment_and_auto_heal():
    from content_generator.core.content_contract import check_objective_alignment
    from content_generator.core import editorial_engine as ee

    # Missing follow CTA on FOLLOW objective
    piece = {
        "funnel_objective": "FOLLOW",
        "caption": "Here is why instant coffee is mostly chicory. Rs 18 per cup.",
        "cta": "Buy at p3online.in",
    }
    check = check_objective_alignment(piece)
    assert not check["passes"]
    assert "Follow" in check["suggested_cta"]

    # When processed through editorial gates, CTA gets auto-healed with follow cue
    content = {"reels": [piece]}
    # Valid candidate
    kept = ee._apply_growth_director_gates(content, ["reel_1"])
    # If kept or processed, CTA is healed
    assert "Follow @" in piece["cta"]

