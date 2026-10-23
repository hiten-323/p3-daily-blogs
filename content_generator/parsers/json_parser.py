"""
JSON extraction with json_repair as primary strategy, multi-strategy fallback.
json_repair is an optional dependency — if not installed, falls back to
regex-based extraction with trailing-comma repair.

Reasoning models (Nemotron Ultra on 2026-10-23) put a think trace in front of
the score object, and the trace itself may contain a brace example. The answer
is the last JSON object outside that trace. A trace with no object is not a
score: callers must keep holding the piece.
"""
import re
import json
import logging

logger = logging.getLogger(__name__)

# Optional dependency — graceful fallback if not installed
try:
    import json_repair as _json_repair
    _HAS_JSON_REPAIR = True
except ImportError:
    _json_repair = None
    _HAS_JSON_REPAIR = False
    logger.debug("json_repair not installed — using built-in fallback parser")

_CLOSED_REASONING = re.compile(
    r"<(?:think|thinking|reasoning)\b[^>]*>[\s\S]*?</(?:think|thinking|reasoning)>",
    re.I,
)


def _sanitize_control_chars(text: str) -> str:
    """Replace literal control characters inside JSON string values."""
    _ESC = {'\n': '\\n', '\t': '\\t', '\r': '\\r', '\b': '\\b', '\f': '\\f'}
    result = []
    in_str = escaping = False
    for ch in text:
        if escaping:
            result.append(ch); escaping = False; continue
        if ch == '\\':
            escaping = True; result.append(ch); continue
        if ch == '"':
            in_str = not in_str; result.append(ch); continue
        if in_str and ord(ch) < 0x20:
            result.append(_ESC.get(ch, '')); continue
        result.append(ch)
    return ''.join(result)


def _strip_closed_reasoning(text: str) -> str:
    """Drop finished think/reasoning blocks. An unclosed trace is left intact
    so a truncated reply still fails closed instead of losing the only clue."""
    return _CLOSED_REASONING.sub("", text)


def _top_level_objects(text: str) -> list[str]:
    """Balanced top-level {...} slices, ignoring braces inside strings."""
    objects: list[str] = []
    start = None
    depth = 0
    in_str = escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i + 1])
                start = None
    return objects


def _loads_object(text: str) -> dict | None:
    cleaned = _sanitize_control_chars(text.strip())
    if not cleaned:
        return None
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        if not _HAS_JSON_REPAIR:
            return None
        try:
            result = _json_repair.loads(cleaned)
        except Exception:
            return None
    return result if isinstance(result, dict) else None


def _extract_from(text: str) -> dict | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    direct = _loads_object(cleaned)
    if direct is not None:
        return direct
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        fenced = _loads_object(fence.group(1).strip())
        if fenced is not None:
            return fenced
    # Last object: reasoning models put scratch JSON in the trace and the
    # real score after it. A greedy first-brace match joins those and fails.
    for candidate in reversed(_top_level_objects(cleaned)):
        parsed = _loads_object(candidate)
        if parsed is not None:
            return parsed
    return None


def extract(raw: str) -> dict:
    """
    Parse JSON from a raw LLM response string.
    Uses json_repair if available (handles malformed JSON automatically),
    otherwise falls back to the legacy multi-strategy extractor.
    """
    if not isinstance(raw, str):
        raw = "" if raw is None else str(raw)
    stripped = _strip_closed_reasoning(raw)
    seen: list[str] = []
    for text in (stripped, raw):
        if text in seen:
            continue
        seen.append(text)
        found = _extract_from(text)
        if found is not None:
            return found
    raise ValueError(f"No JSON object found. First 300 chars: {raw[:300]}")
