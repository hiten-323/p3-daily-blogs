"""On-screen claims follow the jar, and the morning feed does not steal the reel."""
from __future__ import annotations

from content_generator.creative.cinematic_frame import onscreen_chrome
from content_generator.creative.real_jar_composer import _claim_pill
from content_generator.creative.reel_video import _beats_from_reel
from content_generator.creative.short_video import _scenes_from_short


def _blob(*parts: str) -> str:
    return " ".join(parts).upper()


def test_ultra_blend_chrome_never_says_zero_chicory():
    for fmt in ("short", "reel", "story"):
        badge, cta = onscreen_chrome(fmt, "Ultra Blend")
        text = _blob(badge, cta)
        assert "ZERO CHICORY" not in text
        assert "NO CHICORY" not in text
        assert "70%" in text
        assert "30%" in text


def test_pure_jar_chrome_may_say_zero_chicory():
    badge, cta = onscreen_chrome("short", "Bold")
    assert "ZERO CHICORY" in cta
    assert badge == "YOUTUBE SHORTS"


def test_unknown_jar_chrome_stays_on_the_slogan():
    for fmt in ("short", "reel", "story"):
        badge, cta = onscreen_chrome(fmt, None)
        text = _blob(badge, cta)
        assert "ZERO CHICORY" not in text
        assert "100% PURE" not in text
        assert "CLEANEST" in text or "READ THE LABEL" in text or "LINK IN BIO" in text or "SAVE THIS" in text


def test_empty_reel_fallback_is_claim_safe():
    ultra = " ".join(
        f"{beat['on']} {beat['sub']}" for beat in _beats_from_reel({"product": "Ultra Blend"})
    ).upper()
    assert "NO CHICORY" not in ultra
    assert "ZERO CHICORY" not in ultra
    assert "30%" in ultra

    unknown = " ".join(
        f"{beat['on']} {beat['sub']}" for beat in _beats_from_reel({})
    ).upper()
    assert "NO CHICORY" not in unknown
    assert "ZERO CHICORY" not in unknown


def test_empty_short_fallback_does_not_call_ultra_blend_pure():
    scenes = _scenes_from_short({"product": "Ultra Blend"})
    text = " ".join(f"{scene['on']} {scene['sub']}" for scene in scenes).upper()
    assert "100% PURE" not in text
    assert "ZERO CHICORY" not in text
    assert "30%" in text


def test_gourmet_duo_mini_chrome_is_zero_chicory_and_ultra_is_not():
    from content_generator.creative.cinematic_frame import _product_class

    assert _product_class("Gourmet Duo Mini") == "pure"
    assert _product_class("gourmet_duo_mini") == "pure"
    assert _product_class("Ultra Blend") == "ultra"
    assert _product_class("Gourmet Duo Mini vs Ultra Blend") == "unknown"

    badge, cta = onscreen_chrome("reel", "Gourmet Duo Mini")
    assert "ZERO CHICORY" in cta or "PURE COFFEE" in cta
    assert "30%" not in cta
    ultra_badge, ultra_cta = onscreen_chrome("reel", "Ultra Blend")
    assert "30%" in ultra_cta
    assert "ZERO CHICORY" not in ultra_cta
    mixed = " ".join(onscreen_chrome("reel", "Gourmet Duo Mini vs Ultra Blend")).upper()
    assert "ZERO CHICORY" not in mixed
    assert "30%" not in mixed

    duo = " ".join(
        f"{beat['on']} {beat['sub']}" for beat in _beats_from_reel({"product": "Gourmet Duo Mini"})
    ).upper()
    assert "ZERO CHICORY" in duo
    assert "30%" not in duo
    assert "ZERO CHICORY" in _claim_pill("Gourmet Duo Mini", "unlike Ultra Blend").upper()
    assert "30%" not in _claim_pill("Gourmet Duo Mini", "unlike Ultra Blend")


def test_feed_pill_follows_the_product():
    assert "30%" in _claim_pill("Ultra Blend", "Morning coffee")
    assert "ZERO CHICORY" not in _claim_pill("Ultra Blend", "Morning coffee").upper()
    assert "ZERO CHICORY" in _claim_pill("Purica", "Morning cup").upper()
    assert "ZERO CHICORY" not in _claim_pill(None, "Look at this jar").upper()


def test_morning_feed_does_not_publish_the_reel(monkeypatch):
    from content_generator.publisher import instagram as ig

    monkeypatch.setattr(ig, "is_configured", lambda: True)
    monkeypatch.setattr(ig, "_extract_caption", lambda content, day=0: "Read the label.")
    called = {"reel": 0, "carousel": 0}

    def _reel(day, on_date=None):
        called["reel"] += 1
        return "/tmp/reel.mp4"

    monkeypatch.setattr(ig, "_find_reel_video", _reel)
    monkeypatch.setattr(ig, "_find_carousel_images", lambda content: ["/tmp/a.jpg", "/tmp/b.jpg"])
    monkeypatch.setattr(
        "content_generator.publisher.prepublish_gate.authorize_publish",
        lambda content, platform: {"allowed": True, "reason": "ok"},
    )
    monkeypatch.setattr(
        "content_generator.creative.rendered_asset_qa.audit_rendered_images",
        lambda paths: {"ok": True, "issues": []},
    )
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_creative_suite",
        lambda paths: (True, []),
    )

    def _carousel(images, caption):
        called["carousel"] += 1
        return {"success": True, "media_id": "feed-1", "permalink": "", "error": None}

    monkeypatch.setattr(ig, "_post_carousel", _carousel)
    result = ig.post_content({"carousel": {"caption": "Read the label."}}, day=4)
    assert called["reel"] == 0
    assert called["carousel"] == 1
    assert result["success"] is True
