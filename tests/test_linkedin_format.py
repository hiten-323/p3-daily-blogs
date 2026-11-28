"""LinkedIn B2B format: hook first, no body link, one CTA, <=3 hashtags, dated UTM."""
from __future__ import annotations

import datetime as dt

from content_generator.core import viral_gate
from content_generator.core.editorial_engine import get_current_pass_score
from content_generator.creative.visual_gate import AESTHETIC_PASS
from content_generator.publisher import linkedin_format as lf


def _content(hook, body, cta, hashtags, date="2026-11-28", product="Bold"):
    return {
        "date": date,
        "day_number": 331,
        "featured_product": product,
        "generation_id": "gen_2026-11-28_abcd1234",
        "linkedin_post": {
            "type": "linkedin_post",
            "angle": "pantry_economics",
            "hook": hook,
            "body": body,
            "cta": cta,
            "hashtags": hashtags,
            "featured_product": product,
        },
    }


SAMPLE = _content(
    hook="Office pantries still hide the chicory ratio on the back of the jar.",
    body=(
        "When a facilities lead asks what goes into the office urn, the useful "
        "answer is on the front of the jar, not in a brochure.\n\n"
        "Purity Beans Bold is agglomerated pure coffee with 0% chicory. Ultra Blend "
        "is a 70% coffee, 30% chicory milk coffee — same type size, no hiding.\n\n"
        "That is the conversation we have with distributors and pantry buyers."
    ),
    cta=(
        "Follow @purepantryprovisions for how a coffee brand is actually built. "
        "Save this before your next grocery run. Shop Purity Beans at "
        "https://p3online.in/?utm_source=linkedin&utm_medium=post&utm_campaign=202610"
    ),
    hashtags=(
        "#PurityBeans #PureCoffee #InstantCoffee #CoffeeLover #IndianCoffee "
        "#CoffeeIndia #MadeInIndia #GlassJar #GourmetCoffee #BoldCoffee "
        "#AgglomeratedCoffee #CleanLabel #IndianBrands #MorningCoffee #CoffeeRitual"
    ),
)


def test_linkedin_payload_format(monkeypatch, tmp_path):
    photo = tmp_path / "puritybeans_bold_front.png"
    photo.write_bytes(b"fake-jar")
    monkeypatch.setattr(lf, "real_product_photo", lambda content: str(photo))

    payload = lf.build_payload(SAMPLE, day=331)
    commentary = payload["commentary"]
    assert "http://" not in commentary.lower()
    assert "https://" not in commentary.lower()
    tags = [t for t in commentary.split() if t.startswith("#")]
    assert len(tags) <= 3
    assert "#PurityBeans" in tags
    assert "@purepantryprovisions" not in commentary.lower()
    assert "grocery run" not in commentary.lower()
    assert commentary.lower().count("comment") + commentary.lower().count("dm") >= 1
    hook = "Office pantries still hide the chicory ratio on the back of the jar."
    assert commentary[:200].startswith(hook) or hook in commentary[:210]
    comment = payload["comment"]
    assert "utm_source=linkedin" in comment
    assert "utm_medium=organic_social" in comment
    assert "utm_campaign=li_20261128_" in comment
    assert payload["image_path"] == str(photo)
    assert "bold" in payload["image_path"].lower()
    assert "100%" not in commentary
    assert "fresh" not in commentary.lower()
    assert "lab tested" not in commentary.lower()
    assert "single-origin" not in commentary.lower()
    # Ultra Blend is mentioned with the 70/30 disclosure and is not called pure
    low = commentary.lower()
    if "ultra blend" in low:
        assert "pure" not in low.split("ultra blend", 1)[1][:80]
        assert "70%" in commentary and "chicory" in low


def test_posting_window_weekdays_only():
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    monday_0900 = dt.datetime(2026, 11, 30, 9, 0, tzinfo=ist)  # Monday
    monday_0600 = dt.datetime(2026, 11, 30, 6, 13, tzinfo=ist)
    monday_1713 = dt.datetime(2026, 11, 30, 17, 13, tzinfo=ist)
    saturday_0900 = dt.datetime(2026, 11, 28, 9, 0, tzinfo=ist)
    assert lf.posting_window_open(monday_0900) is True
    assert lf.posting_window_open(monday_0600) is False
    assert lf.posting_window_open(monday_1713) is False
    assert lf.posting_window_open(saturday_0900) is False


def test_gate_constants_unchanged():
    assert viral_gate.PASS_MARK == 9.0
    assert float(get_current_pass_score()) == 8.0
    assert AESTHETIC_PASS == 8.0


def test_linkedin_repeated_premise_is_a_collision():
    from content_generator.core.distinctness import find_collisions, fingerprint

    today = {
        "linkedin_post": {
            "hook": "The first jar we sold taught me more than any plan did.",
            "body": "We walked away from a signed contract after the pilot batch failed.",
            "cta": "Comment DISTRIBUTION for the trade sheet.",
        }
    }
    history = [{
        **fingerprint("linkedin_post", {
            "hook": "I watched our pilot Bold batch die in the cup.",
            "body": "We walked away from a signed contract and started over. The label is the only contract that matters.",
            "cta": "Comment below.",
        }),
        "date": "2026-11-26",
        "label": "linkedin_post",
    }]
    collisions = find_collisions(today, history)
    kinds = [c["reason"] for c in collisions if c["label"] == "linkedin_post"]
    assert any("premise" in r for r in kinds)
