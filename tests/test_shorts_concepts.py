import datetime as dt

import numpy as np
import pytest

from content_generator.creative import shorts_concepts as scn
from content_generator.creative import render_claims as rc
from content_generator.creative.concept_backdrop import ConceptBackdrop, camera, tone_palette
from content_generator.creative import premium_cards as pc


def _simulate(days=21, start=dt.date(2026, 10, 22)):
    hist = []
    for i in range(days):
        ds = (start + dt.timedelta(days=i)).isoformat()
        for fmt in ("short", "reel"):
            ch = scn.pick(ds, fmt, sku="bold", history=hist)
            hist.append({k: ch[k] for k in ("date", "format", "concept", "motion", "layout", "transition", "hook")})
    return hist


def test_library_size_and_fields():
    assert len(scn.CONCEPTS) >= 12
    assert len({c["id"] for c in scn.CONCEPTS}) == len(scn.CONCEPTS)
    assert len({c["scene"] for c in scn.CONCEPTS}) >= 12
    for c in scn.CONCEPTS:
        assert c["motions"] and set(c["motions"]) <= set(scn.MOTIONS)
        assert c["transition"] in scn.TRANSITIONS and c["music"] in scn.MUSIC
        assert "jar" not in c["ai_prompt"].lower()
    assert len(scn.LAYOUTS) > scn.ROTATION_DAYS and len(scn.MOTIONS) > scn.ROTATION_DAYS


@pytest.mark.parametrize("fmt", ["short", "reel"])
def test_no_repeat_within_7_days(fmt):
    hist = _simulate()
    rows = [r for r in hist if r["format"] == fmt]
    for i, r in enumerate(rows):
        for prev in rows[max(0, i - 6):i]:
            for f in ("concept", "motion", "layout"):
                assert r[f] != prev[f], (f, r, prev)


def test_short_and_reel_same_day_differ():
    hist = _simulate()
    by_day = {}
    for r in hist:
        by_day.setdefault(r["date"], []).append(r)
    for ds, (a, b) in by_day.items():
        for f in ("concept", "motion", "layout"):
            assert a[f] != b[f], (ds, f)


def test_hooks_vary_and_claim_safe():
    hist = _simulate()
    shorts = [r["hook"] for r in hist if r["format"] == "short"]
    assert len(set(shorts[:7])) == 7
    for c in scn.CONCEPTS:
        for h in c["hooks"]:
            assert scn.hook_is_claim_safe(h), h
            assert rc.guard(h, "ultra") == h  # never rewritten for Ultra Blend (no 'pure'/100%)


def test_record_and_rerender_same_day(tmp_path):
    p = str(tmp_path / "h.json")
    ch = scn.pick("2026-10-22", "short", path=p)
    scn.record(ch, phashes=["0" * 16] * 3, path=p)
    again = scn.pick("2026-10-22", "short", path=p)
    assert again["concept"] == ch["concept"]  # re-render same day keeps its own slot
    reel = scn.pick("2026-10-22", "reel", path=p)
    assert reel["concept"] != ch["concept"]
    assert len(scn.load_history(p)) == 1


def test_phash_distance():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 255, (96, 54, 3), dtype=np.uint8)
    assert scn.hamming(scn.phash(a), scn.phash(a.copy())) == 0
    b = rng.integers(0, 255, (96, 54, 3), dtype=np.uint8)
    assert scn.hamming(scn.phash(a), scn.phash(b)) > scn.PHASH_MIN_DISTANCE


def test_variety_gate_rejects_lookalike(monkeypatch):
    fr = np.tile(np.linspace(0, 255, 54, dtype=np.uint8)[None, :, None], (96, 1, 3))
    monkeypatch.setattr(scn, "key_frames", lambda p, fractions=None: [fr, fr, fr])
    h = scn.phash(fr)
    hist = [{"date": "2026-10-20", "format": "short", "concept": "steam_backlight", "phash": [h, h, h]}]
    ch = {"date": "2026-10-22", "format": "short", "concept": "crema_swirl"}
    v = scn.variety_check("x.mp4", ch, history=hist)
    assert not v["passed"] and any(r.startswith("too_similar_to") for r in v["reasons"])
    ch2 = {"date": "2026-10-22", "format": "short", "concept": "steam_backlight"}
    assert any(r.startswith("concept_repeat") for r in scn.variety_check("x.mp4", ch2, history=hist)["reasons"])
    old = [dict(hist[0], date="2026-10-01")]
    assert scn.variety_check("x.mp4", ch, history=old)["passed"]


def test_every_scene_moves_and_differs():
    pal = pc.PALETTES["bold"][0]
    hashes = {}
    for c in scn.CONCEPTS:
        bd = ConceptBackdrop(tone_palette(pal, c["tone"]), 3, c["scene"], c["motions"][0], (0.3, 0.3, 0.7, 0.4), 0.75)
        a = np.asarray(bd.frame(0.0, 10, (108, 192)).convert("RGB"), np.float32)
        b = np.asarray(bd.frame(9.5, 10, (108, 192)).convert("RGB"), np.float32)
        assert np.abs(a - b).mean() > 3.0, c["id"]
        hashes[c["id"]] = scn.phash(b.astype(np.uint8))
    assert len(set(hashes.values())) == len(hashes)


def test_camera_motions_distinct():
    sigs = {m: tuple(round(v, 2) for v in camera(m, 0.8)[:4]) for m in scn.MOTIONS}
    assert len(set(sigs.values())) == len(sigs)
