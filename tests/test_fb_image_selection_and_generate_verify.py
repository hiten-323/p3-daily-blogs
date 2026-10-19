"""Oct 17/18/19 regressions: FB image selection and late generate cron."""
import os
from pathlib import Path

from content_generator.publisher import facebook

ROOT = Path(__file__).resolve().parents[1]


def _touch(d, name):
    p = d / name
    p.write_bytes(b"x")
    return str(p)


def test_fb_picks_first_verified_image_not_first_glob(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    unverified = _touch(tmp_path, "ugc_day289_2026-10-17.jpg")
    verified = _touch(tmp_path, "facebook_post_day289.jpg")
    monkeypatch.setattr("content_generator.core.ist_dates.asset_date", lambda c: "2026-10-17")
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_jar_provenance",
                        lambda p: {"verified": os.path.basename(p) == "facebook_post_day289.jpg"})
    assert facebook._find_image({"day_number": 289}) == verified
    assert unverified  # still on disk, simply not chosen


def test_fb_skips_unverified_dated_render_for_verified_one(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    _touch(tmp_path, "ugc_day289_2026-10-17.jpg")
    good = _touch(tmp_path, "avatar_day289_2026-10-17.jpg")
    monkeypatch.setattr("content_generator.core.ist_dates.asset_date", lambda c: "2026-10-17")
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_jar_provenance",
                        lambda p: {"verified": p == good})
    assert facebook._find_image({"day_number": 289}) == good


def test_fb_returns_unverified_candidate_so_gate_still_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    only = _touch(tmp_path, "ugc_day289_2026-10-17.jpg")
    monkeypatch.setattr("content_generator.core.ist_dates.asset_date", lambda c: "2026-10-17")
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_jar_provenance",
                        lambda p: {"verified": False, "reason": "unregistered_image"})
    assert facebook._find_image({"day_number": 289}) == only


def test_generate_verify_accepts_already_generated_pack_but_still_validates():
    text = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert 'reason") == "already_ran_today"' in text
    assert "predates this run" in text  # stale-content guard still present
    i = text.index("already_generated = False")
    assert text.index("generation_id", i) > i  # pack validation still runs after


def test_retry_rerenders_when_on_disk_images_fail_provenance(monkeypatch):
    from content_generator.scheduler import retry_unposted
    calls = []
    monkeypatch.setattr("content_generator.publisher.instagram._find_carousel_images", lambda c: ["a.jpg"])
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_creative_suite",
                        lambda imgs: (False, ["a.jpg: unregistered_image"]))
    monkeypatch.setattr("content_generator.scheduler.daily._do_generate_images",
                        lambda c, d: calls.append(d) or {"carousel": ["a.jpg"]})
    assert retry_unposted.ensure_ig_images({"day_number": 290}) is True
    assert calls == [290]


def test_retry_keeps_verified_images(monkeypatch):
    from content_generator.scheduler import retry_unposted
    monkeypatch.setattr("content_generator.publisher.instagram._find_carousel_images", lambda c: ["a.jpg"])
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_creative_suite", lambda imgs: (True, []))
    monkeypatch.setattr("content_generator.scheduler.daily._do_generate_images",
                        lambda c, d: (_ for _ in ()).throw(AssertionError("must not re-render")))
    assert retry_unposted.ensure_ig_images({"day_number": 290}) is True


def test_retry_persist_keeps_rerendered_creatives_and_registry():
    text = (ROOT / ".github/workflows/retry-unposted.yml").read_text(encoding="utf-8")
    i = text.index('mkdir -p "$PERSIST/creative"')
    assert i < text.index("git reset -q --hard HEAD && git clean -qfd output/creative")
    assert "provenance registry merged" in text
