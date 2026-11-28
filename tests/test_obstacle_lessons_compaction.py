import json
import pytest
from pathlib import Path
from content_generator.core import obstacle_lessons


def test_lessons_compaction_standardizes_ids_and_preserves_samples(monkeypatch, tmp_path):
    test_file = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(test_file))

    for i in range(50):
        obstacle_lessons.record(
            "linkedin",
            "linkedin_post",
            "generation",
            "viral",
            f"Viral score 7.2 < 9.0: hook lacks curiosity gap variant {i}",
            feedback=f"LLM viral judge note {i}: hook is too generic",
            count=1,
            first_seen="2026-11-20",
            last_seen="2026-11-28",
        )

    data = json.loads(test_file.read_text(encoding="utf-8"))
    assert len(data["lessons"]) == 1
    row = data["lessons"][0]
    assert row["count"] == 50
    assert row["id"] == "linkedin|viral|generic_hook"
    assert row["code"] == "generic_hook"
    assert len(row["recent_samples"]) <= 3


def test_compact_lessons_caps_file_at_500_rows():
    raw_lessons = []
    for i in range(600):
        raw_lessons.append({
            "platform": "linkedin",
            "gate": "banned_claim",
            "reason": f"banned claim variant {i} 100% {i}",
            "code": f"banned_{i}",
            "count": 1,
            "first_seen": "2026-11-01",
            "last_seen": f"2026-11-{(i % 28) + 1:02d}",
        })

    compacted = obstacle_lessons.compact_lessons({"version": 1, "lessons": raw_lessons})
    assert len(compacted["lessons"]) == 500


def test_prompt_block_deduplicates_and_surfaces_top_lessons(monkeypatch, tmp_path):
    test_file = tmp_path / "obstacle_lessons.json"
    monkeypatch.setenv("OBSTACLE_LESSONS_PATH", str(test_file))

    sample_lessons = {
        "version": 1,
        "lessons": [
            {
                "id": "linkedin|banned_claim|banned_claim:100%",
                "platform": "linkedin",
                "gate": "banned_claim",
                "code": "banned_claim:100%",
                "reason": "Contains banned claim wording: 100%",
                "count": 12,
                "last_seen": "2026-11-28",
            },
            {
                "id": "linkedin|banned_claim|banned_claim:100%",
                "platform": "linkedin",
                "gate": "banned_claim",
                "code": "banned_claim:100%",
                "reason": "Contains banned claim wording: 100%",
                "count": 12,
                "last_seen": "2026-11-28",
            },
            {
                "id": "linkedin|editorial|generic_hook",
                "platform": "linkedin",
                "gate": "editorial",
                "code": "generic_hook",
                "reason": "generic_hook",
                "feedback": "Hook fails 2s scroll-stop",
                "count": 610,
                "last_seen": "2026-11-28",
            },
            {
                "id": "linkedin|viral|llm_viral",
                "platform": "linkedin",
                "gate": "viral",
                "code": "llm_viral",
                "reason": "llm_viral",
                "feedback": "Weak emotional pull",
                "count": 205,
                "last_seen": "2026-11-28",
            },
        ]
    }
    obstacle_lessons._save(test_file, sample_lessons)

    block = obstacle_lessons.prompt_block("linkedin_post")
    lines = block.split("\n")

    assert len(lines) == len(set(lines))
    assert any("generic_hook" in l for l in lines)
    assert any("llm_viral" in l for l in lines)
    assert any("100%" in l for l in lines)
