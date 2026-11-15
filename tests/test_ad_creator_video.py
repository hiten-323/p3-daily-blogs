"""Ad-creator video engine: timeline, captions, template rotation, real-jar-only render, gate."""
from __future__ import annotations

import os
import shutil

import pytest

from content_generator.creative import ad_creator as ac


@pytest.mark.parametrize("template_id", list(ac.TEMPLATES))
@pytest.mark.parametrize("beat", [0.4, 0.4762, 0.5, 0.5455, 0.6])
def test_timeline_hooks_in_one_second_and_cuts_every_1_to_3s(template_id, beat):
    shots = ac.plan_timeline(template_id, beat)
    assert shots[0]["seconds"] <= 1.25 and shots[0]["motion"] == "snap_zoom"
    body = shots[1:-1]
    assert body, "a template must have body cuts"
    assert all(0.9 <= s["seconds"] <= 3.01 for s in body)
    assert shots[-1]["kind"] == "end_card" and shots[-1]["seconds"] >= 2.0
    total = shots[-1]["start"] + shots[-1]["seconds"]
    assert abs(total - ac.TEMPLATES[template_id]["duration"]) < 0.01
    # constant motion and a varied shot list
    assert len({s["motion"] for s in body}) >= 3
    assert len({s["kind"] for s in shots}) >= 4
    # cuts land on the beat grid
    for s in body:
        assert abs(s["start"] / beat - round(s["start"] / beat)) < 1e-3


def test_templates_are_distinct_ad_styles():
    grades = {t["grade"] for t in ac.TEMPLATES.values()}
    music = {t["music"] for t in ac.TEMPLATES.values()}
    assert len(ac.TEMPLATES) >= 5 and len(grades) >= 4 and len(music) >= 5
    assert all(t["duration"] <= 35 for t in ac.TEMPLATES.values())


def test_captions_word_by_word_with_accent_and_cta():
    script = {"hook": "Your kettle is too hot", "lines": ["Boiling water at 100 degrees scorches Bold granules"],
              "cta": "Comment CUP and I'll send you the link"}
    shots = ac.plan_timeline("fast_cut_curiosity", 0.5)
    events = ac.caption_events(script, shots, "CUP")
    assert events[0]["style"] == "hook" and events[0]["end"] <= 1.25
    words = [e for e in events if e["style"] == "word"]
    assert words and all(len(e["text"].split()) <= 2 for e in words)
    assert any(e["accent"] for e in words)  # "100" / "Bold" get the gold accent
    assert any(e["style"] == "cta" for e in events)
    assert all(words[i]["end"] <= words[i + 1]["start"] + 1e-6 for i in range(len(words) - 1))


def test_banned_claims_never_reach_the_screen():
    piece = {"hook": "100% fresh lab tested coffee now", "frames": [{"spoken": "Zero acidity single-origin beans"}]}
    script = ac.script_from_piece(piece)
    text = " ".join([script["hook"]] + script["lines"]).lower()
    for banned in ("100%", "fresh", "lab tested", "zero acidity", "single-origin"):
        assert banned not in text


def test_archetype_label_is_not_used_as_hook():
    script = ac.script_from_piece({"chosen_hook": "certainty_check", "hook_text": "Your",
                                   "hook": "Weigh your coffee jar right now"})
    assert script["hook"].startswith("Weigh your coffee jar")


def test_learned_winner_is_preferred_and_measured_loser_retired():
    scores = {"pov_ritual": {"ratio": 2.2, "n": 4}, "myth_vs_fact": {"ratio": 0.4, "n": 5}}
    assert ac.choose_template("reel_1", 10, scores=scores, recent=[]) == "pov_ritual"
    picks = {ac.choose_template("reel_1", d, scores=scores, recent=[], taken=("pov_ritual",)) for d in range(40)}
    assert "myth_vs_fact" not in picks


def test_untested_templates_keep_being_explored():
    picks = {ac.choose_template("yt_short", d, scores={}, recent=[]) for d in range(60)}
    assert len(picks) >= 3


def test_recent_template_is_avoided_on_the_same_label():
    pick = ac.choose_template("reel_1", 5, scores={}, recent=["asmr_macro", "pov_ritual"])
    assert pick not in ("asmr_macro", "pov_ritual")


def test_assign_templates_gives_each_video_its_own_template_and_utm_link(monkeypatch):
    monkeypatch.setattr(ac, "_recent_templates", lambda label, days=2: [])
    content = {"growth_reel": {"hook": "a b"}, "reels": [{"hook": "c d"}], "yt_short": {"hook": "e f"}}
    plan = ac.assign_templates(content, 321)
    assert len(set(plan.values())) == 3
    for piece, label in ((content["growth_reel"], "growth_reel"), (content["reels"][0], "reel_1"),
                         (content["yt_short"], "yt_short")):
        link = piece["ad_cta_link"]
        assert piece["ad_template_id"] in ac.TEMPLATES
        if not piece.get("reply_link"):
            assert "utm_source=" in link and "utm_medium=" in link and "utm_campaign=ad_" in link


def test_fast_cut_day_keeps_fast_cut_on_growth_reel(monkeypatch):
    monkeypatch.setattr(ac, "_recent_templates", lambda label, days=2: [])
    content = {"growth_reel": {"hook": "a b", "growth_template_id": "fast_cut_curiosity"}, "reels": [{"hook": "c d"}]}
    plan = ac.assign_templates(content, 300)
    assert plan["growth_reel"] == "fast_cut_curiosity" and plan["reel_1"] != "fast_cut_curiosity"


def test_prompt_contract_carries_hook_cadence_and_claim_rules():
    text = ac.prompt_contract("reel_1", 319)
    assert "FIRST SECOND" in text and "never called pure" in text and "real photographed jar" in text
    assert ac.prompt_contract("carousel", 319) == ""


def test_render_until_pass_respects_the_gate_and_logs_misses(monkeypatch, tmp_path):
    monkeypatch.setenv("AD_CREATOR_VIDEO", "1")
    calls = []

    def fake_render(piece, out, **kw):
        calls.append(kw["template_id"])
        open(out, "wb").write(b"x" * 20000)
        return {"path": out, "template": kw["template_id"], "grade": "g", "duration": 18, "shots": [], "music": None}

    monkeypatch.setattr(ac, "render", fake_render)
    lessons = []
    monkeypatch.setattr(ac, "_lesson", lambda label, reason: lessons.append(reason))
    piece = {"ad_template_id": "pov_ritual"}
    out = str(tmp_path / "v.mp4")
    assert ac.render_until_pass(piece, out, label="reel_1", gate=lambda p: {"passed": False, "reasons": ["aesthetic_below_8.0:7.1"]}, max_tries=2) is None
    assert calls[0] == "pov_ritual" and len(calls) == 2 and len(lessons) == 2
    calls.clear()
    assert ac.render_until_pass(piece, out, label="reel_1", gate=lambda p: {"passed": True}, max_tries=2) == out
    assert piece["ad_template_id"] == "pov_ritual" and "video_render" in piece


def test_ad_creator_is_off_in_tests_unless_enabled(monkeypatch):
    monkeypatch.delenv("AD_CREATOR_VIDEO", raising=False)
    assert ac.enabled() is False
    assert ac.render_for({"hook": "x y"}, "reel_1_video", 1) is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_render_uses_official_cutout_and_is_vertical(tmp_path, monkeypatch):
    monkeypatch.setenv("FAST_CUT_BROLL", "0")
    from content_generator.creative import premium_cards as pc
    used = []
    real = pc.official_jar_asset
    monkeypatch.setattr(pc, "official_jar_asset", lambda sku: used.append(sku) or real(sku))
    monkeypatch.setitem(ac.TEMPLATES, "unit_short", {**ac.TEMPLATES["asmr_macro"], "duration": 5.0})
    piece = {"featured_product": "Bold", "hook": "Watch the granules melt",
             "frames": [{"spoken": "Bold is agglomerated pure coffee"}]}
    out = str(tmp_path / "ad.mp4")
    meta = ac.render(piece, out, label="reel_1", day=1, template_id="unit_short", use_broll=False)
    assert meta and os.path.getsize(out) > 10_000
    assert meta["real_jar_only"] is True and used and set(used) == {"bold"}
    import imageio.v2 as imageio
    reader = imageio.get_reader(out, format="FFMPEG")
    try:
        frame = reader.get_data(0)
        assert frame.shape[0] == 1920 and frame.shape[1] == 1080
    finally:
        reader.close()
