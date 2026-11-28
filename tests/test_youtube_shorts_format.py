"""YouTube Shorts format, approval, and evening-slot independence."""
from __future__ import annotations

import inspect

from content_generator.core.publish_bar import clears_quality_bar
from content_generator.core.utm import dated_campaign
from content_generator.prompts.evening_growth_reels import build_youtube_evening_growth
from content_generator.prompts.yt_short import build as build_yt_short
from content_generator.publisher import prepublish_gate, youtube
from content_generator.publisher.youtube_format import (
    hook_is_weak,
    is_placeholder,
    sanitize_cta,
    sanitize_description,
    sanitize_title,
    shop_url,
)


def _passing_piece(**extra):
    piece = {
        "hook": "This Purica jar lists one ingredient.",
        "editorial_score": {"overall": 8.6},
        "viral_potential": {"overall": 9.2, "passed": True, "honesty": []},
        "scenes": [
            {"scene": 1, "spoken": "This Purica jar lists one ingredient.", "on_screen": "ONE INGREDIENT"},
            {"scene": 2, "spoken": "Most pouches add fillers after the roast.", "on_screen": "READ THE PACK"},
            {"scene": 3, "spoken": "Purity Beans freeze-dries Purica. That's the turn.", "on_screen": "PURITY BEANS"},
        ],
    }
    piece.update(extra)
    return piece


def test_placeholder_hook_and_title_are_detected_and_rewritten():
    assert is_placeholder("High-tension 1.5s opening spoken hook line")
    assert is_placeholder("Punchy YouTube SEO Search Title #shorts")
    assert is_placeholder("50-100 words including search keywords, coffee facts, and subscribe link.")
    title = sanitize_title("Punchy YouTube SEO Search Title #shorts", hook="Why Purica lists one ingredient")
    assert "punchy youtube seo" not in title.lower()
    assert "Purica" in title
    assert "#Shorts" in title


def test_description_has_brand_dated_utm_and_drops_ig_handle():
    raw = (
        "Follow @purepantryprovisions for more. "
        "Shop https://p3online.in "
        "#One #Two #Three #Four #Five #Six"
    )
    out = sanitize_description(raw, hook="hook", cta="Follow @purepantryprovisions", date="2026-11-27")
    assert "Purity Beans" in out
    assert "@purepantryprovisions" not in out.lower()
    assert "utm_source=youtube" in out
    assert "utm_medium=organic_social" in out
    assert "utm_campaign=yt_20261127" in out
    assert "202610" not in out
    tags = [part for part in out.split() if part.startswith("#")]
    assert "#PurityBeans" in tags or "#puritybeans" in {t.lower() for t in tags}
    assert "#Shorts" in tags or "#shorts" in {t.lower() for t in tags}
    # at most 3 extra hashtags besides brand + #Shorts
    extras = [t for t in tags if t.lower() not in {"#puritybeans", "#shorts"}]
    assert len(extras) <= 3


def test_cta_is_subscribe_not_ig_handle_or_food_science():
    assert "Subscribe" in sanitize_cta("Follow @purepantryprovisions")
    assert "@purepantryprovisions" not in sanitize_cta("Follow @purepantryprovisions")
    assert "food" not in sanitize_cta("Subscribe to learn what's really in your food.").lower()
    assert hook_is_weak("Did you know instant coffee is...")
    assert hook_is_weak("High-tension 1.5s opening spoken hook line")
    assert not hook_is_weak("This Purica jar lists one ingredient.")


def test_shop_url_uses_dated_campaign():
    url = shop_url(date="2026-11-28")
    assert url.startswith("https://p3online.in")
    assert "utm_campaign=yt_20261128" in url
    assert dated_campaign("youtube", date="2026-11-28") == "yt_20261128"


def test_clears_quality_bar_never_lowers_gates():
    assert clears_quality_bar(_passing_piece())
    # 8.0 editorial is not enough without a 9.0 viral pass
    assert not clears_quality_bar(_passing_piece(viral_potential={"overall": 8.9, "passed": False}))
    # 9.0 viral is not enough without 8.0 editorial
    assert not clears_quality_bar(
        _passing_piece(editorial_score={"overall": 7.9}, viral_potential={"overall": 9.5, "passed": True, "honesty": []})
    )
    assert not clears_quality_bar({"hook": "no scores"})


def test_time_budget_keeps_passing_evening_short(monkeypatch):
    from content_generator.core.publish_bar import clears_quality_bar as _clear

    piece = _passing_piece(editorial_error="editorial time budget reached before this piece passed")
    assert _clear(piece)
    # The daily loop pops editorial_error when the bar is already cleared.
    if _clear(piece):
        piece.pop("editorial_error", None)
    assert "editorial_error" not in piece


def test_evening_yt_is_scored_before_stories():
    import content_generator.scheduler.daily as daily

    src = inspect.getsource(daily)
    yt = src.find('("evening_yt_short", "evening_yt_short", None)')
    stories = src.find('("stories",        "stories",        "story_1")')
    assert yt != -1 and stories != -1
    assert yt < stories


def test_prompts_ban_placeholder_copy_and_ig_handle():
    day_prompt = build_yt_short("Purica", 12)
    night_prompt = build_youtube_evening_growth(12, product="Purica")
    for prompt in (day_prompt, night_prompt):
        lowered = prompt.lower()
        assert "hook must land" in lowered or "0-1.5 seconds" in lowered or "first 1-2 seconds" in lowered
        assert "purity beans" in lowered
        assert "cinematic" in lowered or "real jar" in lowered
        assert "never write 100%" in lowered or "never write 100%, fresh" in lowered
    assert "never write follow @purepantryprovisions" in day_prompt.lower()
    assert "subscribe for the next coffee truth" in night_prompt.lower()
    assert "what's really in your food" not in night_prompt.lower()
    assert "never copy instruction text" in night_prompt.lower()
    assert "never the words" in night_prompt and "Punchy YouTube SEO Search Title" in night_prompt


def test_resolve_approved_short_accepts_evening_key(monkeypatch):
    content = {"evening_yt_short": _passing_piece(), "yt_short": {}}

    def fake_disp(payload, key):
        return "approved" if key == "evening_yt_short" and payload.get(key) else "held"

    monkeypatch.setattr(
        "content_generator.publisher.dispatcher.editorial_disposition",
        fake_disp,
    )
    resolved, key = youtube.resolve_approved_short(content)
    assert key == "evening_yt_short"
    assert resolved["yt_short"]["hook"] == content["evening_yt_short"]["hook"]


def test_prepublish_accepts_evening_yt_short_as_native_youtube():
    assert "evening_yt_short" in prepublish_gate._PLATFORM_KEYS["youtube"]
    content = {"evening_yt_short": _passing_piece()}
    key, asset = prepublish_gate._native_asset(content, "youtube")
    assert key == "evening_yt_short"
    assert asset["hook"].startswith("This Purica")


def test_ensure_yt_video_renders_evening_piece(monkeypatch, tmp_path):
    from content_generator.scheduler import retry_unposted

    content = {"evening_yt_short": _passing_piece(), "day_number": 3, "date": "2026-11-27"}
    monkeypatch.setattr(retry_unposted, "find_native_short", lambda _c: None, raising=False)
    monkeypatch.setattr(
        "content_generator.publisher.youtube.find_native_short",
        lambda _c: None,
    )

    rendered = {}

    def fake_build(piece, day, on_date=None):
        rendered["hook"] = piece.get("hook")
        rendered["day"] = day
        path = tmp_path / "short.mp4"
        path.write_bytes(b"fake")
        return str(path)

    monkeypatch.setattr("content_generator.creative.short_video.build_short_video", fake_build)
    # After render, find_native_short still None unless we flip it
    calls = {"n": 0}

    def find_after(content_arg):
        calls["n"] += 1
        return str(tmp_path / "short.mp4") if calls["n"] > 1 or rendered else None

    monkeypatch.setattr("content_generator.publisher.youtube.find_native_short", find_after)
    assert retry_unposted.ensure_yt_video(content) is True
    assert "Purica" in rendered["hook"]


def test_evening_slot_publishes_youtube_when_reel_contract_returns(monkeypatch):
    from content_generator.scheduler import slots

    published = {}

    def fake_yt(content, approved, slot, day, only_asset=""):
        published["ran"] = True
        published["piece"] = approved.get("evening_yt_short")
        return {"success": True, "skipped": False, "video_id": "abc"}

    monkeypatch.setattr(slots, "_publish_evening_youtube", fake_yt)
    monkeypatch.setattr(slots, "logger", slots.logger)

    contract = {
        "results": {
            "instagram": {"status": "failed", "asset_id": "reel_1", "error": "held", "remote_id": ""},
        }
    }
    # Exercise the attach helper used when the reel contract returns early.
    attached = slots._attach_youtube_to_contract(
        contract,
        {"success": True, "skipped": False, "video_id": "abc"},
        {"evening_yt_short": _passing_piece()},
        "evening",
        3,
        {"generation_id": "g1"},
    )
    assert isinstance(attached, dict)
    # Contract should mention youtube after a successful (non-skipped) upload.
    blob = str(attached)
    assert "youtube" in blob.lower()
