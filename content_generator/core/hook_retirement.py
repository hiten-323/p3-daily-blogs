"""Post-publish retirement of measured-losing hooks and hook templates.

The learning engine already ranks published posts, but its bottom-20% list was
only injected as advice in a prompt. This module turns that measurement into
durable state: a hook (or the hook strategy behind a template) that measured
in the bottom 20% is written to ``output/learning/retired_hooks.json``, the
regeneration loop stops offering a template that reuses it, and the fatigue
guard lists it as a permanent avoid.

Retirement needs the same evidence bar as the learning engine: at least
``_MIN_SAMPLES`` measurable posts with the same objective, platform, and
format, and only the strictly losing bottom slice. One bad day is not a rule,
and evidence scored under a different KPI is discounted before it gets here.

Nothing here decides whether a draft may publish. It only decides which
proven starting points the generator should stop reusing.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

_MIN_SAMPLES = 5
_BOTTOM_FRACTION = 0.2
_MAX_TRACKED = 500


def _dir() -> str:
    return os.getenv("LEARNING_DIR", os.path.join("output", "learning"))


def _path() -> str:
    return os.path.join(_dir(), "retired_hooks.json")


def normalize(text) -> str:
    """Lowercase alphanumerics with collapsed spaces, for exact reuse matching."""
    return " ".join(re.sub(r"[^a-z0-9\s]", "", str(text or "").lower()).split())


def _empty() -> dict:
    return {"hooks": {}, "strategies": {}, "updated_at": ""}


def _load() -> dict:
    path = _path()
    if not os.path.exists(path):
        return _empty()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("[retirement] could not read %s: %s", path, exc)
        return _empty()
    if not isinstance(payload, dict):
        return _empty()
    state = _empty()
    for key in ("hooks", "strategies"):
        value = payload.get(key)
        if isinstance(value, dict):
            state[key] = {str(k): v for k, v in value.items() if str(k).strip()}
    state["updated_at"] = str(payload.get("updated_at") or "")
    return state


def _save(state: dict) -> None:
    parent = os.path.dirname(os.path.abspath(_path()))
    os.makedirs(parent, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=parent,
            prefix=".retired_hooks.", suffix=".tmp", delete=False,
        ) as handle:
            tmp_name = handle.name
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, _path())
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                logger.warning("[retirement] could not clean temp file %s", tmp_name)


def _losers(entries: list[dict]) -> list[tuple[dict, float]]:
    from content_generator.core.learning_engine import (
        _is_measurable, _objective_factor, _weighted_score,
    )

    # Compare like with like. A Story's reach and a LinkedIn post's engagement
    # are not interchangeable, even when both were created for the same KPI.
    groups: dict[tuple[str, str, str], list[tuple[dict, float]]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("metrics") or not _is_measurable(entry):
            continue
        if _objective_factor(entry) != 1.0:
            continue
        key = (
            str(entry.get("platform") or "").strip().lower(),
            str(entry.get("format") or "").strip().lower(),
            str(entry.get("kpi") or "").strip().lower(),
        )
        groups.setdefault(key, []).append((entry, _weighted_score(entry)))

    losers: list[tuple[dict, float]] = []
    for same_surface in groups.values():
        if len(same_surface) < _MIN_SAMPLES:
            continue
        same_surface.sort(key=lambda pair: pair[1])
        median = sorted(score for _, score in same_surface)[len(same_surface) // 2]
        bottom_n = max(1, int(len(same_surface) * _BOTTOM_FRACTION))
        # Only strictly below-median evidence is retired: an all-equal sample
        # has no loser, and retiring it would remove every proven starting point.
        losers.extend((entry, score) for entry, score in same_surface[:bottom_n] if score < median)
    return losers


def retire_from_learning(entries: list[dict] | None = None, *, now: str | None = None) -> dict:
    """Retire measured losers durably. Returns what changed (idempotent)."""
    if entries is None:
        from content_generator.core.learning_engine import _load_log
        entries = _load_log()
    losers = _losers(entries)
    state = _load()
    stamp = now or datetime.datetime.now().isoformat(timespec="seconds")
    added_hooks: list[str] = []
    added_strategies: list[str] = []

    for entry, score in losers:
        asset = str(entry.get("publication_id") or entry.get("asset_id") or "")
        record = {
            "score": round(float(score), 4),
            "source_asset": asset,
            "platform": str(entry.get("platform") or ""),
            "format": str(entry.get("format") or ""),
            "retired_at": stamp,
        }
        hook = normalize(entry.get("hook"))
        if hook and hook not in state["hooks"]:
            state["hooks"][hook] = dict(record, text=str(entry.get("hook") or ""))
            added_hooks.append(hook)
        for field in ("hook_strategy", "attention_mechanism"):
            strategy = normalize(entry.get(field))
            if strategy and strategy not in state["strategies"]:
                state["strategies"][strategy] = dict(record, field=field)
                added_strategies.append(strategy)

    if added_hooks or added_strategies:
        if len(state["hooks"]) > _MAX_TRACKED:
            keep = sorted(state["hooks"].items(), key=lambda kv: kv[1].get("retired_at", ""))[-_MAX_TRACKED:]
            state["hooks"] = dict(keep)
        if len(state["strategies"]) > _MAX_TRACKED:
            keep = sorted(state["strategies"].items(), key=lambda kv: kv[1].get("retired_at", ""))[-_MAX_TRACKED:]
            state["strategies"] = dict(keep)
        state["updated_at"] = stamp
        _save(state)
        logger.info("[retirement] retired %d hook(s), %d strategie(s) from %d measured loser(s)",
                    len(added_hooks), len(added_strategies), len(losers))

    return {
        "added_hooks": added_hooks,
        "added_strategies": added_strategies,
        "losers": len(losers),
        "evidence": len(entries),
    }


def retired_hooks() -> set[str]:
    return set(_load()["hooks"])


def retired_strategies() -> set[str]:
    return set(_load()["strategies"])


def is_hook_retired(hook: str) -> bool:
    key = normalize(hook)
    return bool(key) and key in _load()["hooks"]


def template_tags(template: str) -> set[str]:
    """The hook strategy and attention mechanism a template is built on."""
    from content_generator.core.scroller_psychology import (
        classify_hook_strategy, classify_mechanism,
    )

    piece = {"hook": template}
    tags = set()
    strategy = classify_hook_strategy(piece)
    if strategy:
        tags.add(strategy)
    mechanism = classify_mechanism(piece)
    if mechanism:
        tags.add(mechanism)
    return tags


def is_template_retired(template: str) -> bool:
    if is_hook_retired(template):
        return True
    retired = retired_strategies()
    return bool(retired & template_tags(template))


def active_templates(templates: list[str]) -> list[str]:
    """Templates that do not reuse a measured-losing hook or strategy."""
    if not templates:
        return []
    return [template for template in templates if not is_template_retired(template)]


def retired_lines(limit: int = 8) -> list[str]:
    """Short prompt lines naming what the account stopped reusing."""
    state = _load()
    lines: list[str] = []
    for key, record in list(state["hooks"].items())[-limit:]:
        text = str(record.get("text") or key)
        lines.append(f'- permanently retired hook (measured bottom 20%): "{text[:120]}"')
    for key in list(state["strategies"])[-limit:]:
        lines.append(f"- permanently retired hook strategy: {key}")
    return lines
