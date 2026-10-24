"""YouTube Short scene schema: prompt contract, repair before a ladder miss, live HF model.

Run 39956370166 held yt_short after 9 attempts because scenes.5 omitted
on_screen, spoken, and visual_direction. Groq logged OK with 0 chars, and
Hugging Face 400'd on Qwen/Qwen2.5-72B-Instruct.
"""
from __future__ import annotations

import json

from content_generator.core.brand_guard import EDITORIAL_THRESHOLD
from content_generator.core.fallback_ladder import PASS_FLOOR
from content_generator.core.growth_engine import PASS_THRESHOLD
from content_generator.core.schema_validation import YoutubeShortSchema
from content_generator.core.viral_gate import PASS_MARK
from content_generator.core.yt_short_repair import repair_yt_short
from content_generator.prompts.yt_short import SCENE_FIELDS, build, scene_contract


def test_quality_gates_stay_at_8():
    assert PASS_FLOOR == 8.0
    assert PASS_THRESHOLD == 8.0
    assert PASS_MARK == 8.0
    assert EDITORIAL_THRESHOLD == 8.0


def test_prompt_requires_every_scene_field_with_example_json():
    prompt = build("Bold", 3)
    contract = scene_contract()
    assert contract in prompt
    for field in SCENE_FIELDS:
        assert field in contract
    example = json.loads(contract.split("Example of one complete scene object:\n", 1)[1])
    assert set(SCENE_FIELDS) <= set(example)
    assert example["on_screen"] and example["spoken"] and example["visual_direction"]
    assert isinstance(example["scene"], int)
    assert isinstance(example["duration_s"], (int, float))


def test_regen_prompt_requires_the_same_scene_fields(monkeypatch):
    seen = {}

    def capture(prompt, label="", max_tokens=3000):
        seen[label] = prompt
        return {"hook": "A hook that is long enough", "script": "s" * 60, "cta": "Shop p3online.in today"}

    monkeypatch.setattr("content_generator.providers.llm_router.call", capture)
    from content_generator.scheduler.daily import _regenerate_piece

    piece = {"featured_product": "Bold", "product": "Bold"}
    feedback = "schema: scenes.5.on_screen Field required"
    _regenerate_piece("yt_short", piece, feedback, {"day_number": 1, "featured_product": "Bold"})
    _regenerate_piece(
        "yt_short", piece, feedback, {"day_number": 1, "featured_product": "Bold"}, from_scratch=True,
    )
    for label in ("regen_yt_short", "fresh_yt_short"):
        prompt = seen[label]
        for field in SCENE_FIELDS:
            assert field in prompt
        assert "READ THE JAR" in prompt


def test_on_screen_is_derived_from_spoken_without_new_words():
    spoken = "The cupboard jar has a label you skip every morning."
    piece = _short(scenes=[
        {"type": "problem", "spoken": spoken},
        *_filled(2, 5),
    ])
    repair_yt_short(piece, allow_llm=False)
    scene = piece["scenes"][0]
    assert scene["on_screen"] == "The cupboard jar has"
    assert scene["spoken"] == spoken
    assert set(scene["on_screen"].split()) <= set(spoken.split())
    assert "chicory" not in json.dumps(piece).lower() or "chicory" in spoken.lower()
    assert _schema_ok(piece)


def test_empty_spoken_is_filled_from_on_screen_only():
    piece = _short(scenes=[
        {"scene": 1, "type": "cta", "duration_s": 5, "on_screen": "READ THE JAR", "spoken": ""},
        *_filled(2, 5),
    ])
    repair_yt_short(piece, allow_llm=False)
    assert piece["scenes"][0]["spoken"] == "READ THE JAR"
    assert _schema_ok(piece)


def test_stub_sixth_scene_is_dropped_when_five_scenes_are_complete():
    """The held Short: scenes.5 was {scene, type, duration_s} and nothing else."""
    piece = _short(scenes=[
        *_filled(1, 5),
        {"scene": 6, "type": "follow", "duration_s": 3},
    ])
    called = {"n": 0}

    def llm(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("a complete Short must not call the model")

    repair_yt_short(piece, llm=llm)
    assert called["n"] == 0
    assert len(piece["scenes"]) == 5
    assert _schema_ok(piece)
    assert all(scene["spoken"] == f"Line {scene['scene']} about the jar label." for scene in piece["scenes"])


def test_missing_structural_fields_are_filled_from_the_scene():
    piece = _short(scenes=[
        {"voiceover": "Boil then wait before the water hits the cup."},
        *_filled(2, 5),
    ])
    repair_yt_short(piece, allow_llm=False)
    scene = piece["scenes"][0]
    assert scene["scene"] == 1
    assert scene["type"] == "problem"
    assert scene["duration_s"] == 5.0
    assert scene["spoken"].startswith("Boil then wait")
    assert scene["on_screen"] == "Boil then wait before"
    assert scene["visual_direction"]
    assert _schema_ok(piece)


def test_llm_repairs_only_failing_fields_and_cannot_invent_a_price():
    scenes = _filled(1, 4)
    scenes.append({"scene": 5, "type": "cta", "duration_s": 4})
    original = scenes[0]["spoken"]
    piece = _short(scenes=scenes)
    calls = []

    def llm(prompt, label, max_tokens):
        calls.append((label, prompt, max_tokens))
        return {"scenes": [
            {"scene": 1, "spoken": "Only ₹18 a cup and it cures fatigue.", "on_screen": "IGNORE"},
            {"scene": 5, "on_screen": "READ THE JAR", "spoken": "Read the jar before you brew.",
             "visual_direction": "Jar on the counter"},
        ]}

    repair_yt_short(piece, llm=llm)
    assert calls and calls[0][0] == "yt_short_schema_repair"
    assert "Repair ONLY the missing" in calls[0][1]
    assert piece["scenes"][0]["spoken"] == original
    assert piece["scenes"][0]["on_screen"] != "IGNORE"
    scene = piece["scenes"][4]
    assert scene["on_screen"] == "READ THE JAR"
    assert scene["spoken"] == "Read the jar before you brew."
    assert "₹18" not in json.dumps(piece)
    assert "cure" not in json.dumps(piece).lower()
    assert _schema_ok(piece)


def test_llm_price_on_a_missing_line_is_refused():
    scenes = _filled(1, 4)
    scenes.append({"scene": 5, "type": "cta", "duration_s": 4})
    piece = _short(scenes=scenes)

    def llm(_prompt, _label, _max_tokens):
        return {"scenes": [{"scene": 5, "on_screen": "ONLY ₹18", "spoken": "Only ₹18 a cup."}]}

    repair_yt_short(piece, llm=llm)
    assert not str(piece["scenes"][4].get("spoken") or "").strip()
    assert not _schema_ok(piece)


def test_schema_repair_does_not_burn_a_ladder_attempt(monkeypatch):
    """A derivable miss is fixed, then scored, on the same attempt."""
    spoken = [
        "The cupboard jar has a label you skip every morning.",
        "Turn it and read the ingredient line before the kettle.",
        "Purity Beans Bold is agglomerated pure coffee.",
        "Zero chicory in this jar, and the label is the recipe.",
        "Shop the jar at p3online.in and subscribe for the next label.",
    ]
    scenes = []
    for index, line in enumerate(spoken, start=1):
        scenes.append({
            "scene": index,
            "type": ("problem", "agitation", "product_reveal", "benefit", "cta")[index - 1],
            "duration_s": 5,
            "spoken": line,
            "visual_direction": "Kitchen counter, jar in frame",
        })
    scenes.append({"scene": 6, "type": "follow", "duration_s": 3})
    content = {
        "day_number": 12,
        "featured_product": "Bold",
        "yt_short": {
            "product": "Bold",
            "tagline": "Read the jar",
            "featured_product": "Bold",
            "hook": "The label is the only recipe that matters",
            "cta": "Shop p3online.in",
            "title": "Read the jar before you brew",
            "description": "Purity Beans. Bold is agglomerated pure coffee. p3online.in",
            "scenes": scenes,
        },
    }

    def review(_piece, label=""):
        assert label == "yt_short"
        return {"overall": 8.6, "feedback": "Measured review."}

    def no_llm(*_args, **_kwargs):
        raise AssertionError("schema repair and regen must not call the model")

    monkeypatch.setattr("content_generator.providers.llm_router.any_provider_available", lambda: True)
    monkeypatch.setattr("content_generator.providers.llm_router.call", no_llm)
    monkeypatch.setattr("content_generator.agents.editorial.review_content", review)
    monkeypatch.setattr(
        "content_generator.core.viral_gate.evaluate",
        lambda *_a, **_k: {"passed": True, "overall": 8.4, "honesty": []},
    )
    monkeypatch.setattr(
        "content_generator.scheduler.daily._growth_gate_reason",
        lambda *_a, **_k: "",
    )

    from content_generator.scheduler.daily import _do_editorial

    _do_editorial(content, only={"yt_short"})
    short = content["yt_short"]
    assert short["editorial_score"]["overall"] == 8.6
    assert not short.get("held")
    assert len(short["scenes"]) == 5
    assert short["scenes"][0]["on_screen"] == "The cupboard jar has"
    ladder = content.get("fallback_ladder") or {}
    assert not any(row.get("status") == "exhausted" for row in ladder.get("yt_short") or [])


def test_scene_short_without_tagline_is_repaired_from_the_hook_already_on_the_piece():
    """Run 40060597663 attempt 9/9. The model returned product, hook, cta, and
    six complete scenes, and no tagline or script. featured_product was only
    the first key. Schema rejected the shape before the judge could score it.
    The stored schema/brand error must not be copied into the tagline.
    """
    hook = "At 6:47 AM, your milk coffee is already decided by one number on the jar: 70."
    piece = {
        "featured_product": "Ultra Blend 100g",
        "product": "Ultra Blend 100g",
        "hook": hook,
        "cta": "Follow @purepantryprovisions | Shop p3online.in",
        "share_trigger": "Share with someone who starts every morning with coffee.",
        "editorial_error": (
            "schema: missing tagline | brand: ['product truth: Per-cup price/yield is "
            "verified only for Ultra Blend; name Ultra Blend or omit the figure']"
        ),
        "scenes": _filled(1, 6),
    }
    assert not _schema_ok(piece)
    called = {"n": 0}

    def llm(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("the hook already on the piece is the tagline")

    repair_yt_short(piece, llm=llm)
    assert called["n"] == 0
    assert piece["tagline"] == hook
    assert piece["product"] == "Ultra Blend 100g"
    assert len(piece["scenes"]) == 6
    assert "omit the figure" not in piece["tagline"]
    assert "₹" not in piece["tagline"]
    assert _schema_ok(piece)


def test_featured_product_fills_product_when_the_scene_short_omits_it():
    piece = _short(scenes=_filled(1, 5))
    piece.pop("product")
    assert piece["featured_product"] == "Bold"
    assert not _schema_ok(piece)
    repair_yt_short(piece, allow_llm=False)
    assert piece["product"] == "Bold"
    assert piece["tagline"] == "Read the jar"
    assert _schema_ok(piece)


def test_scratch_prompt_requires_product_and_tagline_when_the_draft_omits_them():
    from content_generator.core.fallback_ladder import scratch_prompt

    prompt = scratch_prompt(
        "yt_short",
        {
            "featured_product": "Ultra Blend",
            "hook": "At 6:47 AM the jar already decided the cup.",
            "cta": "Shop p3online.in today",
            "scenes": [],
        },
        "schema: missing tagline",
        8.0,
        "BRAND",
    )
    listed = prompt.split("Return ONE JSON object with these keys: ", 1)[1].split(".", 1)[0]
    keys = json.loads(listed)
    assert "product" in keys
    assert "tagline" in keys
    assert "scenes" in keys


def test_hf_default_replaces_the_missing_qwen72():
    from pathlib import Path

    text = Path("content_generator/providers/huggingface.py").read_text(encoding="utf-8")
    default = text.split("HF_MODELS", 1)[1].split(")", 1)[0]
    assert "Qwen/Qwen2.5-72B-Instruct" not in default
    assert "Qwen/Qwen3-8B" in default
    assert "meta-llama/Llama-3.3-70B-Instruct" in default


def _filled(start: int, end: int) -> list[dict]:
    types = ("problem", "agitation", "product_reveal", "benefit", "cta", "beat")
    rows = []
    for number in range(start, end + 1):
        rows.append({
            "scene": number,
            "type": types[number - 1],
            "duration_s": 5,
            "on_screen": f"LINE {number}",
            "spoken": f"Line {number} about the jar label.",
            "visual_direction": "Jar on the counter",
        })
    return rows


def _short(scenes: list[dict]) -> dict:
    return {
        "product": "Bold",
        "tagline": "Read the jar",
        "featured_product": "Bold",
        "scenes": scenes,
    }


def _schema_ok(piece: dict) -> bool:
    try:
        YoutubeShortSchema.model_validate(piece)
    except Exception:
        return False
    return True
