"""Persistent obstacle lessons, fed back into generation and regen prompts.

Append a lesson whenever a draft is rejected or a publish is blocked.
Repeated platform+label+gate+reason rows increment ``count`` instead of
growing a new row. Prompt text is capped so a long history cannot blow
the context window. External credential failures are stored and skipped
in prompts.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path

_MAX_PROMPT = 900
_MAX_LINES = 8
_SECRET = re.compile(
    r"(bearer\s+\S+|EAA[A-Za-z0-9]+|sk-[A-Za-z0-9]+|ghp_[A-Za-z0-9]+|api[_-]?key\s*[:=]\s*\S+)",
    re.I,
)

_PLATFORM = {
    "facebook_post": "facebook",
    "threads_post": "threads",
    "linkedin_post": "linkedin",
    "yt_short": "youtube",
    "blog_post": "shopify",
    "carousel": "instagram",
    "instagram_post": "instagram",
    "reel_1": "instagram",
    "reel_2": "instagram",
    "growth_reel": "instagram",
    "stories": "instagram_story",
    "sales_story": "instagram_campaign",
    "sales_reel": "instagram_campaign",
}


def platform_for(label: str) -> str:
    return _PLATFORM.get(str(label or ""), str(label or "unknown"))


def lessons_path() -> Path:
    override = os.getenv("OBSTACLE_LESSONS_PATH", "").strip()
    if override:
        return Path(override)
    return Path("output") / "learning" / "obstacle_lessons.json"


def _writes_enabled() -> bool:
    if os.getenv("OBSTACLE_LESSONS_PATH", "").strip():
        return True
    return not os.getenv("PYTEST_CURRENT_TEST")


def scrub(text: str) -> str:
    cleaned = _SECRET.sub("[redacted]", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500]


def classify(feedback: str) -> str:
    text = str(feedback or "").lower()
    if "ladder" in text:
        return "ladder_exhausted"
    if "viral_scoring_failed" in text or "scoring_failed" in text or "no json" in text:
        return "provider"
    if "viral" in text or "honesty" in text:
        return "llm_viral"
    if "product truth" in text or "fssai" in text or "chicory" in text or "per-cup" in text:
        return "product_truth"
    if "freeze-dried" in text or "process" in text or "agglomerat" in text:
        return "process_match"
    if "schema" in text or "field required" in text or "duration_s" in text:
        return "schema"
    if "provenance" in text or "unregistered_image" in text:
        return "provenance"
    if "visual" in text or "variety" in text or "aesthetic" in text or "render" in text:
        return "aesthetic"
    if "banned claim" in text or "lab tested" in text or "lab-tested" in text or "zero acidity" in text:
        return "banned_claim"
    if "empty content" in text or "480" in text or "brand" in text or "brand mention" in text:
        return "brand"
    if "payoff" in text or "curiosity" in text or "hook/payoff" in text:
        return "payoff"
    if "north-star" in text or "shareability" in text or "no copy" in text:
        return "shareability"
    if "editorial" in text or "score" in text:
        return "editorial"
    if "401" in text or "403" in text or "429" in text or "provider" in text:
        return "provider"
    return "other"


def _norm_reason(reason: str) -> str:
    return re.sub(r"\s+", " ", scrub(reason).lower()).strip()[:180]


def _lesson_id(platform: str, label: str, gate: str, reason: str) -> str:
    return f"{platform}|{label}|{gate}|{_norm_reason(reason)}"


def _empty() -> dict:
    return {"version": 1, "lessons": []}


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("lessons"), list):
        return _empty()
    return data


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix="lessons-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(blob)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record(platform: str, label: str, stage: str, gate: str, reason: str,
           feedback: str = "", *, fix: str = "", status: str = "",
           count: int = 1, first_seen: str = "", last_seen: str = "") -> dict | None:
    """Append or bump one lesson. Returns the stored row, or None when writes are off."""
    if not _writes_enabled():
        return None
    platform = str(platform or platform_for(label))
    label = str(label or "")
    gate = str(gate or classify(reason))
    reason = scrub(reason) or "unspecified"
    feedback = scrub(feedback)
    fix = scrub(fix)
    today = date.today().isoformat()
    first_seen = first_seen or today
    last_seen = last_seen or today
    try:
        bump = max(1, int(count))
    except (TypeError, ValueError):
        bump = 1
    path = lessons_path()
    data = _load(path)
    lessons = [row for row in data.get("lessons") or [] if isinstance(row, dict)]
    key = _lesson_id(platform, label, gate, reason)
    found = next((row for row in lessons if row.get("id") == key), None)
    if found is None:
        found = {
            "id": key,
            "platform": platform,
            "label": label,
            "stage": str(stage or "generation"),
            "gate": gate,
            "reason": reason,
            "feedback": feedback,
            "fix": fix,
            "count": bump,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "status": status or "gate_holding",
        }
        lessons.append(found)
    else:
        found["count"] = int(found.get("count") or 0) + bump
        found["last_seen"] = last_seen
        if feedback:
            found["feedback"] = feedback
        if fix:
            found["fix"] = fix
        if status:
            found["status"] = status
        elif found.get("status") == "fixed":
            found["status"] = "gate_holding"
        found["stage"] = str(stage or found.get("stage") or "generation")
    data["version"] = 1
    data["lessons"] = lessons
    _save(path, data)
    return found


def mark_fixed(label: str, fix: str, gate: str = "") -> None:
    """Note what cleared the latest open lesson for this asset."""
    if not _writes_enabled():
        return
    path = lessons_path()
    data = _load(path)
    lessons = [row for row in data.get("lessons") or [] if isinstance(row, dict)]
    platform = platform_for(label)
    candidates = [
        row for row in lessons
        if row.get("label") == label and row.get("platform") == platform
        and row.get("status") != "external"
        and (not gate or row.get("gate") == gate)
    ]
    if not candidates:
        return
    row = candidates[-1]
    row["status"] = "fixed"
    row["fix"] = scrub(fix) or row.get("fix") or ""
    row["last_seen"] = date.today().isoformat()
    data["lessons"] = lessons
    _save(path, data)


def prompt_block(label: str) -> str:
    """Recent lessons for this platform, capped. External rows are omitted."""
    platform = platform_for(label)
    data = _load(lessons_path())
    rows = [
        row for row in data.get("lessons") or []
        if isinstance(row, dict)
        and row.get("platform") == platform
        and row.get("status") != "external"
    ]
    if not rows:
        return ""
    # Standing claim bans stay in the prompt when newer rows fill the line cap.
    pinned = [row for row in rows if row.get("gate") == "banned_claim"]
    rest = [row for row in rows if row.get("gate") != "banned_claim"]
    rest.sort(key=lambda row: (str(row.get("last_seen") or ""), int(row.get("count") or 0)))
    if len(pinned) >= _MAX_LINES:
        chosen = pinned[:_MAX_LINES]
    else:
        chosen = pinned + rest[-(_MAX_LINES - len(pinned)):]
    lines = ["OBSTACLE LESSONS (do not repeat these; a repeat fails the gate):"]
    for row in chosen:
        reason = scrub(row.get("reason") or "")
        fix = scrub(row.get("fix") or "")
        feedback = scrub(row.get("feedback") or "")
        bit = f"- {row.get('gate')}: {reason}"
        if feedback and feedback.lower() not in reason.lower():
            bit += f" Judge: {feedback}"
        if fix:
            bit += f" Fix: {fix}"
        lines.append(bit[:280])
    text = "\n".join(lines)
    if len(text) <= _MAX_PROMPT:
        return text
    return text[:_MAX_PROMPT].rsplit("\n", 1)[0]
