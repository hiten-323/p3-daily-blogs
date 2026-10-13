"""Fail-closed visual QA for every surface, before any publish.

A frame that fails is re-rendered on the next scene and the other side of
the prop. After QUALITY_MAX_REGEN extra tries it is BLOCKED and moved out of
the publish folder. It is never posted.
"""
from __future__ import annotations

import logging
import os
import re
import shutil

logger = logging.getLogger(__name__)

FORMATS = {
    "story": (1080, 1920),
    "feed": (1080, 1350),
    "square": (1080, 1080),
    "yt": (1280, 720),
}

# id, image_results key, format, platform, whether the value is a list
SURFACES = (
    {"id": "story", "key": "story_frame", "format": "story", "platform": "instagram"},
    {"id": "reel", "key": "reel", "format": "story", "platform": "instagram"},
    {"id": "carousel", "key": "carousel", "format": "feed", "platform": "instagram", "many": True},
    {"id": "feed", "key": "instagram_post", "format": "feed", "platform": "instagram"},
    {"id": "facebook", "key": "facebook_post", "format": "feed", "platform": "facebook"},
    {"id": "linkedin", "key": "linkedin_post", "format": "square", "platform": "linkedin"},
    {"id": "threads", "key": "threads_post", "format": "feed", "platform": "threads"},
    {"id": "yt_thumbnail", "key": "yt_thumbnail", "format": "yt", "platform": "youtube"},
)

_ALLOWED_PERCENTS = {100, 70, 30}
_STAT = re.compile(r"(?:₹|rs\.?\s*)\s*\d|\bwaste\b|\bevery\s+week\b", re.I)
_PERCENT = re.compile(r"\b(\d+)\s*(?:%|percent)\b", re.I)
_WRONG_HANDLE = re.compile(r"@puritybeans\b", re.I)


def retry_limit() -> int:
    try:
        return max(0, int(os.getenv("QUALITY_MAX_REGEN", "3")))
    except (TypeError, ValueError):
        return 3


def copy_and_mask_issues(geometry: dict | None) -> list[str]:
    """Handle, unverified stat hooks, and a mask that did not pass integrity."""
    if not isinstance(geometry, dict) or geometry.get("lifestyle_required") is False:
        return []
    issues: list[str] = []
    if geometry.get("jar_required") is not False:
        if geometry.get("mask_ok") is not True:
            issues.append("mask_integrity")
        for name in geometry.get("mask_issues") or []:
            text = str(name or "").strip()
            if text and text not in issues:
                issues.append(text)
    copy = geometry.get("on_image") if isinstance(geometry.get("on_image"), dict) else None
    if not copy:
        issues.append("on_image_copy_missing")
        return issues
    from config.brand_config import platform_handle

    handle = platform_handle("instagram")
    cta = str(copy.get("cta") or "")
    blob = " ".join(str(copy.get(key) or "") for key in ("hook", "benefit", "offer", "cta"))
    if not handle or handle.lower() not in cta.lower():
        issues.append("wrong_handle")
    elif _WRONG_HANDLE.search(blob) and "puritybeans" not in handle.lower():
        issues.append("wrong_handle")
    spoken = " ".join(str(copy.get(key) or "") for key in ("hook", "benefit", "cta"))
    if _STAT.search(spoken):
        issues.append("unverified_stat_hook")
    percents = {int(value) for value in _PERCENT.findall(spoken)}
    if percents - _ALLOWED_PERCENTS:
        issues.append("unverified_stat_hook")
    return issues


def surface_row(content: dict, surface_id: str) -> dict | None:
    gate = content.get("visual_gate") if isinstance(content, dict) else None
    if not isinstance(gate, dict):
        return None
    for row in gate.get("surfaces") or []:
        if isinstance(row, dict) and row.get("id") == surface_id:
            return row
    return None


def surface_decision(content: dict, surface_id: str) -> str | None:
    row = surface_row(content, surface_id)
    if not row:
        return None
    return str(row.get("decision") or "") or None


def surface_path(content: dict, surface_id: str) -> str | None:
    row = surface_row(content, surface_id)
    if not row or row.get("decision") != "PASS":
        return None
    path = row.get("path")
    return path if isinstance(path, str) and path else None


def platform_blocked(content: dict, platform: str) -> bool:
    gate = content.get("visual_gate") if isinstance(content, dict) else None
    if not isinstance(gate, dict):
        return False
    return str(platform or "").lower() in set(gate.get("blocked_platforms") or [])


def _quarantine(path: str) -> None:
    if not path or not os.path.isfile(path):
        return
    folder = os.path.join(os.path.dirname(path), "_blocked")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, os.path.basename(path))
    shutil.move(path, dest)
    sidecar = path + ".jar.json"
    if os.path.isfile(sidecar):
        shutil.move(sidecar, dest + ".jar.json")
    logger.error("[visual-gate] quarantined %s", os.path.basename(path))


def _audit(path: str) -> dict:
    from content_generator.creative.jar_frame import audit_product_image
    if not path:
        return {"ok": False, "issues": ["missing_frame"]}
    return audit_product_image(path)


def _headline(content: dict, surface_id: str, day: int) -> str:
    try:
        if surface_id == "story":
            from content_generator.publisher.surface_copy import story_frame_copy
            return str(story_frame_copy(content, day=day).get("headline") or "")
        if surface_id in ("facebook", "linkedin", "threads"):
            from content_generator.publisher.surface_copy import on_image_hook
            return str(on_image_hook(content, surface_id if surface_id != "feed" else "instagram") or "")
        if surface_id == "reel":
            reel = (content.get("reels") or [{}])[0] if content.get("reels") else {}
            reel = reel if isinstance(reel, dict) else {}
            return str(reel.get("hook_text") or reel.get("hook") or "")
        if surface_id == "yt_thumbnail":
            short = content.get("yt_short") if isinstance(content.get("yt_short"), dict) else {}
            return str(short.get("title") or short.get("hook") or "")
    except Exception as exc:
        logger.debug("[visual-gate] headline for %s skipped: %s", surface_id, exc)
    post = content.get("instagram_post") if isinstance(content.get("instagram_post"), dict) else {}
    return str(post.get("hook_line") or post.get("hook") or "")


def _render_frame(content, day, surface, attempt: int, label: str, out_dir: str | None) -> str | None:
    from content_generator.creative.jar_frame import compose_conversion_frame
    width, height = FORMATS[surface["format"]]
    return compose_conversion_frame(
        headline=_headline(content, surface["id"], day),
        product=content.get("featured_product"),
        day=int(day) + (int(attempt) // 2),
        width=width,
        height=height,
        label=label,
        format_name="story" if surface["format"] == "story" else surface["format"],
        out_dir=out_dir,
        attempt=int(attempt) % 2,
    )


def _label_of(path: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"_\d{4}-\d{2}-\d{2}$", "", name)


def render_passing_frame(
    content: dict,
    day: int,
    surface_id: str,
    *,
    label: str,
    out_dir: str | None = None,
    existing: str | None = None,
) -> dict:
    """Audit one frame. Retry with a new scene and placement, then BLOCK."""
    surface = next(row for row in SURFACES if row["id"] == surface_id)
    budget = retry_limit()
    last = {"ok": False, "issues": ["missing_frame"], "path": existing, "attempts": 0}
    start = 0
    if existing:
        last = _audit(existing)
        last["path"] = existing
        last["attempts"] = 1
        if last.get("ok"):
            last["decision"] = "PASS"
            return last
        start = 1
    for attempt in range(start, budget + 1):
        path = _render_frame(content, day, surface, attempt, label, out_dir)
        if not path:
            last = {"ok": False, "issues": ["render_failed"], "path": None, "attempts": attempt + 1}
            continue
        last = _audit(path)
        last["path"] = path
        last["attempts"] = attempt + 1
        if last.get("ok"):
            last["decision"] = "PASS"
            return last
    last["decision"] = "BLOCKED"
    _quarantine(str(last.get("path") or existing or ""))
    last["path"] = None
    return last


def _paths(value) -> list[str]:
    if isinstance(value, list):
        return [path for path in value if isinstance(path, str) and path]
    if isinstance(value, str) and value:
        return [value]
    return []


def _gate_carousel(content, day, paths: list[str]) -> dict:
    budget = retry_limit()
    current = list(paths)
    issues: list[str] = []

    def _check(frames: list[str]) -> tuple[bool, list[str]]:
        found = []
        for path in frames:
            result = _audit(path)
            if not result.get("ok"):
                found.extend(result.get("issues") or ["jar_qa_failed"])
        return not found, found

    slides = (content.get("carousel") or {}).get("slides") if isinstance(content.get("carousel"), dict) else None
    start = 1 if current else 0
    if current:
        ok, issues = _check(current)
        if ok:
            return {"decision": "PASS", "paths": current, "issues": [], "attempts": 1}
    attempts = 1 if current else 0
    for attempt in range(start, budget + 1):
        if not slides:
            break
        from content_generator.creative.real_jar_composer import compose_carousel_slides
        rendered = compose_carousel_slides(
            slides,
            int(day) + (attempt // 2),
            product=content.get("featured_product"),
            attempt=attempt % 2,
        )
        attempts = attempt + 1
        current = [path for path in rendered or [] if path]
        if not current:
            issues = ["render_failed"]
            continue
        ok, issues = _check(current)
        if ok:
            return {"decision": "PASS", "paths": current, "issues": [], "attempts": attempts}
    for path in current:
        _quarantine(path)
    return {"decision": "BLOCKED", "paths": [], "issues": issues or ["visual_qa_failed"], "attempts": attempts}


def _blocked_platforms(rows: list[dict]) -> list[str]:
    by_id = {row["id"]: row for row in rows}
    blocked = []
    for surface in SURFACES:
        row = by_id.get(surface["id"])
        if not row or row.get("decision") != "BLOCKED":
            continue
        if surface["platform"] == "instagram":
            continue
        if surface["platform"] not in blocked:
            blocked.append(surface["platform"])
    feed = by_id.get("feed")
    carousel = by_id.get("carousel")
    feed_pass = bool(feed and feed.get("decision") == "PASS")
    carousel_pass = bool(carousel and carousel.get("decision") == "PASS")
    feed_block = bool(feed and feed.get("decision") == "BLOCKED")
    carousel_block = bool(carousel and carousel.get("decision") == "BLOCKED")
    if not feed_pass and not carousel_pass and (feed_block or carousel_block):
        blocked.append("instagram")
    return blocked


def enforce_visual_gate(content: dict, image_results: dict | None = None, day: int = 0) -> dict:
    """Audit every surface. Re-render failures. BLOCK whatever still fails."""
    image_results = image_results if isinstance(image_results, dict) else {}
    content = content if isinstance(content, dict) else {}
    rows = []
    for surface in SURFACES:
        key = surface["key"]
        existing = _paths(image_results.get(key))
        if surface.get("many"):
            if not existing and not (content.get("carousel") or {}).get("slides"):
                continue
            gated = _gate_carousel(content, day, existing)
            rows.append({
                "id": surface["id"],
                "key": key,
                "platform": surface["platform"],
                "decision": gated["decision"],
                "paths": gated.get("paths") or [],
                "issues": gated.get("issues") or [],
                "attempts": gated.get("attempts") or 0,
            })
            continue
        label = _label_of(existing[0]) if existing else f"{key}_day{int(day)}"
        out_dir = os.path.dirname(existing[0]) if existing else None
        gated = render_passing_frame(
            content, day, surface["id"], label=label, out_dir=out_dir, existing=existing[0] if existing else None,
        )
        rows.append({
            "id": surface["id"],
            "key": key,
            "platform": surface["platform"],
            "decision": gated.get("decision"),
            "path": gated.get("path"),
            "issues": gated.get("issues") or [],
            "attempts": gated.get("attempts") or 0,
        })
    blocked_surfaces = [row["id"] for row in rows if row.get("decision") == "BLOCKED"]
    summary = {
        "passes": not blocked_surfaces,
        "retry_limit": retry_limit(),
        "surfaces": rows,
        "blocked_surfaces": blocked_surfaces,
        "blocked_platforms": _blocked_platforms(rows),
    }
    for row in rows:
        if row.get("decision") != "PASS":
            logger.error("[visual-gate] %s BLOCKED after %s tries: %s", row["id"], row.get("attempts"), row.get("issues"))
    return summary
