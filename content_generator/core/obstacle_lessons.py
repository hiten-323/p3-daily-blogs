"""Persistent obstacle lessons, fed back into generation and regen prompts.

Append a lesson whenever a draft is rejected or a publish is blocked.
Repeated platform+gate+normalized_reason_code rows increment ``count`` instead of
growing a new row. The lessons file is capped at 500 rows (LRU by last_seen).
Prompt text is deduplicated and capped so history cannot blow the context window.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

_MAX_PROMPT = 900
_MAX_LINES = 8
_MAX_LESSONS_FILE_ROWS = 500
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
    if "generic" in text and "hook" in text:
        return "generic_hook"
    if "no tension" in text or "without tension" in text or "lack tension" in text or "no stakes" in text:
        return "tension"
    if "promotional" in text or "sales-led" in text or "too salesy" in text or "primarily promotional" in text:
        return "salesy_follow"
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
    if "visual" in text or "variety" in text or "aesthetic" in text or "render" in text or "layout" in text or "pale_background" in text:
        return "aesthetic"
    if "banned claim" in text or "lab tested" in text or "lab-tested" in text or "zero acidity" in text or "100%" in text or "fresh" in text:
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


def normalized_reason_code(reason: str, gate: str = "", feedback: str = "") -> str:
    """Extract a canonical normalized reason code (not full free-text feedback)."""
    combined = f"{reason} {feedback} {gate}".lower()
    
    # Specific banned claim extraction
    if "100%" in combined:
        return "banned_claim:100%"
    if "fresh" in combined:
        return "banned_claim:fresh"
    if "lab tested" in combined or "lab-tested" in combined:
        return "banned_claim:lab_tested"
    if "single-origin" in combined or "single origin" in combined:
        return "banned_claim:single_origin"
    if "zero acidity" in combined:
        return "banned_claim:zero_acidity"
    if "bean" in combined and "green bean" in combined:
        return "banned_claim:bean_wording"

    # Provider failures: distinguish by provider name so each provider has its own failure tracker
    if "provider" in combined or gate in ("provider", "creative") or "hf_" in combined:
        for prov in (
            "hf_cogvideo", "hf_hunyuan", "hf_wan_i2v", "hf_wan", "hf_ltx",
            "kaggle_bank", "pixazo", "runway", "pexels", "pixabay",
            "gemini", "groq", "cerebras", "xai", "mistral", "openrouter",
            "nvidia", "cloudflare"
        ):
            if prov in combined:
                return f"provider:{prov}"
        
    code = classify(f"{reason} {feedback}")
    if code != "other":
        return code
    if gate and gate.strip().lower() not in ("editorial", "viral", "schema", "other"):
        return gate.strip().lower().replace(" ", "_")
    return code


def _lesson_id(platform: str, gate: str, code: str) -> str:
    return f"{platform}|{gate}|{code}"


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
    compacted = compact_lessons(data)
    blob = json.dumps(compacted, indent=2, sort_keys=True) + "\n"
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

    code = normalized_reason_code(reason, gate, feedback)
    key = _lesson_id(platform, gate, code)

    path = lessons_path()
    data = _load(path)
    lessons = [row for row in data.get("lessons") or [] if isinstance(row, dict)]
    found = next((row for row in lessons if row.get("id") == key), None)
    
    sample = (feedback or reason)[:300]
    
    if found is None:
        samples = [sample] if sample else []
        found = {
            "id": key,
            "platform": platform,
            "label": label,
            "stage": str(stage or "generation"),
            "gate": gate,
            "reason": reason,
            "code": code,
            "feedback": feedback,
            "recent_samples": samples,
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
        samples = list(found.get("recent_samples") or [])
        if sample and sample not in samples:
            samples.append(sample)
        found["recent_samples"] = samples[-3:]
        if reason:
            found["reason"] = reason
        if feedback:
            found["feedback"] = feedback
        if fix:
            found["fix"] = fix
        if status:
            found["status"] = status
        elif found.get("status") == "fixed":
            found["status"] = "gate_holding"
        found["stage"] = str(stage or found.get("stage") or "generation")
        found["code"] = code
        found["label"] = label

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


def compact_lessons(data: dict) -> dict:
    """Merge rows with the same (platform, gate, normalized_reason_code) into one row.
    
    Capped at 500 rows (LRU by last_seen).
    """
    lessons = [row for row in data.get("lessons") or [] if isinstance(row, dict)]
    by_key: dict[str, dict] = {}

    for row in lessons:
        platform = str(row.get("platform") or platform_for(row.get("label", "")))
        gate = str(row.get("gate") or classify(row.get("reason", "")))
        raw_reason = str(row.get("reason") or "")
        raw_feedback = str(row.get("feedback") or "")
        code = row.get("code") or normalized_reason_code(raw_reason, gate, raw_feedback)
        key = _lesson_id(platform, gate, code)

        count = int(row.get("count") or 1)
        first_seen = str(row.get("first_seen") or "")
        last_seen = str(row.get("last_seen") or "")
        sample = scrub(raw_feedback or raw_reason)[:300]

        if key not in by_key:
            merged = dict(row)
            merged["id"] = key
            merged["platform"] = platform
            merged["gate"] = gate
            merged["code"] = code
            merged["reason"] = raw_reason
            merged["feedback"] = raw_feedback
            merged["count"] = count
            merged["first_seen"] = first_seen
            merged["last_seen"] = last_seen
            existing_samples = list(row.get("recent_samples") or [])
            if sample and sample not in existing_samples:
                existing_samples.append(sample)
            merged["recent_samples"] = existing_samples[-3:] if existing_samples else ([sample] if sample else [])
            by_key[key] = merged
        else:
            cur = by_key[key]
            cur["count"] = int(cur.get("count") or 1) + count
            if last_seen and (not cur.get("last_seen") or last_seen > str(cur.get("last_seen"))):
                cur["last_seen"] = last_seen
            if first_seen and (not cur.get("first_seen") or first_seen < str(cur.get("first_seen"))):
                cur["first_seen"] = first_seen
            if not cur.get("fix") and row.get("fix"):
                cur["fix"] = row["fix"]
            if raw_reason:
                cur["reason"] = raw_reason
            if raw_feedback:
                cur["feedback"] = raw_feedback
            samples = list(cur.get("recent_samples") or [])
            if sample and sample not in samples:
                samples.append(sample)
            cur["recent_samples"] = samples[-3:]

    # Sort: pinned banned claims stay on top, then order by count desc, last_seen desc
    sorted_lessons = sorted(
        by_key.values(),
        key=lambda r: (
            1 if r.get("gate") == "banned_claim" else 0,
            int(r.get("count") or 0),
            str(r.get("last_seen") or ""),
        ),
        reverse=True,
    )
    
    # Cap at 500 rows
    capped = sorted_lessons[:_MAX_LESSONS_FILE_ROWS]
    return {"version": 1, "lessons": capped}


def prompt_block(label: str) -> str:
    """Recent lessons for this platform, deduplicated and capped. External rows are omitted."""
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

    # Pinned claim bans stay in the prompt
    pinned = [row for row in rows if row.get("gate") == "banned_claim"]
    # Top lessons sorted by occurrence count and recency (e.g. generic_hook, llm_viral, ladder_exhausted)
    rest = [row for row in rows if row.get("gate") != "banned_claim"]
    rest.sort(key=lambda row: (int(row.get("count") or 0), str(row.get("last_seen") or "")), reverse=True)

    if len(pinned) >= _MAX_LINES:
        chosen = pinned[:_MAX_LINES]
    else:
        chosen = pinned + rest[:(_MAX_LINES - len(pinned))]

    lines = ["OBSTACLE LESSONS (do not repeat these; a repeat fails the gate):"]
    seen_lines = set()

    for row in chosen:
        reason = scrub(row.get("reason") or row.get("code") or "")
        fix = scrub(row.get("fix") or "")
        feedback = scrub(row.get("feedback") or "")
        bit = f"- {row.get('gate')}: {reason}"
        if feedback and feedback.lower() not in reason.lower():
            bit += f" Judge: {feedback}"
        if fix:
            bit += f" Fix: {fix}"
        bit = bit[:280]

        if bit not in seen_lines:
            seen_lines.add(bit)
            lines.append(bit)

    text = "\n".join(lines)
    if len(text) <= _MAX_PROMPT:
        return text
    return text[:_MAX_PROMPT].rsplit("\n", 1)[0]
