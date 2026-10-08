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


def test_threads_is_conversational_and_avoids_promo_links():
    th = th_prompt.build(("CHICORY TRUTH", "40% filler in commercial coffee"), day=1)
    # Native Threads must not force promotional links or hashtag clutter in the thread copy
    assert "NO PROMOTIONAL LINKS" in th
    assert "NO HASHTAG CLUTTER" in th
    assert "UNDER 480 CHARACTERS" in th
    assert "Follow for daily coffee truths" in th
    assert "with Purity Beans and https://" not in th


def test_portfolio_commercial_cap_in_ignition():
    from content_generator.core.content_balance import enforce_portfolio_commercial_cap, get_stage_product_cap
    from content_generator.core.growth_director import get_growth_stage

    # In IGNITION stage (0-1K), max product share is 5%
    stage = get_growth_stage(followers=100)
    assert stage["sell_pct"] == 5
    assert get_stage_product_cap(followers=100) == 0.05

    # With 4 assets, floor(4 * 0.05) == 0, so commercial count must be 0
    content = {
        "reel_1": {"caption": "How to brew at 85°C: why boiling water extracts bitter tannins. Learn the method.", "funnel_objective": "DISCOVERY"},
        "reel_2": {"caption": "Buy our jar now at Rs 450. Discount coupon inside.", "funnel_objective": "CONVERSION", "objective": "Consumer Purchase"},
        "carousel": {"caption": "Read the label on the back. Pure vs chicory guide. Check ingredients.", "funnel_objective": "AUTHORITY"},
        "instagram_post": {"caption": "Check out our sale! Add to cart now at p3online.in. Buy today.", "funnel_objective": "CONVERSION", "objective": "Consumer Purchase"},
    }
    valid = ["reel_1", "reel_2", "carousel", "instagram_post"]
    filtered = enforce_portfolio_commercial_cap(valid, content)

    # Both commercial assets must be dropped from publication
    assert "reel_2" not in filtered
    assert "instagram_post" not in filtered
    assert "reel_1" in filtered
    assert "carousel" in filtered


def test_objective_compliance_rejects_disguised_sales_pitches():
    from content_generator.core.content_contract import check_objective_compliance

    # A promotional sales pitch with a follow CTA tacked on is NOT a FOLLOW asset
    disguised = {
        "funnel_objective": "FOLLOW",
        "hook": "Limited time offer on our jars",
        "caption": "Buy our jar now! Special discount at checkout. Use code COFFEE for 20% off. Add to cart today.",
        "cta": "Follow @puritybeans and buy now at p3online.in",
    }
    compliance = check_objective_compliance(disguised)
    assert not compliance["passes"]
    assert not compliance["creative_compliant"]
    assert "selling to strangers wastes viral reach" in compliance["reason"]


def test_semantic_premise_lock_detects_topic_collapse():
    from content_generator.core.semantic_lock import verify_portfolio_diversity

    # Collapsed portfolio (multiple rewrites of chicory filler)
    collapsed = {
        "reel_1": {"hook": "Chicory root filler is what brands hide."},
        "reel_2": {"caption": "Why mass market brands add 40% roasted chicory."},
        "carousel": {"headline": "The wartime history of chicory root adulteration."},
    }
    report = verify_portfolio_diversity(collapsed)
    assert not report["passes"]
    assert "chicory_filler" in report["duplicates"]

    # Diversified portfolio across distinct semantic clusters
    diverse = {
        "reel_1": {"hook": "Why 100°C boiling water scorches natural coffee tannins."},
        "threads_post": {"text": "Big Coffee spends millions so you never turn the jar around to read the back."},
        "linkedin_post": {"body": "The thermodynamics of -40°C sublimation in freeze-dried vs spray-dried coffee."},
        "facebook_post": {"caption": "Rs 18 home Arabica cup vs Rs 250 cafe cup: what an Indian family saves in a year."},
    }
    div_report = verify_portfolio_diversity(diverse)
    assert div_report["passes"]
    assert len(div_report["duplicates"]) == 0


def test_youtube_holds_without_video_file(monkeypatch):
    import os
    monkeypatch.delenv("ALLOW_YOUTUBE_SLIDESHOW", raising=False)
    monkeypatch.setattr(youtube, "is_configured", lambda: True)
    monkeypatch.setattr(youtube, "_refresh_access_token", lambda: "fake_token")
    monkeypatch.setattr(youtube, "_find_video", lambda _: None)
    monkeypatch.setattr("content_generator.core.editorial_engine.approved_assets", lambda c: {"yt_short": c.get("yt_short")})

    valid_short = {
        "title": "Why 100°C Water Destroys Coffee",
        "description": "Brew at 85°C. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory by Purity Beans. Explore p3online.in.",
        "hook": "100°C water is scalding your coffee beans.",
        "script": "Never pour boiling water directly on coffee. Let it cool 60s to 85°C. Purity Beans makes 100% pure coffee with zero chicory. Rs 18 per cup at p3online.in.",
        "cta": "Subscribe for daily coffee truths.",
    }
    res = youtube.post_content({"yt_short": valid_short}, day=1)
    # Must HOLD rather than manufacture a low-retention slideshow
    assert res.get("held") is True
    assert res.get("error") == "held_no_native_video"


def test_creative_viral_readiness_evaluation():
    from content_generator.core.viral_readiness import evaluate_viral_readiness

    generic_ad = {
        "hook": "Start your day with premium quality coffee",
        "caption": "Perfect cup for coffee lovers. Rich aroma. Shop now.",
        "cta": "Buy at p3online.in",
    }
    gen_result = evaluate_viral_readiness(generic_ad, platform="reel_1")
    assert not gen_result["passes"]
    assert gen_result["score"] < 50.0

    viral_value_piece = {
        "hook": "Why 100°C water destroys your instant coffee in 5 seconds",
        "caption": "Boiling water extracts bitter tannins. Let water cool to 85°C. Bold and Purista are 100% Robusta with zero chicory. Send this to someone who drinks instant coffee.",
        "cta": "Follow @puritybeans so you never drink roasted root again.",
        "frames": [
            {"spoken": "Never pour boiling water directly on coffee."},
            {"spoken": "At 100°C you scorch the delicate aromatics."},
            {"spoken": "Cool the water for 60 seconds to 85°C."},
            {"spoken": "Taste the natural sweetness without adding sugar."},
            {"spoken": "Follow @puritybeans for daily honest coffee craft."},
        ],
    }
    viral_res = evaluate_viral_readiness(viral_value_piece, platform="reel_1")
    assert viral_res["passes"]
    assert viral_res["score"] >= 70.0


