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


def _load(*, strict: bool = False) -> dict:
    """Read retirement state; strict consumers must never erase a corrupt avoid-list."""
    path = _path()
    if not os.path.exists(path):
        return _empty()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("retirement state must be a JSON object")
        state = _empty()
        for key in ("hooks", "strategies"):
            value = payload.get(key)
            if not isinstance(value, dict):
                raise ValueError(f"retirement state field {key!r} must be an object")
            state[key] = {str(k): v for k, v in value.items() if str(k).strip()}
        state["updated_at"] = str(payload.get("updated_at") or "")
        return state
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("[retirement] could not read %s: %s", path, exc)
        if strict:
            raise ValueError(f"Refusing to ignore corrupt retirement state: {path}") from exc
        return _empty()


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


def _surface_groups(entries: list[dict]) -> dict[tuple[str, str, str], list[tuple[dict, float]]]:
    from content_generator.core.learning_engine import (
        _is_measurable, _objective_factor, _weighted_score, is_teachable,
    )

    groups: dict[tuple[str, str, str], list[tuple[dict, float]]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("metrics") or not _is_measurable(entry):
            continue
        if not is_teachable(entry) or _objective_factor(entry) != 1.0:
            continue
        # Legacy rows without an explicit KPI/surface cannot establish that
        # the samples are comparable, so they remain advisory only.
        platform = str(entry.get("platform") or "").strip().lower()
        fmt = str(entry.get("format") or "").strip().lower()
        kpi = str(entry.get("kpi") or "").strip().lower()
        if not (platform and fmt and kpi):
            continue
        groups.setdefault((platform, fmt, kpi), []).append((entry, _weighted_score(entry)))
    return groups


def _losers(entries: list[dict]) -> list[tuple[dict, float]]:
    # Compare like with like. A Story's reach and a LinkedIn post's engagement
    # are not interchangeable, even when both were created for the same KPI.
    losers: list[tuple[dict, float]] = []
    for same_surface in _surface_groups(entries).values():
        if len(same_surface) < _MIN_SAMPLES:
            continue
        same_surface.sort(key=lambda pair: pair[1])
        median = sorted(score for _, score in same_surface)[len(same_surface) // 2]
        bottom_n = max(1, int(len(same_surface) * _BOTTOM_FRACTION))
        # Only strictly below-median evidence is retired: an all-equal sample
        # has no loser, and retiring it would remove every proven starting point.
        losers.extend((entry, score) for entry, score in same_surface[:bottom_n] if score < median)
    return losers


def _strategy_losers(entries: list[dict]) -> list[tuple[str, str, str, str, str, float]]:
    """Retire a strategy only after five same-surface examples prove it weak."""
    result = []
    for (platform, fmt, kpi), same_surface in _surface_groups(entries).items():
        if len(same_surface) < _MIN_SAMPLES:
            continue
        surface_median = sorted(score for _, score in same_surface)[len(same_surface) // 2]
        for field in ("hook_strategy", "attention_mechanism"):
            by_strategy: dict[str, list[float]] = {}
            for entry, score in same_surface:
                strategy = normalize(entry.get(field))
                if strategy:
                    by_strategy.setdefault(strategy, []).append(score)
            for strategy, scores in by_strategy.items():
                if len(scores) < _MIN_SAMPLES:
                    continue
                strategy_median = sorted(scores)[len(scores) // 2]
                if strategy_median < surface_median:
                    result.append((platform, fmt, kpi, field, strategy, strategy_median))
    return result


def retire_from_learning(entries: list[dict] | None = None, *, now: str | None = None) -> dict:
    """Retire measured losers durably. Returns what changed (idempotent)."""
    if entries is None:
        from content_generator.core.learning_engine import _load_log
        entries = _load_log()
    losers = _losers(entries)
    strategy_losers = _strategy_losers(entries)
    state = _load(strict=True)
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
    for platform, fmt, kpi, field, strategy, score in strategy_losers:
        key = "::".join((platform, fmt, kpi, field, strategy))
        if key not in state["strategies"]:
            state["strategies"][key] = {
                "score": round(float(score), 4), "platform": platform,
                "format": fmt, "kpi": kpi, "field": field,
                "strategy": strategy, "retired_at": stamp,
            }
            added_strategies.append(key)

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
    return set(_load(strict=True)["hooks"])


def retired_strategies(platform: str = "", fmt: str = "") -> set[str]:
    state = _load(strict=True)
    return {
        str(record.get("strategy") or "")
        for record in state["strategies"].values()
        if (not platform or record.get("platform") == platform)
        and (not fmt or record.get("format") == fmt)
        and record.get("strategy")
    }


def is_hook_retired(hook: str) -> bool:
    key = normalize(hook)
    return bool(key) and key in _load(strict=True)["hooks"]


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


def is_template_retired(template: str, platform: str = "", fmt: str = "") -> bool:
    if is_hook_retired(template):
        return True
    retired = retired_strategies(platform, fmt)
    return bool(retired & template_tags(template))


def active_templates(templates: list[str], platform: str = "", fmt: str = "") -> list[str]:
    """Templates that do not reuse a measured-losing hook or same-surface strategy."""
    if not templates:
        return []
    # Load once in strict mode: malformed state must never make retired hooks
    # available again merely because a forgiving reader returned an empty set.
    state = _load(strict=True)
    retired_hooks_set = set(state["hooks"])
    retired_strategy_set = {
        str(record.get("strategy") or "")
        for record in state["strategies"].values()
        if (not platform or record.get("platform") == platform)
        and (not fmt or record.get("format") == fmt)
        and record.get("strategy")
    }
    active = []
    for template in templates:
        if normalize(template) in retired_hooks_set:
            continue
        if retired_strategy_set & template_tags(template):
            continue
        active.append(template)
    return active


def retired_lines(limit: int = 8) -> list[str]:
    """Short prompt lines naming what the account stopped reusing."""
    state = _load(strict=True)
    lines: list[str] = []
    for key, record in list(state["hooks"].items())[-limit:]:
        text = str(record.get("text") or key)
        lines.append(f'- permanently retired hook (measured bottom 20%): "{text[:120]}"')
    for record in list(state["strategies"].values())[-limit:]:
        lines.append(
            "- permanently retired hook strategy for %s/%s: %s"
            % (record.get("platform", "unknown"), record.get("format", "unknown"), record.get("strategy", "unknown"))
        )
    return lines
