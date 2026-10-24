"""Repair a YouTube Short's scenes before a schema miss burns a ladder attempt.

YoutubeShortSchema rejects the whole Short when any scene omits scene, type,
duration_s, on_screen, spoken, or visual_direction. On 2026-10-23 the model
kept a sixth scene that only had scene, type, and duration_s, and each of the
nine ladder attempts was spent on that same gap.

Repair fills a missing field only from text already on that scene (on_screen
is the first words of spoken, spoken is the on-screen line when the voiceover
is blank). A trailing stub with no line is dropped once five complete scenes
remain. Anything still empty is sent back to the model as a patch of only the
failing fields. New prices, percentages, or numbers that are not already in
the piece are refused. The 8.0 gates and the product-truth checks are not
touched; they still run on whatever this returns.

A scene-based Short that already has product and five complete scenes still
fails the schema when tagline is absent (run 40060597663: the model returned
product, hook, cta, and six scenes, and no tagline or script). featured_product
is the day's jar key, not the schema's product field. Repair copies product
from featured_product when product is blank, and copies tagline from hook,
title, or the first scene line already on the piece. It does not read
editorial_error or hold_reason, so a stored gate message cannot become the
tagline.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_TYPE_CYCLE = ("problem", "agitation", "product_reveal", "benefit", "cta")
_PRODUCT_ALIASES = ("featured_product", "product_name")
_TAGLINE_SOURCES = ("hook", "hook_text", "chosen_hook", "title")
_SPOKEN_ALIASES = ("voiceover", "narration", "dialogue", "audio")
_SCREEN_ALIASES = ("overlay", "text_overlay", "headline", "caption", "text")
_VISUAL_ALIASES = ("visual", "shot", "direction", "camera")
_VISUAL_DEFAULT = "Hold on the line already written."
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MONEY_OR_PERCENT = re.compile(r"₹\s*\d+(?:\.\d+)?|\brs\.?\s*\d+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*%", re.I)
_MEDICAL = ("cure", "diagnose", "diagnosis", "weight loss", "clinically")


def repair_yt_short(piece: dict, *, llm=None, allow_llm: bool = True) -> dict:
    """Mutate piece. Returns it. One LLM patch at most, and only for gaps that remain."""
    if not isinstance(piece, dict):
        return piece
    _alias_product(piece)
    scenes = piece.get("scenes")
    if isinstance(scenes, list):
        piece["scenes"] = _repair_scene_list(scenes)
    _fill_tagline(piece)
    if _schema_ok(piece) or not allow_llm:
        return piece
    gaps = _scene_gaps(piece)
    if not gaps:
        return piece
    caller = llm or _default_llm
    try:
        patch = caller(_repair_prompt(piece, gaps), "yt_short_schema_repair", 800)
    except Exception as exc:
        logger.warning("[yt-short] schema repair call failed: %s", exc)
        return piece
    if isinstance(patch, dict):
        _apply_patch(piece, patch, gaps)
        _alias_product(piece)
        _fill_tagline(piece)
    return piece


def _alias_product(piece: dict) -> None:
    """The schema reads product. The pipeline and many drafts only set featured_product."""
    if _text(piece.get("product")):
        return
    for key in _PRODUCT_ALIASES:
        name = _text(piece.get(key))
        if name:
            piece["product"] = name
            return


def _fill_tagline(piece: dict) -> None:
    """Format 2 still needs tagline. Copy one that is already written on the piece.

    editorial_error and hold_reason are excluded: they store the gate's own
    words, including the brand sentence that pydantic then shows inside the payload.
    """
    if _text(piece.get("tagline")) or not _text(piece.get("product")):
        return
    scenes = piece.get("scenes")
    if not isinstance(scenes, list):
        return
    ready = [scene for scene in scenes if isinstance(scene, dict) and _scene_ready(scene)]
    if len(ready) < 5:
        return
    for key in _TAGLINE_SOURCES:
        line = _text(piece.get(key))
        if line:
            piece["tagline"] = line
            return
    on_screen = _text(ready[0].get("on_screen"))
    if on_screen:
        piece["tagline"] = on_screen


def _scene_ready(scene: dict) -> bool:
    return (
        _present(scene.get("scene"), "scene")
        and _text(scene.get("type"))
        and _present(scene.get("duration_s"), "duration_s")
        and _has_lines(scene)
        and _text(scene.get("visual_direction"))
    )


def _repair_scene_list(scenes: list) -> list:
    repaired = []
    for index, raw in enumerate(scenes):
        if isinstance(raw, dict):
            repaired.append(_fill_scene(dict(raw), index))
    complete = [scene for scene in repaired if _has_lines(scene)]
    if len(complete) >= 5:
        return complete
    return repaired


def _fill_scene(scene: dict, index: int) -> dict:
    if not _text(scene.get("spoken")):
        for key in _SPOKEN_ALIASES:
            if _text(scene.get(key)):
                scene["spoken"] = _text(scene[key])
                break
    if not _text(scene.get("on_screen")):
        for key in _SCREEN_ALIASES:
            if _text(scene.get(key)):
                scene["on_screen"] = _first_words(scene[key], 4)
                break
    if not _text(scene.get("on_screen")) and _text(scene.get("spoken")):
        scene["on_screen"] = _first_words(scene["spoken"], 4)
    if not _text(scene.get("spoken")) and _text(scene.get("on_screen")):
        scene["spoken"] = _text(scene["on_screen"])
    if not _text(scene.get("visual_direction")):
        for key in _VISUAL_ALIASES:
            if _text(scene.get(key)):
                scene["visual_direction"] = _text(scene[key])
                break
    if not _text(scene.get("visual_direction")):
        scene["visual_direction"] = _VISUAL_DEFAULT
    duration = _as_duration(scene.get("duration_s"))
    if duration is None:
        for key in ("duration", "seconds", "duration_sec"):
            duration = _as_duration(scene.get(key))
            if duration is not None:
                break
    scene["duration_s"] = duration if duration is not None else 5.0
    if not _text(scene.get("type")):
        scene["type"] = _TYPE_CYCLE[index] if index < len(_TYPE_CYCLE) else "beat"
    scene_no = scene.get("scene")
    if isinstance(scene_no, bool) or not isinstance(scene_no, int):
        try:
            scene["scene"] = int(str(scene_no).strip())
        except (TypeError, ValueError):
            scene["scene"] = index + 1
    return scene


def _schema_ok(piece: dict) -> bool:
    from pydantic import ValidationError

    from content_generator.core.schema_validation import YoutubeShortSchema

    try:
        YoutubeShortSchema.model_validate(piece)
    except ValidationError:
        return False
    return True


def _scene_gaps(piece: dict) -> list[dict]:
    from pydantic import ValidationError

    from content_generator.core.schema_validation import YoutubeShortSchema

    try:
        YoutubeShortSchema.model_validate(piece)
    except ValidationError as exc:
        gaps = []
        for err in exc.errors():
            loc = err.get("loc") or ()
            if len(loc) >= 3 and loc[0] == "scenes" and isinstance(loc[1], int):
                gaps.append({"index": loc[1], "field": str(loc[2])})
        return gaps
    return []


def _repair_prompt(piece: dict, gaps: list[dict]) -> str:
    from content_generator.prompts.yt_short import scene_contract

    scenes = piece.get("scenes") if isinstance(piece.get("scenes"), list) else []
    missing = []
    for gap in gaps:
        index = gap["index"]
        current = scenes[index] if index < len(scenes) and isinstance(scenes[index], dict) else {}
        missing.append({"index": index, "missing": gap["field"], "scene": current})
    return (
        "Repair ONLY the missing YouTube Short scene fields listed below. "
        'Return one JSON object {"scenes": [{"scene": <number>, "<missing field>": "<value>"}, ...]}. '
        "Use words already present in the piece. Do not add a price, a statistic, a percentage, "
        "a medical claim, or a product fact that is not already written in the piece. "
        "Do not rewrite a field that already has text.\n\n"
        + scene_contract()
        + "\n\nPIECE:\n"
        + json.dumps(piece, ensure_ascii=False)[:4000]
        + "\n\nMISSING:\n"
        + json.dumps(missing, ensure_ascii=False)
    )


def _apply_patch(piece: dict, patch: dict, gaps: list[dict]) -> None:
    incoming = patch.get("scenes")
    scenes = piece.get("scenes")
    if not isinstance(incoming, list) or not isinstance(scenes, list):
        return
    allowed: dict[int, set[str]] = {}
    for gap in gaps:
        allowed.setdefault(int(gap["index"]), set()).add(gap["field"])
    by_number = {}
    for item in incoming:
        if not isinstance(item, dict):
            continue
        try:
            by_number[int(item.get("scene"))] = item
        except (TypeError, ValueError):
            continue
    blob = _existing_text(piece)
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        try:
            numbered = by_number.get(int(scene.get("scene")))
        except (TypeError, ValueError):
            numbered = None
        positional = incoming[index] if index < len(incoming) and isinstance(incoming[index], dict) else None
        if isinstance(numbered, dict):
            source = numbered
        elif isinstance(positional, dict) and "scene" not in positional:
            source = positional
        else:
            continue
        for field in allowed.get(index, ()):
            if _present(scene.get(field), field):
                continue
            value = source.get(field)
            if not _present(value, field):
                continue
            if field in ("on_screen", "spoken", "visual_direction", "type"):
                text = str(value).strip()
                if _invents_claim(text, blob):
                    logger.info("[yt-short] refused repaired %s on scene %s — new claim", field, index)
                    continue
                scene[field] = text
            elif field == "duration_s":
                duration = _as_duration(value)
                if duration is not None:
                    scene[field] = duration
            elif field == "scene":
                try:
                    scene[field] = int(value)
                except (TypeError, ValueError):
                    continue


def _default_llm(prompt: str, label: str, max_tokens: int):
    from content_generator.providers.llm_router import call

    return call(prompt, label, max_tokens)


def _existing_text(piece: dict) -> str:
    return json.dumps(piece, ensure_ascii=False)


def _invents_claim(new: str, existing: str) -> bool:
    old = existing.lower()
    new_l = new.lower()
    folded_old = re.sub(r"\s+", "", old)
    for match in _MONEY_OR_PERCENT.finditer(new):
        token = match.group(0).lower()
        if token not in old and re.sub(r"\s+", "", token) not in folded_old:
            return True
    have = set(_NUMBER.findall(existing))
    if set(_NUMBER.findall(new)) - have:
        return True
    return any(word in new_l and word not in old for word in _MEDICAL)


def _has_lines(scene: dict) -> bool:
    return bool(_text(scene.get("on_screen")) and _text(scene.get("spoken")))


def _present(value, field: str) -> bool:
    if field == "duration_s":
        return _as_duration(value) is not None
    if field == "scene":
        return isinstance(value, int) and not isinstance(value, bool)
    return bool(_text(value))


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_words(value, count: int) -> str:
    return " ".join(_text(value).split()[:count])


def _as_duration(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = _NUMBER.search(str(value))
    if not match:
        return None
    number = float(match.group(0))
    return number if number > 0 else None
