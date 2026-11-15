"""Per-post outcome tracker: real audience results -> next generation, per platform.

Every VERIFIED_LIVE post already lands in ``published_posts.json`` and gets
measurement snapshots (early / 24h / 72h / 7d) from the native platform APIs.
This module turns those snapshots into decisions the next generation can act
on, separately for each platform:

* joins each measured post back to the piece that produced it (hook, angle,
  template, product, editorial score) using that day's ``content_<date>.json``,
  so even posts tracked without a hook (Facebook, Threads, LinkedIn) can teach;
* scores each post against the median of comparable posts on the same
  platform, the same metric basis and the same measurement window, so an
  early read is never compared with a 7-day read;
* groups those relative scores by template, angle, hook strategy and piece
  type, and names winners to reuse and losers to retire;
* reports measurement gaps (missing scopes/APIs) instead of inventing zeros.

Real audience data ranks first. Editorial scores are only used as a labelled
tie-break or when a platform has no audience data at all.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import logging
import os
import re
import statistics
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LEARNING_DIR = Path(os.getenv("LEARNING_DIR", "output/learning"))
OUTPUT_DIR = Path(os.getenv("CONTENT_OUTPUT_DIR", "output"))
OUTCOMES_FILE = "post_outcomes.json"
LOOKBACK_DAYS = int(os.getenv("OUTCOME_LOOKBACK_DAYS", "30"))
MIN_COHORT = 3          # comparable posts needed before a relative score exists
MIN_GROUP = 2           # posts behind a reuse/retire verdict
PROVEN_GROUP = 5        # below this a verdict is labelled provisional
WIN_RATIO = 1.25
LOSE_RATIO = 0.70
WINDOW_RANK = {"early": 0, "24h": 1, "72h": 2, "7d": 3}

# Piece labels a published record can come from, per platform.
PLATFORM_LABELS = {
    "instagram": ("growth_reel", "reel_1", "instagram_post", "carousel"),
    "instagram_story": ("stories",),
    "facebook": ("facebook_post", "growth_reel", "reel_1"),
    "threads": ("threads_post",),
    "linkedin": ("linkedin_post",),
    "youtube": ("yt_short",),
    "shopify": ("blog_post",),
}
DEFAULT_LABEL = {
    "instagram_story": "stories", "facebook": "facebook_post", "threads": "threads_post",
    "linkedin": "linkedin_post", "youtube": "yt_short", "shopify": "blog_post",
}
_FORMAT_LABEL = {
    "carousel": "carousel", "instagram_post": "instagram_post", "growth_reel": "growth_reel",
    "reel_1": "reel_1", "reel": "reel_1", "yt_short": "yt_short",
}
_GAP_HINTS = {
    "instagram": "Instagram reach, views, saves, shares and watch time need instagram_manage_insights on the Instagram token; likes and comments are measured without it.",
    "facebook": "Facebook post likes, comments and impressions need pages_read_engagement (and read_insights) on the Page token.",
    "youtube": "YouTube likes/comments need YOUTUBE_API_KEY (optional) or a youtube.readonly OAuth scope; the public view count is read without it.",
    "linkedin": "LinkedIn reactions/comments need LINKEDIN_ACCESS_TOKEN with r_member_social or organization social read access plus LINKEDIN_VERSION.",
    "shopify": "Blog sessions are not measured; UTM link clicks arrive through Shopify order attribution only.",
    "instagram_story": "Story insights also need instagram_manage_insights and must be read within 24h.",
}


# ── small helpers ────────────────────────────────────────────────────────────

def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except (OSError, ValueError) as exc:
        logger.warning("[outcomes] unreadable %s: %s", path, type(exc).__name__)
        return fallback


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(dt.timezone.utc)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def text_similarity(a: str, b: str) -> float:
    """Token Jaccard blended with character trigram Jaccard (0..1)."""
    wa, wb = set(_words(a)), set(_words(b))
    if not wa or not wb:
        return 0.0
    tok = len(wa & wb) / len(wa | wb)
    sa, sb = " ".join(_words(a)), " ".join(_words(b))
    ga = {sa[i:i + 3] for i in range(max(0, len(sa) - 2))}
    gb = {sb[i:i + 3] for i in range(max(0, len(sb) - 2))}
    tri = len(ga & gb) / len(ga | gb) if ga and gb else 0.0
    return round(0.5 * tok + 0.5 * tri, 4)


_LABELISH = re.compile(r"^[A-Za-z_]+(?:[ _-][A-Za-z]+){0,2}$")


def piece_hook(piece: dict) -> str:
    """The audience-facing opening line. Archetype labels ("Direct Accusation") are not hooks."""
    if not isinstance(piece, dict):
        return ""
    for key in ("hook", "hook_spoken", "chosen_hook", "hook_text", "hook_line", "title", "headline", "text"):
        value = piece.get(key)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
            if key in ("chosen_hook", "hook_text") and len(value.split()) <= 3 and _LABELISH.match(value):
                continue
            return value.split("\n")[0][:220]
    story = piece.get("story_1") if isinstance(piece.get("story_1"), dict) else None
    if story:
        return " ".join(str(story.get(k) or "") for k in ("headline", "subtext")).strip()[:220]
    return ""


def piece_template(piece: dict) -> str:
    if not isinstance(piece, dict):
        return ""
    for key in ("ad_template_id", "growth_template_id", "template_id", "video_template_id"):
        value = piece.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def piece_angle(piece: dict) -> str:
    if not isinstance(piece, dict):
        return ""
    for key in ("angle", "save_mechanic", "objective", "psychology_frame"):
        value = piece.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value.strip().lower())[:60]
    return ""


def content_pieces(content: dict) -> dict[str, dict]:
    """label -> piece for one day's content object."""
    out: dict[str, dict] = {}
    if not isinstance(content, dict):
        return out
    reels = content.get("reels") if isinstance(content.get("reels"), list) else []
    if reels and isinstance(reels[0], dict) and reels[0]:
        out["reel_1"] = reels[0]
    for label in ("growth_reel", "instagram_post", "carousel", "stories", "facebook_post",
                  "threads_post", "linkedin_post", "yt_short", "blog_post"):
        piece = content.get(label)
        if isinstance(piece, dict) and piece:
            out[label] = piece
    return out


def load_content_by_day(output_dir: Path | None = None, days: int = 45) -> dict[int, dict]:
    root = Path(output_dir or OUTPUT_DIR)
    by_day: dict[int, dict] = {}
    files = sorted(glob.glob(str(root / "content_20*.json")))[-days:]
    for path in files:
        data = _read_json(Path(path), {})
        try:
            day = int(data.get("day_number") or 0)
        except (TypeError, ValueError):
            day = 0
        if day:
            by_day[day] = data
    return by_day


def _known_templates() -> set[str]:
    try:
        from content_generator.creative.ad_creator import TEMPLATES
        return set(TEMPLATES)
    except Exception:
        return {"fast_cut_curiosity"}


def _day_from_asset(asset_id: str) -> int:
    match = re.search(r"day(\d+)", str(asset_id or ""))
    return int(match.group(1)) if match else 0


def match_piece(post: dict, content: dict | None) -> tuple[str, dict]:
    """Find the piece that produced a published post: hook match first, then format."""
    platform = str(post.get("platform") or "").lower()
    pieces = content_pieces(content or {})
    candidates = [lbl for lbl in PLATFORM_LABELS.get(platform, ()) if lbl in pieces]
    hook = str(post.get("hook") or "")
    if hook and candidates:
        scored = sorted(((text_similarity(hook, piece_hook(pieces[l])), l) for l in candidates), reverse=True)
        if scored and scored[0][0] >= 0.35:
            return scored[0][1], pieces[scored[0][1]]
    fmt_label = _FORMAT_LABEL.get(str(post.get("format") or "").lower())
    if fmt_label and fmt_label in pieces and (not candidates or fmt_label in candidates):
        return fmt_label, pieces[fmt_label]
    default = DEFAULT_LABEL.get(platform)
    if default and default in pieces:
        return default, pieces[default]
    if fmt_label:
        return fmt_label, {}
    return default or "", {}


# ── scoring ──────────────────────────────────────────────────────────────────

def latest_snapshot(post: dict) -> dict | None:
    snaps = [s for s in (post.get("measurement_snapshots") or []) if isinstance(s, dict) and s.get("metrics")]
    if not snaps:
        return None
    return max(snaps, key=lambda s: WINDOW_RANK.get(str(s.get("window")), -1))


def _num(metrics: dict, key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audience_value(metrics: dict) -> tuple[str, float] | None:
    """(basis, value) from real audience metrics. None when nothing was observed.

    reach basis: distribution weighted by interaction rate (views/reach known).
    engagement basis: weighted interactions only (no reach permission).
    """
    m = metrics or {}
    reach = next((v for v in (_num(m, "views"), _num(m, "reach"), _num(m, "impressions")) if v is not None), None)
    parts = {"likes": 1.0, "comments": 3.0, "shares": 4.0, "saves": 4.0,
             "follows_gained": 8.0, "website_clicks": 6.0, "orders": 40.0}
    observed = {k: _num(m, k) for k in parts if _num(m, k) is not None}
    engagement = sum(parts[k] * v for k, v in observed.items())
    if reach is not None:
        rate = engagement / max(reach, 1.0)
        return "reach", reach * (1.0 + 10.0 * min(rate, 0.5))
    if observed:
        return "engagement", engagement
    return None


def build_outcomes(now: dt.datetime | None = None, *, posts: list | None = None,
                   content_by_day: dict[int, dict] | None = None) -> dict:
    current = (now or dt.datetime.now().astimezone()).astimezone(dt.timezone.utc)
    if posts is None:
        posts = _read_json(LEARNING_DIR / "published_posts.json", [])
    if content_by_day is None:
        content_by_day = load_content_by_day()
    rows: list[dict] = []
    coverage: dict[str, dict] = defaultdict(lambda: {"posts": 0, "measured": 0, "statuses": Counter(), "metrics_seen": Counter()})
    for post in posts if isinstance(posts, list) else []:
        if not isinstance(post, dict):
            continue
        published = _parse_time(post.get("published_at"))
        if published is None or (current - published).days > LOOKBACK_DAYS:
            continue
        platform = str(post.get("platform") or "").lower() or "unknown"
        cov = coverage[platform]
        cov["posts"] += 1
        snap = latest_snapshot(post)
        if not snap:
            cov["statuses"][str(post.get("measurement_status") or "awaiting_first_window")] += 1
        day = _day_from_asset(post.get("asset_id"))
        label, piece = match_piece(post, content_by_day.get(day))
        row = {
            "platform": platform,
            "label": label,
            "day": day,
            "media_id": str(post.get("media_id") or ""),
            "published_at": published.isoformat(),
            "hook": (str(post.get("hook") or "") or piece_hook(piece))[:200],
            "angle": piece_angle(piece),
            "template": piece_template(piece) or (str(post.get("format")) if str(post.get("format") or "") in _known_templates() else ""),
            "hook_strategy": str(post.get("hook_strategy") or ""),
            "attention_mechanism": str(post.get("attention_mechanism") or ""),
            "product": str((piece or {}).get("featured_product") or ""),
            "editorial_score": _num(piece or {}, "editorial_score"),
            "window": None,
            "metrics": {},
            "basis": None,
            "value": None,
            "relative": None,
        }
        if snap:
            metrics = {k: v for k, v in (snap.get("metrics") or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            row["window"] = str(snap.get("window"))
            row["metrics"] = metrics
            av = audience_value(metrics)
            if av:
                row["basis"], row["value"] = av
                cov["measured"] += 1
                cov["metrics_seen"].update(metrics.keys())
        rows.append(row)

    cohorts: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if row["value"] is not None:
            cohorts[(row["platform"], row["basis"], row["window"])].append(row)
    for members in cohorts.values():
        if len(members) < MIN_COHORT:
            continue
        median = statistics.median(r["value"] for r in members)
        for r in members:
            r["relative"] = round(r["value"] / median, 3) if median > 0 else (1.0 if r["value"] == 0 else 2.0)

    platforms: dict[str, dict] = {}
    for platform in sorted({r["platform"] for r in rows}):
        prow = [r for r in rows if r["platform"] == platform]
        platforms[platform] = _platform_verdicts(platform, prow, coverage[platform])
    result = {
        "generated_at": current.isoformat(timespec="seconds"),
        "lookback_days": LOOKBACK_DAYS,
        "platforms": platforms,
        "posts": rows,
    }
    return result


def _group_verdicts(rows: list[dict], dimension: str) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        key = str(r.get(dimension) or "").strip()
        if key and r.get("relative") is not None:
            groups[key].append(float(r["relative"]))
    winners, losers = [], []
    for key, values in groups.items():
        if len(values) < MIN_GROUP:
            continue
        mean = round(sum(values) / len(values), 2)
        entry = {"dimension": dimension, "value": key, "ratio": mean, "n": len(values),
                 "provisional": len(values) < PROVEN_GROUP}
        if mean >= WIN_RATIO:
            winners.append(entry)
        elif mean <= LOSE_RATIO:
            losers.append(entry)
    winners.sort(key=lambda e: (-e["ratio"], -e["n"]))
    losers.sort(key=lambda e: (e["ratio"], -e["n"]))
    return winners, losers


def _platform_verdicts(platform: str, rows: list[dict], cov: dict) -> dict:
    ranked = [r for r in rows if r.get("relative") is not None]
    winners, losers = [], []
    for dimension in ("template", "angle", "label", "hook_strategy", "attention_mechanism"):
        w, l = _group_verdicts(ranked, dimension)
        winners += w
        losers += l
    # Real audience data first; editorial score only breaks ties.
    ranked.sort(key=lambda r: (r["relative"], r.get("editorial_score") or 0.0), reverse=True)
    top = [_brief(r) for r in ranked[:3]]
    bottom = [_brief(r) for r in ranked[-3:]][::-1] if len(ranked) >= 4 else []
    editorial_only = []
    if not ranked:
        scored = [r for r in rows if r.get("editorial_score") is not None]
        scored.sort(key=lambda r: r["editorial_score"], reverse=True)
        editorial_only = [_brief(r) for r in scored[:2]]
    seen = dict(cov.get("metrics_seen") or {})
    gaps = []
    if cov.get("posts") and not cov.get("measured"):
        gaps.append("no audience metrics measured yet")
    if platform == "instagram" and "reach" not in seen and "views" not in seen:
        gaps.append(_GAP_HINTS["instagram"])
    elif platform in _GAP_HINTS and not cov.get("measured"):
        gaps.append(_GAP_HINTS[platform])
    statuses = dict(Counter(cov.get("statuses") or {}).most_common(4))
    return {
        "posts": cov.get("posts", 0),
        "measured": cov.get("measured", 0),
        "ranked": len(ranked),
        "metrics_seen": sorted(seen),
        "unmeasured_statuses": statuses,
        "winners": winners[:6],
        "losers": losers[:6],
        "top_posts": top,
        "bottom_posts": bottom,
        "editorial_only": editorial_only,
        "gaps": gaps,
    }


def _brief(row: dict) -> dict:
    keep = ("views", "reach", "likes", "comments", "shares", "saves", "follows_gained")
    return {
        "label": row.get("label"), "hook": row.get("hook", "")[:140], "template": row.get("template"),
        "angle": row.get("angle"), "relative": row.get("relative"), "window": row.get("window"),
        "editorial_score": row.get("editorial_score"),
        "metrics": {k: row["metrics"][k] for k in keep if k in (row.get("metrics") or {})},
    }


def refresh(now: dt.datetime | None = None) -> dict:
    """Rebuild and persist the outcome file. Never raises into the pipeline."""
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("POST_OUTCOMES_WRITE"):
        return {"skipped": "test"}
    try:
        result = build_outcomes(now)
        _write_json(LEARNING_DIR / OUTCOMES_FILE, {k: v for k, v in result.items() if k != "posts"} | {
            "posts": result["posts"][-200:],
        })
        summary = {p: {"posts": v["posts"], "measured": v["measured"], "winners": len(v["winners"]),
                       "losers": len(v["losers"])} for p, v in result["platforms"].items()}
        logger.info("[outcomes] %s", summary)
        _log_gap_lessons(result)
        return summary
    except Exception as exc:
        logger.warning("[outcomes] refresh failed: %s", type(exc).__name__)
        return {"error": type(exc).__name__}


def _log_gap_lessons(result: dict) -> None:
    try:
        from content_generator.core.obstacle_lessons import record
    except Exception:
        return
    for platform, verdict in (result.get("platforms") or {}).items():
        for gap in verdict.get("gaps") or []:
            if gap == "no audience metrics measured yet":
                continue
            try:
                record(platform, f"{platform}_measurement", "measurement", "metrics_gap",
                       gap, "Learning on this platform uses whatever real metrics are readable; missing ones stay unknown.",
                       fix="Grant the read permission named in the reason.")
            except Exception:
                return


def load() -> dict:
    data = _read_json(LEARNING_DIR / OUTCOMES_FILE, {})
    return data if isinstance(data, dict) else {}


_PROMPT_PLATFORM = {
    "reel": "instagram", "reel_1": "instagram", "growth_reel": "instagram", "carousel": "instagram",
    "ig_single": "instagram", "instagram_post": "instagram", "instagram": "instagram",
    "stories": "instagram_story", "story": "instagram_story", "facebook": "facebook",
    "facebook_post": "facebook", "threads": "threads", "threads_post": "threads",
    "linkedin": "linkedin", "linkedin_post": "linkedin", "yt_short": "youtube", "youtube": "youtube",
    "blog": "shopify", "blog_post": "shopify",
}


def prompt_block(platform_or_label: str, data: dict | None = None, max_items: int = 3) -> str:
    """Concrete reuse/retire lessons from this platform's own real posts."""
    platform = _PROMPT_PLATFORM.get(str(platform_or_label or "").lower(), str(platform_or_label or "").lower())
    data = data if data is not None else load()
    verdict = (data.get("platforms") or {}).get(platform)
    if not verdict or not verdict.get("posts"):
        return ""
    lines = [f"LEARNED FROM OUR REAL {platform.upper()} POSTS (last {data.get('lookback_days', LOOKBACK_DAYS)} days; "
             f"{verdict.get('measured', 0)} of {verdict.get('posts', 0)} posts measured; metrics: "
             f"{', '.join(verdict.get('metrics_seen') or []) or 'none yet'}):"]
    def _fmt(e):
        tag = " provisional" if e.get("provisional") else ""
        return f"{e['dimension']}={e['value']} ({e['ratio']}x median, n={e['n']}{tag})"
    if verdict.get("winners"):
        lines.append("REUSE these structures (beat this platform's median): " + "; ".join(_fmt(e) for e in verdict["winners"][:max_items]))
    if verdict.get("losers"):
        lines.append("RETIRE these structures (well below median): " + "; ".join(_fmt(e) for e in verdict["losers"][:max_items]))
    for post in (verdict.get("top_posts") or [])[:2]:
        if post.get("hook"):
            lines.append(f"  + best: \"{post['hook'][:110]}\" {post.get('metrics')} — reuse the mechanism, never the words")
    for post in (verdict.get("bottom_posts") or [])[:2]:
        if post.get("hook"):
            lines.append(f"  - weakest: \"{post['hook'][:110]}\" {post.get('metrics')} — do not repeat this opening shape")
    if not verdict.get("ranked") and verdict.get("editorial_only"):
        lines.append("No audience data yet on this platform; editorial scores only (weak signal). Test a clearly different angle.")
    for gap in (verdict.get("gaps") or [])[:1]:
        lines.append(f"Measurement gap: {gap}")
    return "\n".join(lines) if len(lines) > 1 else ""


def template_scores(platforms: tuple[str, ...] = ("instagram", "facebook", "youtube"),
                    data: dict | None = None) -> dict[str, dict]:
    """template id -> {ratio, n} from real video outcomes across the given platforms."""
    data = data if data is not None else load()
    values: dict[str, list[float]] = defaultdict(list)
    for row in data.get("posts") or []:
        if row.get("platform") in platforms and row.get("template") and row.get("relative") is not None:
            values[str(row["template"])].append(float(row["relative"]))
    return {k: {"ratio": round(sum(v) / len(v), 3), "n": len(v)} for k, v in values.items()}
