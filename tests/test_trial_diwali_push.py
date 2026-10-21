"""Organic trial and Diwali push: window, exclusion list, claims, and publish gates."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from content_generator.campaigns import trial_diwali_push as push
from content_generator.core.viral_gate import honesty_issues
from content_generator.creative import shorts_concepts as scn
from content_generator.creative.shorts_concepts import PHASH_MIN_DISTANCE
from content_generator.creative.visual_gate import AESTHETIC_PASS, MIN_BG_MOTION

START = dt.date(2026, 10, 21)
END = dt.date(2026, 11, 20)
ALLOWED = {"bold", "purista", "purica", "gourmet_duo_mini"}
UTM = "utm_source=instagram&utm_medium=organic&utm_campaign=trial_diwali_push"
HANDLES = {
    "bold": "purity-beans-bold-instant-coffee",
    "purista": "purity-beans-purista-gourmet-instant-coffee-granules",
    "purica": "purity-beans-purica-gourmet-instant-coffee-granules",
    "gourmet_duo_mini": "gourmet-duo-mini",
}


def _day(offset: int) -> dt.date:
    return START + dt.timedelta(days=offset)


def _spoken(piece: dict) -> str:
    frames = " ".join(f"{fr.get('on', '')} {fr.get('sub', '')}" for fr in piece["frames"])
    return piece["caption"] + "\n" + frames


@pytest.fixture
def prov(tmp_path, monkeypatch):
    import content_generator.creative.jar_provenance as jp
    saved = dict(jp._MEMORY_REGISTRY)
    monkeypatch.setattr(jp, "_PROVENANCE_FILE", str(tmp_path / "jar_provenance.json"))
    monkeypatch.setattr(jp, "_OUT_DIR", str(tmp_path))
    jp._MEMORY_REGISTRY.clear()
    yield jp
    jp._MEMORY_REGISTRY.clear()
    jp._MEMORY_REGISTRY.update(saved)


def test_window_and_diwali_angle():
    assert push.active(_day(-1)) is False
    assert push.active(END) is True
    assert push.active(END + dt.timedelta(days=1)) is False
    assert push.diwali_angle(dt.date(2026, 11, 8)) is True
    assert push.diwali_angle(dt.date(2026, 11, 9)) is False
    assert push.attach({}, _day(-1))["sales_push"]["reason"] == "outside_window"


def test_rotation_only_promotes_the_four_allowed_skus():
    seen = []
    for offset in range(31):
        day = _day(offset)
        offer = push.offer_for(day)
        assert offer is not None
        assert offer["slug"] in ALLOWED
        assert offer["slug"] not in {"prima", "ultra_blend", "variety_box", "gourmet_duo"}
        if offset % 2 == 0:
            assert offer["role"] == "trial"
            assert offer["slug"] == ("bold", "purista", "purica")[(offset // 2) % 3]
        else:
            assert offer["role"] == "gift"
            assert offer["slug"] == "gourmet_duo_mini"
        seen.append(offer["slug"])
    assert seen[0] == "bold"
    assert set(seen) == ALLOWED


def test_prices_match_the_shopify_snapshot():
    prices = {push.offer_for(_day(i))["slug"]: push.offer_for(_day(i))["price"] for i in range(6)}
    assert prices["bold"] == 239
    assert prices["purista"] == 319
    assert prices["purica"] == 329
    assert prices["gourmet_duo_mini"] == 570


def test_captions_pass_claim_gates_and_end_on_the_cta():
    reel = push.build_piece(START, "reel")
    story = push.build_piece(_day(1), "story")
    assert reel["caption"].splitlines()[-1] == push.REEL_CTA
    assert story["caption"].splitlines()[-1] == push.STORY_CTA
    assert f"https://p3online.in/products/{HANDLES['bold']}?{UTM}" in reel["caption"]
    assert f"https://p3online.in/products/{HANDLES['gourmet_duo_mini']}?{UTM}" in story["caption"]
    assert "Trial jars from Rs239." in reel["caption"]
    assert "Use code FREESHIP." in reel["caption"]
    assert "Use code BUNDLE10." in reel["caption"]
    assert "order by" not in reel["caption"].lower()
    assert "Diwali" in story["caption"]
    assert "Order by 2 Nov." in story["caption"]
    assert "Use code FREESHIP." in story["caption"]
    assert "Use code BUNDLE10." in story["caption"]
    assert "Order by 2 Nov." in push.build_piece(_day(11), "story")["caption"]
    nov3 = push.build_piece(_day(13), "story")
    assert "Diwali" in nov3["caption"]
    assert "order by" not in nov3["caption"].lower()
    assert "Use code FREESHIP." in nov3["caption"]
    assert "Diwali" not in push.build_piece(dt.date(2026, 11, 9), "story")["caption"]
    assert "order by" not in push.build_piece(dt.date(2026, 11, 9), "story")["caption"].lower()
    assert "Diwali" not in push.build_piece(dt.date(2026, 11, 8), "reel")["caption"]
    assert "order by" not in push.build_piece(dt.date(2026, 11, 2), "reel")["caption"].lower()
    for piece in (reel, story, nov3, push.build_piece(dt.date(2026, 11, 9), "reel")):
        text = _spoken(piece)
        assert push.copy_problems(text, piece["slug"], piece["date"]) == []
        low = text.lower()
        for banned in (
            "100%", "100 percent", "fresh", "lab tested", "lab-tested",
            "zero acidity", "per cup", "66 cups", "limited stock",
            "countdown", "variety box", "ultra blend", "prima", "november",
            "free shipping", "10%", "on bundles",
        ):
            assert banned not in low
        if piece["slug"] != "gourmet_duo_mini" or piece["date"] > "2026-11-02":
            assert "order by" not in low
        else:
            assert low.count("order by") == 1
            assert "order by 2 nov" in low
        assert "only " not in low or "only if" in low


def test_exclude_list_is_configurable(tmp_path, monkeypatch):
    cfg = json.loads(Path(push.CONFIG_PATH).read_text(encoding="utf-8"))
    cfg["promote"] = [row for row in cfg["promote"] if row["slug"] not in {"bold", "purista"}]
    cfg["promote"].append({"slug": "ultra_blend", "grams": 50, "role": "trial", "verified_price": 209})
    cfg["exclude"] = list(cfg["exclude"]) + ["ultra_blend"]
    path = tmp_path / "push.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(push, "CONFIG_PATH", path)
    loaded = push.load_config()
    assert push.is_excluded("ultra_blend", loaded)
    assert push.is_excluded("variety-box", loaded)
    assert push.is_excluded("gourmet-duo", loaded)
    assert push.resolve_asset("ultra_blend", loaded) is None
    for offset in range(8):
        offer = push.offer_for(_day(offset), loaded)
        assert offer["slug"] in {"purica", "gourmet_duo_mini"}


def test_price_mismatch_drops_the_sku(tmp_path, monkeypatch):
    cfg = json.loads(Path(push.CONFIG_PATH).read_text(encoding="utf-8"))
    for row in cfg["promote"]:
        if row["slug"] == "bold":
            row["verified_price"] = 1
    path = tmp_path / "push.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(push, "CONFIG_PATH", path)
    loaded = push.load_config()
    assert push.offer_for(START, loaded)["slug"] == "purista"


def test_assets_resolve_only_for_promoted_real_files():
    bold = push.resolve_asset("bold")
    assert bold and bold.endswith("bold_50g_cutout_front.png")
    mini = push.resolve_asset("gourmet_duo_mini")
    assert mini and mini.endswith("gourmet_duo_mini_pack_cutout.png")
    for slug in ("ultra_blend", "variety_box", "prima", "gourmet_duo"):
        assert push.resolve_asset(slug) is None


def test_register_source_verifies_the_pack(prov):
    path = push.resolve_asset("gourmet_duo_mini")
    entry = push.register_source(path)
    assert entry["asset_real_jar_verified"] is True
    assert prov.verify_jar_provenance(path)["verified"] is True


def test_render_uses_distinct_formats_and_holds_on_failure(prov, tmp_path, monkeypatch):
    content = {}
    push.attach(content, START)
    calls = []

    def _fake(sku, beats, out_path, **kwargs):
        calls.append({"sku": sku, "out": out_path, **kwargs})
        if kwargs.get("format_type") == "push_story":
            return None
        poster = tmp_path / "poster.jpg"
        poster.write_bytes(Path(kwargs["jar_source"]).read_bytes())
        return {
            "visual_gate": {"passed": True},
            "variety_gate": {"passed": True},
            "poster": str(poster),
            "path": out_path,
        }

    monkeypatch.setattr(
        "content_generator.creative.cinematic_motion.render_cinematic_until_pass",
        _fake,
    )
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    rendered = push.render_assets(content, 1, START)
    assert [c["format_type"] for c in calls] == ["push_reel", "push_story"]
    assert all(c["concepts"] is True for c in calls)
    assert calls[0]["jar_source"].endswith("bold_50g_cutout_front.png")
    assert calls[0]["end_cta"] == push.REEL_CTA
    assert "reel" in rendered
    assert content["sales_push"]["story"]["held"] == "visual_or_variety_gate"
    assert push.render_assets({}, 1, START) == {}


def test_publish_skips_until_gates_and_provenance_pass(prov, monkeypatch):
    content = {}
    push.attach(content, START)
    calls = []

    def _ledger(platform, _content, _slot, _day, publish):
        calls.append(platform)
        return publish()

    monkeypatch.setattr(
        "content_generator.publisher.publishing_ledger.publish_with_ledger",
        _ledger,
    )
    assert push.publish_for_slot(content, "evening", 1)["reason"] == "not_rendered"
    assert calls == []

    piece = content["sales_push"]["reel"]
    poster = push.resolve_asset("bold")
    push.register_source(poster)
    prov.record_jar_provenance(poster, jar_asset_id=poster, render_source="cinematic_real_jar")
    piece.update({
        "video_path": poster,
        "poster_path": poster,
        "visual_gate": {"passed": True},
        "variety_gate": {"passed": True},
    })
    posted = {}

    def _post(video, caption):
        posted["video"] = video
        posted["caption"] = caption
        return {"success": True, "media_id": "1"}

    monkeypatch.setattr(
        "content_generator.publisher.instagram._post_reel_direct_binary",
        _post,
    )
    result = push.publish_for_slot(content, "evening", 1)
    assert result["success"] is True
    assert calls == ["instagram_sales_reel"]
    assert posted["caption"].endswith(push.REEL_CTA)


def test_limited_stock_phrase_stays_blocked():
    assert "fabricated urgency" in honesty_issues({"caption": "Limited stock."})
    cfg = push.load_config()
    cfg = {**cfg, "limited_stock_copy": True}
    offer = push.offer_for(_day(1), cfg)
    body = push._body(offer, cfg)
    assert push._stock_line(offer, cfg, body) == ""
    caption = push.build_piece(_day(1), "story", cfg)["caption"].lower()
    assert "limited stock" not in caption
    assert "countdown" not in caption


def test_confirmed_codes_and_deadline_match_the_honesty_gate():
    cfg = push.load_config()
    assert [row["code"] for row in cfg["codes"]] == ["FREESHIP", "BUNDLE10"]
    assert "benefit" not in json.dumps(cfg["codes"]).lower()
    assert cfg["order_by"]["through"] == "2026-11-02"
    assert cfg["order_by"]["line"] == "Order by 2 Nov"
    assert cfg["order_by"]["slug"] == "gourmet_duo_mini"
    open_day = {"date": "2026-11-02"}
    assert honesty_issues({**open_day, "caption": "Use code FREESHIP. Use code BUNDLE10."}) == []
    assert honesty_issues({**open_day, "caption": "Order by 2 Nov."}) == []
    assert "fabricated urgency" in honesty_issues({"date": "2026-11-03", "caption": "Order by 2 Nov."})
    assert "fabricated urgency" in honesty_issues({**open_day, "caption": "Order by tomorrow."})
    assert "fabricated urgency" in honesty_issues({**open_day, "caption": "Order by 2 Nov. Hurry, limited stock."})


def test_existing_gates_are_unchanged():
    assert AESTHETIC_PASS == 8.0
    assert MIN_BG_MOTION == 12.0
    assert PHASH_MIN_DISTANCE == 12


def test_pipeline_hooks_are_wired():
    daily = Path("content_generator/scheduler/daily.py").read_text(encoding="utf-8")
    slots = Path("content_generator/scheduler/slots.py").read_text(encoding="utf-8")
    assert "attach(content, asset_date(content))" in daily
    assert "render_assets(content, day_number, asset_date(content))" in daily
    assert "publish_for_slot(content, slot, day)" in slots


def test_push_reel_does_not_reuse_the_daily_reel_concept():
    assert scn.format_key("push_reel") != "reel"
    reel = scn.pick("2026-10-21", "reel", sku="bold", history=[])
    push_reel = scn.pick("2026-10-21", "push_reel", sku="bold", history=[reel])
    assert push_reel["format"] == "push_reel"
    assert push_reel["concept"] != reel["concept"]
