"""Process-rule rewrites must clear the gate, and a skipped gate must be regenerated.

2026-10-22 threads was SKIPPED on product_truth with no retry. 2026-10-21 evening
Facebook failed that same gate four times after freeze-drying was tied to Bold.
2026-10-22 morning Facebook had native copy nested where the scorer never measured
it, so the 8.0 editorial gate had nothing that could pass.
"""
from __future__ import annotations


def _reasons(text: str, featured: str | None = None) -> list[str]:
    from content_generator.core.product_truth import product_truth_findings

    return [item["reason"] for item in product_truth_findings(text, featured=featured)]


def test_bold_day_freeze_dried_line_is_rewritten_until_compliant():
    from content_generator.core.process_match import align_process_piece

    piece = {
        "body": (
            "Read the jar: Purica is pure Arabica freeze-dried instant coffee "
            "with zero chicory. Purity Beans. https://p3online.in"
        ),
        "featured_product": "Bold",
    }
    align_process_piece(piece, "Bold")
    assert _reasons(piece["body"], featured="Bold") == []
    assert "bold is freeze" not in piece["body"].lower()
    assert "agglomerat" in piece["body"].lower()


def test_ultra_blend_loses_a_stray_process_claim():
    from content_generator.core.process_match import align_process_piece

    piece = {
        "body": "Freeze-drying is how this cup is made. The jar is on the shelf.",
        "featured_product": "Ultra Blend",
    }
    align_process_piece(piece, "Ultra Blend")
    assert _reasons(piece["body"], featured="Ultra Blend") == []
    assert "freeze" not in piece["body"].lower()
    assert "70% coffee" in piece["body"]


def test_mixed_process_list_does_not_call_purista_agglomerated():
    from content_generator.core.process_match import align_process_piece

    piece = {
        "body": (
            "Bold, Purista, and Purica by Purity Beans are pure coffee with zero chicory, "
            "agglomerated or freeze-dried, in glass jars. Ultra Blend by Purity Beans is "
            "a smooth 70% coffee and 30% chicory blend. https://p3online.in"
        ),
    }
    align_process_piece(piece, "Purista")
    assert _reasons(piece["body"], featured="Purista") == []
    assert "purista is agglomerat" not in piece["body"].lower()


def test_bold_granule_process_is_rewritten_to_agglomerated():
    from content_generator.core.process_match import align_process_piece

    piece = {"caption": "Bold is made into granules. Purity Beans. https://p3online.in"}
    align_process_piece(piece, "Bold")
    assert _reasons(piece["caption"], featured="Bold") == []
    assert "granule" not in piece["caption"].lower()


def test_valid_comparison_stays_a_comparison():
    from content_generator.core.process_match import align_process_piece

    piece = {"body": "Purica is freeze-dried pure Arabica. Bold is agglomerated pure coffee."}
    align_process_piece(piece, "Bold")
    assert "freeze-dried" in piece["body"].lower()
    assert "agglomerated" in piece["body"].lower()
    assert _reasons(piece["body"], featured="Bold") == []


def test_prepublish_skip_is_a_due_retry(tmp_path, monkeypatch):
    from content_generator.core.ist_dates import today_ist
    from content_generator.publisher import publishing_ledger as ledger

    monkeypatch.setattr(ledger, "_PATH", tmp_path / "ledger.json")
    today = today_ist().isoformat()
    content = {"date": today, "generation_id": "threads-gate"}
    ticket = ledger.begin_attempt(content, "threads", "generate", 294)
    record = ledger.finish_attempt(ticket, {
        "success": False,
        "attempted": False,
        "skipped": True,
        "error": "prepublish_gate:product_truth_failed",
    })
    assert record["status"] == "FAILED"
    assert record["next_retry_at"]
    assert {"content_date": today, "slot": "generate"} in ledger.due_retry_groups()
    assert ledger.begin_attempt(content, "threads", "generate", 294)["allowed"] is True

    plain = {"date": today, "generation_id": "threads-plain-skip"}
    skipped = ledger.finish_attempt(
        ledger.begin_attempt(plain, "threads", "generate", 294),
        {"success": False, "attempted": False, "skipped": True, "error": "no_content"},
    )
    assert skipped["status"] == "SKIPPED"
    assert skipped["next_retry_at"] is None


def test_skipped_and_failed_gate_holds_are_queued_for_regen():
    from content_generator.scheduler.retry_unposted import labels_to_regen

    records = [
        {
            "slot": "generate",
            "platform": "threads",
            "status": "SKIPPED",
            "error": "prepublish_gate:product_truth_failed",
        },
        {
            "slot": "morning",
            "platform": "facebook",
            "status": "FAILED",
            "error": "prepublish_gate:native_asset_missing_passing_editorial_score",
        },
    ]
    queued = labels_to_regen(["threads", "facebook", "linkedin"], approved={}, records=records)
    assert "threads_post" in queued
    assert "facebook_post" in queued
    assert "linkedin_post" not in queued

    configured = [{
        "slot": "generate", "platform": "threads", "status": "SKIPPED", "error": "not_configured",
    }]
    assert labels_to_regen(["threads"], approved={}, records=configured) == []


def _editorial_score(overall: float) -> dict:
    return {
        "overall": overall,
        "shareability": overall,
        "saveability": overall,
        "emotion_pull": overall,
        "hook_strength": overall,
        "brand_clarity": overall,
        "feedback": "measured",
    }


def test_nested_facebook_copy_is_scored_until_it_passes(monkeypatch):
    from content_generator.agents import editorial
    from content_generator.core.editorial_engine import get_current_pass_score
    from content_generator.core.fallback_ladder import PASS_FLOOR
    from content_generator.core.viral_gate import PASS_MARK
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    assert PASS_FLOOR == 8.0
    assert PASS_MARK == 8.0
    assert get_current_pass_score() == 8.0

    seen = []

    def review(piece, label="content"):
        seen.append(str(piece.get("body") or piece.get("hook") or ""))
        overall = 7.2 if len(seen) == 1 else 8.6
        return _editorial_score(overall)

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(editorial, "review_content", review)
    monkeypatch.setattr(daily, "_growth_gate_reason", lambda *a, **k: "")
    monkeypatch.setattr("content_generator.core.viral_gate.enabled", lambda: False)
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "2")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "2")

    content = {
        "day_number": 294,
        "featured_product": "Purista",
        "facebook_post": {
            "featured_product": "ultra_blend_100g",
            "primary_cta": "Shop https://p3online.in",
            "comment_trigger": "Comment MILK or BLACK.",
            "editorial_subscores": {
                "brand_clarity": 9.5,
                "hook_strength": 9.0,
                "saveability": 9.0,
                "shareability": 9.0,
            },
            "facebook_post": {
                "body": (
                    "Bold, Purista, and Purica by Purity Beans are pure coffee with zero chicory, "
                    "agglomerated or freeze-dried, in glass jars. Ultra Blend by Purity Beans is a "
                    "smooth 70% coffee and 30% chicory blend. https://p3online.in"
                ),
            },
        },
    }
    daily._do_editorial(content, only={"facebook_post"})
    piece = content["facebook_post"]
    assert piece.get("hook") and piece.get("body")
    assert _reasons(piece["body"], featured="Purista") == []
    assert len(seen) >= 2
    assert piece["editorial_score"]["overall"] == 8.6
    assert piece["editorial_score"]["overall"] >= get_current_pass_score()
    assert piece["editorial_subscores"]["shareability"] == 9.0


def test_stale_pass_is_replaced_after_a_process_rewrite(monkeypatch):
    from content_generator.agents import editorial
    from content_generator.providers import llm_router
    from content_generator.scheduler import daily

    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setattr(editorial, "review_content", lambda piece, label="content": _editorial_score(8.4))
    monkeypatch.setattr(daily, "_growth_gate_reason", lambda *a, **k: "")
    monkeypatch.setattr("content_generator.core.viral_gate.enabled", lambda: False)
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    monkeypatch.setenv("QUALITY_MAX_REGEN", "1")
    monkeypatch.setenv("QUALITY_LADDER_MAX", "1")

    content = {
        "day_number": 293,
        "featured_product": "Bold",
        "facebook_post": {
            "hook": "Why the morning cup tastes burnt",
            "body": (
                "Read the jar: Purica is pure Arabica freeze-dried instant coffee "
                "with zero chicory. Purity Beans. https://p3online.in"
            ),
            "cta": "Follow @purepantryprovisions",
            "comment_trigger": "Comment the first ingredient.",
            "featured_product": "Bold",
            "editorial_score": _editorial_score(9.0),
        },
    }
    daily._do_editorial(content, only={"facebook_post"})
    piece = content["facebook_post"]
    assert _reasons(piece["body"], featured="Bold") == []
    assert piece["editorial_score"]["overall"] == 8.4
