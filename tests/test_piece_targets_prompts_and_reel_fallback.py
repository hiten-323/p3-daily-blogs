"""Separate retry targets, reel fallback, and the Short/reel prompt contract.

The 8.0 editorial and viral gates stay where they are. Product-truth and
process-match are not bypassed.
"""
from content_generator.scheduler import retry_unposted as ru


def test_exhausted_reel_regens_even_when_another_reel_passed():
    approved = {"growth_reel": {"hook": "passed"}}
    queued = ru.labels_to_regen(["reel_1", "reel_2", "growth_reel"], approved, records=[])
    assert queued == ["reel_1", "reel_2"]


def test_mark_fresh_clears_ladder_hold_and_asks_for_a_new_draft():
    content = {"reels": [{
        "hook": "old",
        "ladder_exhausted": True,
        "publish_blocked": "ladder_exhausted",
        "held": True,
        "hold_reason": "FALLBACK LADDER EXHAUSTED: brand",
        "editorial_score": {"overall": 5.1},
    }, {"hook": "b"}]}
    ru.mark_fresh(content, ["reel_1"])
    piece = content["reels"][0]
    assert piece["needs_regen"] is True
    assert "ladder_exhausted" not in piece
    assert piece.get("publish_blocked") != "ladder_exhausted"
    assert "editorial_score" not in piece


def test_asset_aware_dedupe(monkeypatch):
    from content_generator.publisher import publishing_ledger as pl
    rows = [
        {"ledger_key": "k1", "platform": "instagram_video", "slot": "evening",
         "status": "VERIFIED_LIVE", "asset": "reel_1"},
        {"ledger_key": "k2", "platform": "instagram", "slot": "morning",
         "status": "VERIFIED_LIVE"},
    ]
    monkeypatch.setattr(pl, "records_for_content_date", lambda _d: rows)
    when = "2026-01-02"
    assert pl.already_posted_today("instagram_video", "evening", "", on_date=when, asset="reel_2") is None
    assert pl.already_posted_today("instagram_video", "evening", "", on_date=when, asset="reel_1")["asset"] == "reel_1"
    assert pl.already_posted_today("instagram", "morning", "", on_date=when, asset="carousel") is None
    assert pl.already_posted_today("instagram", "morning", "", on_date=when, asset="instagram_post")["slot"] == "morning"


def test_gates_stay_at_8():
    from content_generator.core.editorial_engine import get_current_pass_score
    from content_generator.core.fallback_ladder import PASS_FLOOR
    from content_generator.core.viral_gate import PASS_MARK
    assert PASS_FLOOR == 8.0
    assert PASS_MARK == 8.0
    assert float(get_current_pass_score()) == 8.0


def test_scratch_prompt_feeds_the_judge_critique_back():
    from content_generator.core.fallback_ladder import scratch_prompt
    critique = (
        "viral: score 5.1 < 8.0. The hook 'Most people never read the back of their coffee jar' "
        "is generic and the scenes had no tension."
    )
    prompt = scratch_prompt(
        "yt_short",
        {"hook": "Most people never read the back of their coffee jar", "scenes": [], "featured_product": "Purica"},
        critique, 8.0, "BRAND",
    )
    assert "JUDGE CRITIQUE TO FIX" in prompt
    assert "Most people never read the back of their coffee jar" in prompt
    assert "contained a banned claim" not in prompt
    assert "tension-then-payoff" in prompt
    assert "last 7 days" in prompt
    assert "Most people never read the back of their coffee jar" not in prompt.split("JUDGE CRITIQUE")[0]


def test_short_and_reel_prompts_require_awe_and_tension():
    from content_generator.prompts import reels, yt_short
    short = yt_short.build("Purica", 295)
    reel = reels.build("reel_1", ("curiosity", "open a loop"), "morning", "reel_morning", "", 295)
    for prompt in (short, reel):
        assert "tension" in prompt.lower()
        assert "payoff" in prompt.lower()
        assert "last 7 days" in prompt
        assert "Most people never" in prompt
    assert "product dump" in short.lower() or "no tension" in short.lower()


def test_follow_growth_prompt_is_value_first_and_the_gate_still_rejects_sales():
    from content_generator.core.content_contract import check_objective_compliance
    from content_generator.prompts import instagram_post
    prompt = instagram_post.build(295, "")
    assert "value first" in prompt.lower()
    assert "Shop now" not in prompt
    salesy = {
        "objective": "FOLLOW",
        "hook": "Buy the jar today",
        "caption": "Shop now. Limited offer. Buy your jar at the sale price.",
        "cta": "Follow @purepantryprovisions and shop the offer",
    }
    assert check_objective_compliance(salesy)["passes"] is False
    useful = {
        "objective": "FOLLOW",
        "hook": "The spoon left in the tin overnight",
        "caption": (
            "How to keep the next cup from tasting flat: the difference is a dry spoon and a closed lid. "
            "That is the lesson. Follow @purepantryprovisions for the next check."
        ),
        "cta": "Follow @purepantryprovisions",
    }
    assert check_objective_compliance(useful)["passes"] is True


def test_pick_skips_a_layout_that_just_failed():
    from content_generator.creative.shorts_concepts import pick
    first = pick("2026-10-23", "reel", sku="ultra_blend", history=[])
    second = pick("2026-10-23", "reel", sku="ultra_blend", history=[], exclude_layouts=[first["layout"]])
    assert second["layout"] != first["layout"]


def test_failed_plate_is_skipped_on_the_next_fetch(tmp_path, monkeypatch):
    from content_generator.creative import ai_backgrounds, hf_video, kaggle_bank
    ai_backgrounds.reset_session()
    for name in ("HF_TOKEN", "PIXAZO_API_KEY", "RUNWAY_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY"):
        monkeypatch.setenv(name, "present")
    monkeypatch.setattr(ai_backgrounds, "load_frames", lambda *_a, **_k: [b"frame"])
    monkeypatch.setattr(kaggle_bank, "available", lambda: True)
    calls = []

    def take(*_a, **_k):
        calls.append("kaggle_bank")
        plate = tmp_path / "kaggle.mp4"
        plate.write_bytes(b"k")
        return {"path": str(plate), "id": "kaggle:1", "source": "kaggle_bank"}

    def ltx(*_a, **_k):
        calls.append("hf_ltx")
        plate = tmp_path / "ltx.mp4"
        plate.write_bytes(b"h")
        return str(plate)

    monkeypatch.setattr(kaggle_bank, "take", take)
    monkeypatch.setattr(hf_video, "ltx", ltx)
    monkeypatch.setattr(hf_video, "wan", lambda *_a, **_k: None)
    choice = {"date": "2026-10-23", "format": "reel", "concept": "velvet_orbit"}
    assert ai_backgrounds.fetch_background(choice, "lab", (8, 8), 5)[1] == "kaggle_bank"
    ai_backgrounds.reject_source(choice, "kaggle_bank")
    assert ai_backgrounds.fetch_background(choice, "lab", (8, 8), 5)[1] == "hf_ltx"
    assert calls == ["kaggle_bank", "hf_ltx"]


def test_new_obstacle_phrases_become_lessons():
    from content_generator.core.obstacle_lessons import classify
    assert classify("The hook is generic and the scenes had no tension") == "generic_hook"
    assert classify("scenes had no tension and no stakes") == "tension"
    assert classify("primarily promotional/commercial copy") == "salesy_follow"
    assert classify("same_layout_as_last_tile:hero_center") == "aesthetic"
