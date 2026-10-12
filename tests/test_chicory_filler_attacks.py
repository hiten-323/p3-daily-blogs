"""Chicory-filler attacks fail on an Ultra Blend day and repair to 70/30."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hidden_chicory_fillers_fail_product_truth_on_ultra_blend_day():
    from content_generator.core.product_truth import product_truth_findings

    spoken = "You might be drinking hidden chicory fillers."
    flagged = product_truth_findings(spoken, featured="Ultra Blend")
    assert flagged
    assert any("anti-chicory" in item["reason"] for item in flagged)
    for phrase in (
        "hidden chicory fillers",
        "chicory fillers",
        "chicory filler",
        "chicory root fillers",
        "hidden chicory roots",
    ):
        assert product_truth_findings(phrase, featured="Ultra Blend"), phrase
    assert product_truth_findings("Ultra Blend is 70% coffee and 30% chicory.") == []
    assert product_truth_findings(spoken, featured="Bold") == []
    joined = (
        "You might be drinking hidden chicory fillers. "
        "Ultra Blend is 70% coffee and 30% chicory."
    )
    assert product_truth_findings(joined)


def test_yt_short_hidden_chicory_fillers_are_repaired_to_seventy_thirty():
    from content_generator.core.product_truth import repair_content
    from scripts.repair_chicory_day import remaining_findings

    reveal = (
        "Purity Beans Ultra Blend combines 70% rich coffee with 30% chicory "
        "for a smooth everyday cup."
    )
    payload = {
        "date": "2026-10-12",
        "featured_product": "Ultra Blend",
        "yt_short": {
            "product": "Ultra Blend",
            "scenes": [
                {
                    "spoken": (
                        "Why does your morning coffee turn bitter before noon? "
                        "You might be drinking hidden chicory fillers."
                    ),
                },
                {"spoken": "Commercial jars often hide behind vague labels."},
                {"spoken": reveal},
            ],
        },
    }
    assert remaining_findings(payload)
    repaired = repair_content(payload)
    assert remaining_findings(repaired) == []
    scene0 = repaired["yt_short"]["scenes"][0]["spoken"]
    assert "hidden chicory" not in scene0.lower()
    assert "filler" not in scene0.lower()
    assert "70% coffee" in scene0
    assert "30% chicory" in scene0
    assert repaired["yt_short"]["scenes"][2]["spoken"] == reveal


def test_negated_zero_chicory_is_not_rewritten_to_the_blend_ratio():
    from content_generator.core.product_truth import repair_text

    denial = "Do not call Ultra Blend zero chicory."
    assert repair_text(denial, chicory_scope=True) == denial
    never = "Notice that Ultra Blend is never called zero chicory or no chicory."
    assert repair_text(never, chicory_scope=True) == never
    assert (
        repair_text("Ultra Blend is zero chicory.", chicory_scope=True)
        == "Ultra Blend is 30% chicory."
    )


def test_committed_2026_10_12_yt_short_scene_is_honest():
    from scripts.repair_chicory_day import remaining_findings

    data = json.loads((ROOT / "output" / "content_2026-10-12.json").read_text(encoding="utf-8"))
    spoken = data["yt_short"]["scenes"][0]["spoken"]
    assert spoken == (
        "Why does your morning coffee turn bitter before noon? "
        "Ultra Blend is 70% coffee and 30% chicory."
    )
    reveal = data["yt_short"]["scenes"][2]["spoken"]
    assert "70%" in reveal and "30% chicory" in reveal
    blob = json.dumps(data).lower()
    assert "hidden chicory" not in blob
    assert "chicory filler" not in blob
    assert remaining_findings(data) == []


def test_repair_script_documents_2026_10_12_write():
    text = (ROOT / "scripts" / "repair_chicory_day.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "repair-chicory-day.yml").read_text(encoding="utf-8")
    assert "python scripts/repair_chicory_day.py --date 2026-10-12 --dry-run" in text
    assert "python scripts/repair_chicory_day.py --date 2026-10-12 --write" in text
    assert "does not publish" in text.lower()
    assert "morning" in text.lower() and "evening" in text.lower()
    assert "python scripts/repair_chicory_day.py --date 2026-10-12 --write" in workflow
    assert "schedule:" not in workflow
