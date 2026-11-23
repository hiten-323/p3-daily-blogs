"""First-pass quality: aim for every piece to clear the gates on its FIRST generation.

Owner, 17 Nov 2026: "make sure the first generation itself passes the bar, so no
retry would be needed". Three parts, none of which changes a gate:

1. brief(label): before writing, the writer gets the scorers' exact rubric (the
   editorial dimensions and rules, copied verbatim from agents/editorial.py's
   prompt, and viral_gate.DIMENSIONS / FORMAT_RULES / PASS_MARK), the top-scoring
   past pieces for that platform, the recent gate feedback for it and the
   obstacle lessons.
2. generate(label, prompt, tokens): draft -> score with the SAME copy/claim gate,
   editorial scorer and viral scorer -> rewrite with that feedback, up to N rounds,
   inside generation and before anything is saved. The best version is kept.
3. The editorial loop in scheduler/daily.py still re-scores every piece, and
   retry-unposted stays as the safety net. The pass marks (editorial
   get_current_pass_score(), floor 8.0; viral 9.0) and the claim rules are read
   from the gates, never redefined or lowered here.

The self-critique loop costs about three LLM calls per round, so by default it
runs only when the paid xAI (Grok) key is present (FIRST_PASS_SELF_CRITIQUE=auto).
Without it the free quotas would be burned; brief() still runs because it is free.
Nothing here raises: any failure returns the best draft so far.
"""
from __future__ import annotations

import copy
import glob
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

# label -> (content key, index) exactly as scheduler/daily.py review_targets.
TARGETS = {
    "reel_1": ("reels", 0),
    "carousel": ("carousel", None),
    "instagram_post": ("instagram_post", None),
    "linkedin_post": ("linkedin_post", None),
    "facebook_post": ("facebook_post", None),
    "threads_post": ("threads_post", None),
    "growth_reel": ("growth_reel", None),
    "yt_short": ("yt_short", None),
    "stories": ("stories", "story_1"),
}

DEFAULT_ROUNDS = 3
MAX_ROUNDS = 6
_DEADLINE: dict = {"at": None}
_META_KEYS = ("editorial_score", "viral_potential", "editorial_error", "gate_rejection",
              "ladder_exhausted", "publish_blocked", "needs_regen", "held", "hold_reason",
              "fallback_ladder", "first_pass")


# ── settings ─────────────────────────────────────────────────────────────────

def rounds() -> int:
    try:
        n = int(os.getenv("FIRST_PASS_ROUNDS", str(DEFAULT_ROUNDS)))
    except ValueError:
        n = DEFAULT_ROUNDS
    return max(1, min(MAX_ROUNDS, n))


def self_critique_enabled() -> bool:
    mode = os.getenv("FIRST_PASS_SELF_CRITIQUE", "auto").strip().lower()
    if mode in ("1", "true", "on", "yes"):
        return True
    if mode in ("0", "false", "off", "no"):
        return False
    from content_generator.providers import xai
    return bool(xai.get_key())


def start_budget(seconds: int | None = None) -> None:
    """Soft time budget for all self-critique rounds in one generation run."""
    if seconds is None:
        seconds = int(os.getenv("FIRST_PASS_BUDGET_S", "900"))
    _DEADLINE["at"] = time.monotonic() + max(0, int(seconds))


def _budget_left() -> bool:
    at = _DEADLINE.get("at")
    return at is None or time.monotonic() < at


# ── the gates' own rubric ────────────────────────────────────────────────────

def _editorial_threshold() -> float:
    try:
        from content_generator.core.editorial_engine import get_current_pass_score
        return max(8.0, float(get_current_pass_score()))
    except Exception:
        return 8.0


def _editorial_rubric() -> tuple[str, str]:
    """(brand rules, scoring rubric) copied verbatim from the editorial scorer's prompt."""
    from content_generator.agents import editorial
    tpl = editorial._PROMPT_TEMPLATE
    lines = tpl.split("\n")
    rules = lines[1] if len(lines) > 1 else ""
    start = tpl.find("Score each dimension")
    end = tpl.find("Reply ONLY")
    rubric = tpl[start:end].strip() if start >= 0 and end > start else ""
    return rules, rubric


def rubric_block(label: str) -> str:
    from content_generator.core import viral_gate
    rules, rubric = _editorial_rubric()
    fmt = viral_gate.format_for(label)
    dims = "\n".join(f"- {k}: {v}" for k, v in viral_gate.DIMENSIONS.items())
    honesty = sorted({why for _rx, why in viral_gate._DISHONEST})
    thr = _editorial_threshold()
    return (
        "HOW THIS PIECE WILL BE SCORED (write to pass on the first try; the judges are strict "
        "and most first drafts score 5-7):\n"
        f"GATE 1, EDITORIAL: overall must be >= {thr:.1f}/10.\n{rubric}\n"
        f"Editor's brand rules: {rules}\n"
        f"GATE 2, VIRAL POTENTIAL: overall must be >= {viral_gate.PASS_MARK:.1f}/10. The overall is the "
        "LOWER of the judge's overall and the mean of these dimensions, so EVERY dimension must "
        f"reach {viral_gate.PASS_MARK:.0f}+:\n{dims}\n"
        f"FORMAT RULES for {label} ({fmt}): {viral_gate.FORMAT_RULES.get(fmt, 'platform-native pacing')}\n"
        "Automatic fails (no score can rescue them): " + "; ".join(honesty) + ". Also never: "
        "'fresh', 'lab tested', 'single-origin', bean or variety wording, 'fully', zero-acidity, "
        "knocking competitors or chicory, calling Ultra Blend pure (it is 70% coffee / 30% chicory), "
        "freeze-dried for anything but Purica/Purista, agglomerated for anything but Bold/Prima, "
        "or any price that is not the live Shopify price already given to you."
        + ("\nOn-canvas word cap: keep each frame's on-screen text concise (<= 12 words per frame) to avoid visual clutter." if label == "stories" else "")
        + ("\nReel 1 brand facts: MUST include at least one verifiable brand fact (e.g. Bold is pure agglomerated coffee, Purista/Purica is pure freeze-dried coffee, Ultra Blend is 70% coffee / 30% chicory) in the caption or cta." if label == "reel_1" else "")
        + ("\nThreads anti-hedging: Forbid competitor-knocking ('might be', 'other brands cut', 'secretly'). State only Purity Beans' own verifiable processes." if label == "threads_post" else "")
    )


# ── past pieces and recent feedback ──────────────────────────────────────────

def _content_files(output_dir: str, limit: int) -> list[str]:
    files = sorted(glob.glob(os.path.join(output_dir, "content_20*.json")), reverse=True)
    return files[:limit]


def _piece(content: dict, label: str):
    key, idx = TARGETS.get(label, (label, None))
    value = content.get(key) if isinstance(content, dict) else None
    if isinstance(idx, int):
        value = value[idx] if isinstance(value, list) and len(value) > idx else None
    elif isinstance(idx, str):
        value = value.get(idx) if isinstance(value, dict) else None
    return value if isinstance(value, dict) else None


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _scores(piece: dict) -> tuple[float | None, float | None, bool]:
    ed = piece.get("editorial_score") if isinstance(piece.get("editorial_score"), dict) else {}
    vg = piece.get("viral_potential") if isinstance(piece.get("viral_potential"), dict) else {}
    e, v = _num(ed.get("overall")), _num(vg.get("overall"))
    passed = bool(e is not None and e >= _editorial_threshold() and vg.get("passed") is True)
    return e, v, passed


def _clean(piece: dict) -> dict:
    return {k: v for k, v in piece.items()
            if k not in _META_KEYS and not str(k).startswith("_")}


def exemplars_block(label: str, output_dir: str = "output", days: int = 45, k: int = 2) -> str:
    """Top past pieces for this label that passed BOTH gates, best viral first."""
    found = []
    for path in _content_files(output_dir, days):
        piece = _piece(_load(path), label)
        if not piece:
            continue
        e, v, passed = _scores(piece)
        if passed:
            found.append((v or 0.0, e or 0.0, os.path.basename(path), piece))
    if not found:
        return ""
    found.sort(key=lambda r: (r[0], r[1]), reverse=True)
    lines = [f"TOP-SCORING PAST {label} PIECES (they cleared both gates; match their quality, "
             "do NOT reuse their hooks, angles or wording):"]
    for v, e, name, piece in found[:k]:
        body = json.dumps(_clean(piece), ensure_ascii=False)[:1200]
        lines.append(f"- viral {v:.2f} / editorial {e:.1f} ({name}): {body}")
    return "\n".join(lines)


def _feedback_of(piece: dict) -> list[str]:
    out = []
    ed = piece.get("editorial_score") if isinstance(piece.get("editorial_score"), dict) else {}
    vg = piece.get("viral_potential") if isinstance(piece.get("viral_potential"), dict) else {}
    e, v, passed = _scores(piece)
    if passed:
        return out
    if ed.get("feedback") and (e is None or e < _editorial_threshold()):
        out.append(f"editorial {e}: {ed['feedback']}")
    if vg.get("feedback") and not vg.get("passed"):
        weak = ", ".join(vg.get("weakest") or [])
        out.append(f"viral {v} (weakest: {weak}): {vg['feedback']}")
    for key in ("gate_rejection", "editorial_error"):
        if piece.get(key):
            out.append(f"{key}: {piece[key]}")
    return out


def feedback_block(label: str, output_dir: str = "output", days: int = 3, k: int = 5) -> str:
    notes: list[str] = []
    for path in _content_files(output_dir, days):
        piece = _piece(_load(path), label)
        if piece:
            notes.extend(_feedback_of(piece))
    seen, uniq = set(), []
    for n in notes:
        key = re.sub(r"\W+", " ", n.lower())[:120]
        if key not in seen:
            seen.add(key)
            uniq.append(n[:320])
    parts = []
    if uniq:
        parts.append(f"RECENT GATE FEEDBACK ON {label} (these drafts FAILED; fix every point):\n"
                     + "\n".join(f"- {n}" for n in uniq[:k]))
    try:
        from content_generator.core.obstacle_lessons import prompt_block
        lessons = prompt_block(label)
        if lessons:
            parts.append(lessons)
    except Exception as e:
        logger.debug("[first-pass] lessons unavailable for %s: %s", label, e)
    return "\n\n".join(parts)


def brief(label: str, output_dir: str = "output") -> str:
    """Everything the writer needs to pass first time. Never raises."""
    parts = []
    for fn in (rubric_block, lambda l: exemplars_block(l, output_dir), lambda l: feedback_block(l, output_dir)):
        try:
            block = fn(label)
        except Exception as e:
            logger.debug("[first-pass] brief part unavailable for %s: %s", label, e)
            block = ""
        if block:
            parts.append(block)
    return "\n\n".join(parts)


# ── self-critique with the real scorers ──────────────────────────────────────

def _target_piece(label: str, result):
    if label == "stories" and isinstance(result, dict):
        inner = result.get("story_1")
        return inner if isinstance(inner, dict) else None
    return result if isinstance(result, dict) else None


def evaluate(label: str, result) -> dict:
    """Score a draft with the same gates the editorial loop uses, on a copy."""
    piece = _target_piece(label, result)
    if not piece:
        return {"passed": False, "stage": "shape", "editorial": None, "viral": None,
                "feedback": "draft has no usable piece object"}
    piece = copy.deepcopy(piece)
    from content_generator.scheduler import daily
    from content_generator.core.piece_integrity import ensure_structural_fields
    ensure_structural_fields(piece, label)
    daily._inject_brand_into_piece(label, piece)
    schema = daily._schema_issues(label, piece)
    ok, copy_issues = daily._validate_piece_copy(label, piece)
    if schema or not ok:
        fb = " | ".join(p for p in (("schema: " + "; ".join(schema)) if schema else "",
                                    f"brand/claims: {copy_issues}" if not ok else "") if p)
        return {"passed": False, "stage": "copy", "editorial": None, "viral": None, "feedback": fb}
    from content_generator.agents.editorial import review_content
    from content_generator.core.editorial_engine import normalize_editorial_result
    review = normalize_editorial_result(review_content(piece, label=label))
    e = _num(review.get("overall"))
    if review.get("verdict") != "PASS":
        return {"passed": False, "stage": "editorial", "editorial": e, "viral": None,
                "feedback": str(review.get("feedback") or "")}
    from content_generator.core import viral_gate
    if not viral_gate.enabled():
        return {"passed": True, "stage": "editorial", "editorial": e, "viral": None, "feedback": ""}
    vg = viral_gate.evaluate(label, piece)
    v = _num(vg.get("overall"))
    if vg.get("passed"):
        return {"passed": True, "stage": "viral", "editorial": e, "viral": v, "feedback": ""}
    fb = viral_gate.feedback_for(label, vg, 0) if v is not None else str(vg.get("feedback") or "")
    return {"passed": False, "stage": "viral", "editorial": e, "viral": v, "feedback": fb}


def _rank(ev: dict) -> tuple:
    order = {"shape": 0, "copy": 1, "editorial": 2, "viral": 3}
    return (bool(ev.get("passed")), order.get(ev.get("stage"), 0),
            ev.get("viral") or 0.0, ev.get("editorial") or 0.0)


def rewrite_prompt(base_prompt: str, label: str, draft, ev: dict, round_no: int) -> str:
    from content_generator.core import viral_gate
    body = json.dumps(draft, ensure_ascii=False)[:5000]
    return (
        f"{base_prompt}\n\n"
        f"SELF-CRITIQUE ROUND {round_no}: your previous draft of {label} did NOT clear the gates "
        f"(failed at: {ev.get('stage')}; editorial {ev.get('editorial')} vs {_editorial_threshold():.1f}; "
        f"viral {ev.get('viral')} vs {viral_gate.PASS_MARK:.1f}).\n"
        f"JUDGE FEEDBACK: {str(ev.get('feedback') or '')[:1500]}\n"
        f"PREVIOUS DRAFT JSON:\n{body}\n\n"
        "Rewrite the COMPLETE piece in exactly the same JSON shape so it clears both gates. "
        "Fix every point above, lift the weakest dimensions to 9+, and use a sharper, specific, "
        "honest hook. Keep every brand and claim rule. Return ONLY the JSON object."
    )


def generate(label: str, prompt: str, tokens: int, *, call=None, evaluator=None,
             max_rounds: int | None = None):
    """Draft, then score-and-rewrite up to N rounds. Returns (best_draft, record)."""
    if call is None:
        from content_generator.providers.llm_router import call as call
    draft = call(prompt, label, tokens)  # a first-draft failure propagates exactly as before
    record = {"label": label, "enabled": False, "rounds": 0, "passed": None, "history": []}
    if label not in TARGETS or not self_critique_enabled():
        return draft, record
    evaluator = evaluator or evaluate
    n = max_rounds or rounds()
    record["enabled"] = True
    best, best_ev = draft, None
    current = draft
    for i in range(n):
        try:
            ev = evaluator(label, current)
        except Exception as e:  # a scorer outage is not a verdict; keep the best draft
            logger.warning("[first-pass] %s scoring failed in round %d: %s", label, i + 1, e)
            break
        record["rounds"] = i + 1
        record["history"].append({k: ev.get(k) for k in ("stage", "editorial", "viral", "passed")})
        logger.info("[first-pass] %s round %d/%d: stage=%s editorial=%s viral=%s passed=%s",
                    label, i + 1, n, ev.get("stage"), ev.get("editorial"), ev.get("viral"), ev.get("passed"))
        if best_ev is None or _rank(ev) > _rank(best_ev):
            best, best_ev = current, ev
        if ev.get("passed") or i + 1 >= n or not _budget_left():
            break
        try:
            candidate = call(rewrite_prompt(prompt, label, current, ev, i + 1),
                             f"selfcritique_{label}", tokens)
        except Exception as e:
            logger.warning("[first-pass] %s rewrite failed in round %d: %s", label, i + 1, e)
            break
        if not isinstance(candidate, dict) or not candidate:
            break
        current = candidate
    record["passed"] = bool(best_ev and best_ev.get("passed"))
    record["best"] = {k: (best_ev or {}).get(k) for k in ("stage", "editorial", "viral")}
    return best, record
