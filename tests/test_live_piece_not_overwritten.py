"""Already-live pieces must not be overwritten by later regeneration."""
from __future__ import annotations

import json
from pathlib import Path

from content_generator.core import live_piece_guard as guard
from content_generator.pipeline.generator import save_content


LIVE_PIECE = {
    "type": "linkedin_post",
    "hook": "We almost launched with the wrong label.",
    "body": "The posted body that actually went live.",
    "cta": "Comment DISTRIBUTION for the trade sheet.",
    "hashtags": "#PurityBeans #FMCG #D2CIndia",
    "editorial_score": {"overall": 9.3},
    "viral_potential": {"overall": 9.2, "passed": True},
}


def test_live_piece_not_overwritten(tmp_path, monkeypatch):
    """Ledger VERIFIED_LIVE for LinkedIn → save_content leaves the posted piece intact."""
    out = tmp_path / "output"
    out.mkdir()
    ledger = tmp_path / "publishing_ledger.json"
    monkeypatch.setenv("PUBLISH_LEDGER_PATH", str(ledger))
    # Re-bind the module path after env change.
    import content_generator.publisher.publishing_ledger as pl
    monkeypatch.setattr(pl, "_PATH", Path(ledger))

    snapshot = {"label": "linkedin_post", "piece": dict(LIVE_PIECE), "source": "test"}
    pl._save({
        "records": {
            "2026-11-27|generate|linkedin|pb_live": {
                "content_date": "2026-11-27",
                "platform": "linkedin",
                "slot": "generate",
                "status": "VERIFIED_LIVE",
                "posted_snapshot": snapshot,
            }
        }
    })

    content = {
        "date": "2026-11-27",
        "day_number": 330,
        "linkedin_post": {
            "type": "linkedin_post",
            "hook": "When a retail buyer flips our coffee jar over, this is the exact detail they look for first.",
            "body": "A later regeneration that must not replace the live post.",
            "cta": "Follow @purepantryprovisions",
            "hashtags": "#Too #Many #Tags",
            "held": True,
            "hold_reason": "FALLBACK LADDER EXHAUSTED",
        },
    }

    path = save_content(content, output_dir=str(out))
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    live = {k: LIVE_PIECE[k] for k in ("hook", "body", "cta", "hashtags")}
    got = {k: saved["linkedin_post"][k] for k in ("hook", "body", "cta", "hashtags")}
    assert got == live
    assert saved["linkedin_post"].get("held") is not True


def test_mark_fresh_skips_live_linkedin(tmp_path, monkeypatch):
    content = {
        "date": "2026-11-27",
        "linkedin_post": dict(LIVE_PIECE),
        "_posted_snapshots": {"linkedin_post": {"label": "linkedin_post", "piece": dict(LIVE_PIECE)}},
    }
    from content_generator.scheduler.retry_unposted import mark_fresh
    original = json.dumps(content["linkedin_post"], sort_keys=True)
    mark_fresh(content, ["linkedin_post", "threads_post"])
    assert json.dumps(content["linkedin_post"], sort_keys=True) == original
    assert content["linkedin_post"].get("needs_regen") is not True


def test_labels_to_regen_excludes_verified_live():
    records = [{
        "slot": "generate",
        "platform": "linkedin",
        "status": "VERIFIED_LIVE",
        "asset": "",
        "error": "",
    }]
    from content_generator.scheduler.retry_unposted import labels_to_regen
    queued = labels_to_regen(["linkedin", "threads"], approved={}, records=records)
    assert "linkedin_post" not in queued
