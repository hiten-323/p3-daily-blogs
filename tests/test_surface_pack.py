"""Every surface keeps a true caption and a jar frame that can pass visual QA."""
from __future__ import annotations

import json

from PIL import Image

from content_generator.creative.cinematic_frame import compose_cinematic_frame
from content_generator.creative.jar_frame import audit_product_image
from content_generator.creative.real_jar_composer import compose_carousel_slide
from content_generator.creative.surface_frames import compose_editorial_card
from content_generator.publisher.surface_copy import (
    audit_copy,
    clean_reel_beats,
    clean_slide_copy,
    finalize_facebook,
    finalize_instagram,
    finalize_linkedin,
    finalize_threads,
)


def _pack() -> dict:
    return {
        "featured_product": "Bold",
        "day_number": 285,
        "growth_reel": {
            "hook_text": "Most people waste Rs 200 every week on this.",
            "featured_product": "Bold",
            "caption": "A home cup instead of the cafe receipt.",
            "script": [
                {"on_screen": "RS 200 EVERY DAY.", "voiceover": "Most people waste Rs 200 every week on a habit."},
                {"on_screen": "AGGOMERATED COFFEE", "voiceover": "Bold is agglomerated 100% Robusta."},
            ],
        },
        "linkedin_post": {
            "featured_product": "Bold",
            "hook": "Why your morning coffee routine is secretly tanking your deep work.",
            "body": (
                "Here is what executive chronobiology tells us: a glycemic and adrenal spike. "
                "If your jar contains hidden chicory or roasted root fillers, you are drinking a low-grade chicory infusion. "
                "Ultra Blend is 70% coffee."
            ),
            "cta": "Follow Hiten Jain and explore the jars at https://p3online.in",
            "hashtags": "#One #Two #Three #Four #Five #Six #Seven #Eight #Nine #Ten",
        },
        "threads_post": {
            "featured_product": "Bold",
            "text": "Unpopular opinion: sugar in instant coffee is self-defense against roasted root filler.\n\nCheck the ingredient panel.",
        },
        "facebook_post": {
            "featured_product": "Bold",
            "hook": "That third spoon of sugar is a rescue mission.",
            "body": "Commercial jars bulk up with roasted root filler. Bold is 100% Robusta with zero chicory.",
            "community_question": "What does your jar list?",
            "cta": "Follow our page. Discover the cup at https://p3online.in",
            "hashtags": "#PurityBeans #IndianCoffee #MorningCoffee #CoffeeLovers #CleanCoffee #ExtraOne",
        },
        "stories": {"story_1": {"type": "poll", "headline": "THE CORPORATE CUP", "poll_question": "Mystery chicory?"}},
        "carousel": {"slides": []},
    }


def test_linkedin_threads_and_facebook_copy_pass_platform_rules():
    content = _pack()
    linkedin = finalize_linkedin(content)
    threads = finalize_threads(content)
    facebook = finalize_facebook(content)
    for platform, text in (("linkedin", linkedin), ("threads", threads), ("facebook", facebook)):
        result = audit_copy(platform, text, featured="Bold")
        assert result["ok"], (platform, result, text)
    assert "chronobiology" not in linkedin.lower()
    assert "roasted root" not in linkedin.lower()
    assert "30% chicory" in linkedin.lower() or "30% chicory" in linkedin
    assert "I build Purity Beans" in linkedin or "Hiten" in linkedin
    assert "APPROVED" not in linkedin
    assert len(threads) <= 500
    assert "roasted root" not in threads.lower()
    assert len(facebook.split("#")) - 1 <= 5


def test_approved_linkedin_sentence_is_kept():
    text = finalize_linkedin({
        "linkedin_post": {"hook": "APPROVED LINKEDIN BODY about the label on the jar.", "body": "The ratio is printed on the glass."},
        "featured_product": "Bold",
    })
    assert "APPROVED LINKEDIN BODY" in text
    assert audit_copy("linkedin", text, featured="Bold")["ok"]


def test_reel_beats_do_not_contradict_the_week():
    beats = clean_reel_beats(_pack()["growth_reel"])
    assert "EVERY WEEK" in beats[0]["on"].upper()
    assert "EVERY DAY" not in beats[0]["on"].upper()
    assert "AGGLOMERATED" in beats[1]["on"]
    assert "AGGOMERATED" not in beats[1]["on"]


def test_slide_copy_discloses_ultra_and_drops_invented_percents():
    heading, body = clean_slide_copy(
        "The Purity Beans Standard",
        "Ultra Blend is 70% coffee. Brands hide 30% to 49% chicory filler.",
        "Bold",
    )
    blob = f"{heading} {body}".lower()
    assert "30% chicory" in blob
    assert "49%" not in blob


def test_reel_frame_and_editorial_card_pass_visual_qa(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    import content_generator.creative.jar_frame as jar_frame
    import content_generator.creative.real_jar_composer as real_jar
    monkeypatch.setattr(jar_frame, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(real_jar, "_OUT_DIR", str(tmp_path))
    reel = compose_cinematic_frame(
        headline="Most people waste Rs 200 every week on this.",
        sub="100% Robusta. Zero chicory.",
        product="Bold",
        width=1080,
        height=1920,
        label="reel_surface",
        format_type="reel",
        on_date="2026-10-13",
    )
    assert reel
    with Image.open(reel) as image:
        assert image.size == (1080, 1920)
    visual = audit_product_image(reel)
    assert visual["ok"], visual
    geometry = json.loads(open(reel + ".jar.json", encoding="utf-8").read())
    assert geometry["scale"] <= 1.0
    assert "bold_50g_front" in geometry["source_asset"]

    card = compose_editorial_card(
        "Freeze-Dried Coffee: The Cold Lock",
        "Freeze-drying keeps the aroma. Bold is agglomerated 100% Robusta.",
        idx=2,
        total_slides=6,
        width=1080,
        height=1350,
        label="middle_surface",
        product="Bold",
        out_dir=str(tmp_path),
    )
    assert card
    with Image.open(card) as image:
        assert image.size == (1080, 1350)
    card_geometry = json.loads(open(card + ".jar.json", encoding="utf-8").read())
    assert card_geometry["jar_required"] is False

    cover = compose_carousel_slide(
        "The Real Difference",
        "Bold is agglomerated 100% Robusta. Zero chicory.",
        day=285,
        idx=0,
        total_slides=3,
        width=1080,
        height=1350,
        label="cover_surface",
        product="Bold",
    )
    assert cover
    cover_audit = audit_product_image(cover)
    assert cover_audit["ok"], cover_audit


def test_instagram_caption_includes_shop_and_stays_true():
    caption = finalize_instagram(
        "A home cup instead of the cafe receipt.",
        {"hashtags": "#PurityBeans #InstantCoffee #Coffee #MorningCoffee #IndianCoffee"},
        day=285,
        featured="Bold",
    )
    result = audit_copy("instagram", caption, featured="Bold")
    assert result["ok"], (result, caption)
