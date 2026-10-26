"""Evidence-backed cross-platform post measurement and publication reconciliation.

Only confirmed-live ledger records are reconciled. Metrics are fetched from each
platform's own API; missing permissions/data remain unknown and are never coerced
to zero. Every successful observation updates one post-level learning sample so
24h data can improve tomorrow's generation without inflating the sample count.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from config.api_versions import META_GRAPH_BASE

logger = logging.getLogger(__name__)
LEARNING_DIR = Path(os.getenv("LEARNING_DIR", "output/learning"))
POSTS_PATH = LEARNING_DIR / "published_posts.json"
LEDGER_PATH = LEARNING_DIR / "publishing_ledger.json"
WINDOWS = (("24h", 24), ("72h", 72), ("7d", 168))
# A window is only comparable within its collection grace period. Late API reads
# must not be mislabeled as historical 24h/72h measurements.
WINDOW_MAX_AGE_HOURS = {"24h": 48, "72h": 120, "7d": 240}
MAX_ATTEMPTS = 5
_TIMEOUT = 20

# These aliases preserve the native platform for reporting while selecting the
# appropriate metrics adapter.
_ALIASES = {
    "instagram": "instagram",
    "instagram_video": "instagram",
    "instagram_reel": "instagram",
    "instagram_story": "instagram_story",
    "facebook": "facebook",
    "facebook_reel": "facebook",
    "threads": "threads",
    "youtube": "youtube",
    "linkedin": "linkedin",
    "blog": "shopify",
    "shopify": "shopify",
}


def _read_json(path: Path, fallback: Any) -> Any:
    """Use a fallback only for an absent file; never silently reset corrupt state."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback
    except OSError:
        logger.exception("[platform-learning] cannot read state file %s", path)
        raise
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.error("[platform-learning] refusing corrupt state file %s: %s", path, exc)
        raise ValueError(f"Refusing to overwrite malformed JSON state: {path}") from exc


def _write_json(path: Path, value: Any) -> None:
    """Atomically replace state with a unique same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                logger.warning("[platform-learning] could not clean temp state file %s", tmp_name)


def _platform(raw: Any, asset_id: str = "") -> str:
    name = str(raw or "").strip().lower()
    if not name and asset_id:
        name = str(asset_id).split("_", 1)[0].lower()
    return _ALIASES.get(name, name)


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        return None


def _age_hours(published_at: Any, now: dt.datetime) -> float:
    published = _parse_time(published_at)
    if published is None:
        return 0.0
    current = now
    if current.tzinfo is None:
        current = current.astimezone()
    current = current.astimezone(dt.timezone.utc)
    return max(0.0, (current - published).total_seconds() / 3600.0)


def reconcile_verified_publications() -> dict[str, int]:
    """Merge verified-live publication ledger records into the measurement tracker."""
    ledger = _read_json(LEDGER_PATH, {})
    if not isinstance(ledger, dict) or not isinstance(ledger.get("records", {}), dict):
        raise ValueError("Invalid publishing ledger schema; refusing reconciliation")
    records = ledger.get("records", {})
    posts = _read_json(POSTS_PATH, [])
    if not isinstance(posts, list) or any(not isinstance(p, dict) for p in posts):
        raise ValueError("Invalid published-post tracker schema; refusing to overwrite state")
    # Migrate historical tracker rows whose platform was omitted by older runs.
    by_id = {str(p.get("media_id")): p for p in posts if p.get("media_id")}
    added = enriched = migrated = skipped = 0

    for old_post in posts:
        inferred = _platform(old_post.get("platform"), str(old_post.get("asset_id") or ""))
        if inferred and str(old_post.get("platform") or "").lower() != inferred:
            old_post["platform"] = inferred
            migrated += 1

    for key, rec in (records.items() if isinstance(records, dict) else []):
        if not isinstance(rec, dict) or rec.get("status") != "VERIFIED_LIVE":
            skipped += 1
            continue
        media_id = str(rec.get("remote_id") or "").strip()
        if not media_id:
            skipped += 1
            continue
        raw_platform = str(rec.get("platform") or "")
        platform = _platform(raw_platform)
        if not platform:
            skipped += 1
            continue
        history = rec.get("history") or []
        publish_events = [
            event for event in history
            if isinstance(event, dict)
            and event.get("event") == "attempt_finished"
            and event.get("remote_id")
            and str(event.get("status") or "") in {"PUBLISHED_UNVERIFIED", "VERIFIED_LIVE"}
        ]
        # Prefer the actual successful publish event over a later readback
        # timestamp; otherwise a delayed verification shifts the measurement age.
        published_at = (
            publish_events[-1].get("at") if publish_events
            else rec.get("verified_at") or rec.get("updated_at") or rec.get("last_verification_at") or ""
        )
        # Ledger timestamps are often UTC-aware; keep a normalized UTC value so
        # the measurement scheduler can compare them consistently.
        parsed = _parse_time(published_at)
        published_at = parsed.isoformat(timespec="seconds") if parsed else str(published_at)
        post = by_id.get(media_id)
        if post is None:
            content_id = str(rec.get("content_id") or "")
            day = rec.get("day_number")
            asset_id = f"{platform}_day{day}" if day is not None else (content_id or f"{platform}_{media_id}")
            post = {
                "media_id": media_id,
                "asset_id": asset_id,
                "platform": platform,
                "track": "brand",
                "hook": "",
                "topic": "",
                "format": str(rec.get("slot") or "post"),
                "published_at": published_at,
                "permalink": str(rec.get("url") or ""),
                "ledger_key": str(key),
                "publication_status": "VERIFIED_LIVE",
                "insights_recorded": False,
                "measurement_snapshots": [],
                "fetch_attempts_by_window": {},
                "failed_windows": [],
                "measurement_status": "pending",
            }
            posts.append(post)
            by_id[media_id] = post
            added += 1
        else:
            changed = False
            for field, value in (
                ("platform", platform),
                ("published_at", published_at),
                ("permalink", str(rec.get("url") or "")),
                ("ledger_key", str(key)),
                ("publication_status", "VERIFIED_LIVE"),
            ):
                if value and not post.get(field):
                    post[field] = value
                    changed = True
            # Backfill old tracker rows with a missing/incorrect platform label.
            if post.get("platform") != platform and _platform(post.get("platform"), post.get("asset_id")) == platform:
                post["platform"] = platform
                changed = True
            if changed:
                enriched += 1

    if added or enriched or migrated:
        _write_json(POSTS_PATH, posts)
    return {"added": added, "enriched": enriched, "migrated_legacy": migrated, "skipped_unverified": skipped, "total": len(posts)}


def _request_json(url: str, *, headers: dict[str, str] | None = None) -> dict | None:
    request = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        return payload if isinstance(payload, dict) else None
    except urllib.error.HTTPError as exc:
        # Do not log request URLs: some providers place tokens in query strings.
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        logger.warning("[platform-learning] API returned HTTP %s: %s", exc.code, detail)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("[platform-learning] API request failed: %s", type(exc).__name__)
    return None


def _meta_base() -> str:
    return str(META_GRAPH_BASE).rstrip("/")


def _meta_get(object_id: str, token: str, fields: str) -> dict | None:
    params = urllib.parse.urlencode({"fields": fields, "access_token": token})
    return _request_json(f"{_meta_base()}/{urllib.parse.quote(object_id, safe='_') }?{params}")


_YOUTUBE_TOKEN: str | None = None
_YOUTUBE_TOKEN_EXPIRES_AT = 0.0


def _youtube_access_token() -> str | None:
    """Use the configured API key or refresh the repository's existing YouTube OAuth token."""
    global _YOUTUBE_TOKEN, _YOUTUBE_TOKEN_EXPIRES_AT
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        return None
    import time
    if _YOUTUBE_TOKEN and time.time() < _YOUTUBE_TOKEN_EXPIRES_AT - 60:
        return _YOUTUBE_TOKEN
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        token = payload.get("access_token")
        if token:
            _YOUTUBE_TOKEN = str(token)
            _YOUTUBE_TOKEN_EXPIRES_AT = time.time() + int(payload.get("expires_in", 3600))
            return _YOUTUBE_TOKEN
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("[platform-learning] YouTube OAuth refresh failed: %s", type(exc).__name__)
    return None


def _fetch_youtube(media_id: str) -> dict | None:
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    access_token = None if key else _youtube_access_token()
    if not key and not access_token:
        return None
    params = urllib.parse.urlencode({"part": "statistics", "id": media_id, **({"key": key} if key else {})})
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    data = _request_json(f"https://www.googleapis.com/youtube/v3/videos?{params}", headers=headers)
    items = (data or {}).get("items") or []
    if not items:
        return None
    stats = items[0].get("statistics") or {}
    out = {}
    for source, target in (("viewCount", "views"), ("likeCount", "likes"), ("commentCount", "comments")):
        if source in stats:
            try:
                out[target] = int(stats[source])
            except (ValueError, TypeError):
                pass
    return out or None


def _fetch_facebook(media_id: str) -> dict | None:
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("FACEBOOK_ACCESS_TOKEN")
    if not token:
        return None
    # Keep engagement fields independent from Insights permissions: a missing
    # insights scope must not discard otherwise valid like/comment/share counts.
    data = _meta_get(media_id, token, "shares,likes.summary(true),comments.summary(true)")
    if not data:
        return None
    out: dict[str, Any] = {}
    query = urllib.parse.urlencode({
        "metric": "post_impressions,post_engaged_users,post_video_views",
        "access_token": token,
    })
    insights = _request_json(
        f"{_meta_base()}/{urllib.parse.quote(media_id, safe='_')}/insights?{query}"
    )
    if isinstance(data.get("shares"), dict) and "count" in data["shares"]:
        out["shares"] = data["shares"]["count"]
    likes = (data.get("likes") or {}).get("summary") or {}
    comments = (data.get("comments") or {}).get("summary") or {}
    if "total_count" in likes:
        out["likes"] = likes["total_count"]
    if "total_count" in comments:
        out["comments"] = comments["total_count"]
    for item in ((insights or {}).get("data") or []):
        values = item.get("values") or []
        if not values:
            continue
        value = values[0].get("value")
        name = item.get("name")
        if value is None:
            continue
        if name == "post_impressions":
            out["impressions"] = value
        elif name == "post_video_views":
            out["views"] = value
        elif name == "post_engaged_users":
            out["engaged_users"] = value
    return out or None


def _fetch_threads(media_id: str) -> dict | None:
    token = os.getenv("THREADS_ACCESS_TOKEN")
    if not token:
        return None
    params = urllib.parse.urlencode({
        "metric": "views,likes,replies,reposts,quotes",
        "access_token": token,
    })
    base = os.getenv("THREADS_GRAPH_BASE", "https://graph.threads.net/v1.0").rstrip("/")
    data = _request_json(f"{base}/{urllib.parse.quote(media_id, safe='_')}/insights?{params}")
    if not data or not isinstance(data.get("data"), list):
        return None
    out: dict[str, Any] = {}
    aliases = {"views": "views", "likes": "likes", "replies": "comments"}
    for item in data["data"]:
        raw_name = str(item.get("name") or "")
        name = aliases.get(raw_name)
        values = item.get("values") or []
        if name and values and values[0].get("value") is not None:
            out[name] = values[0]["value"]
        elif raw_name in {"reposts", "quotes"} and values and values[0].get("value") is not None:
            out["shares"] = int(out.get("shares") or 0) + int(values[0]["value"])
    return out or None


def _fetch_linkedin(media_id: str) -> dict | None:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN") or os.getenv("LI_API_ACCESS")
    version = os.getenv("LINKEDIN_VERSION") or os.getenv("LI_API_VERSION") or "202610"
    if not token:
        return None
    encoded = urllib.parse.quote(media_id, safe=":")
    data = _request_json(
        f"https://api.linkedin.com/rest/socialActions/{encoded}",
        headers={
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Accept": "application/json",
        },
    )
    if not data:
        return None
    out: dict[str, Any] = {}
    likes = data.get("likesSummary") or {}
    comments = data.get("commentsSummary") or {}
    if likes.get("totalLikes") is not None:
        out["likes"] = likes["totalLikes"]
    if comments.get("totalFirstLevelComments") is not None:
        out["comments"] = comments["totalFirstLevelComments"]
    return out or None


def _fetch_platform_metrics(post: dict) -> tuple[dict | None, str]:
    platform = _platform(post.get("platform"), post.get("asset_id"))
    media_id = str(post.get("media_id") or "").strip()
    if not media_id:
        return None, "missing_media_id"
    if platform == "youtube":
        if not ((os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")) or (os.getenv("YOUTUBE_CLIENT_ID") and os.getenv("YOUTUBE_CLIENT_SECRET") and os.getenv("YOUTUBE_REFRESH_TOKEN"))):
            return None, "missing_youtube_credentials"
        metrics = _fetch_youtube(media_id)
    elif platform == "facebook":
        if not (os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("FACEBOOK_ACCESS_TOKEN")):
            return None, "missing_facebook_page_token"
        metrics = _fetch_facebook(media_id)
    elif platform == "threads":
        if not os.getenv("THREADS_ACCESS_TOKEN"):
            return None, "missing_threads_access_token"
        metrics = _fetch_threads(media_id)
    elif platform == "linkedin":
        if not (os.getenv("LINKEDIN_ACCESS_TOKEN") or os.getenv("LI_API_ACCESS")) or not os.getenv("LINKEDIN_VERSION"):
            return None, "missing_linkedin_token_or_version"
        metrics = _fetch_linkedin(media_id)
    elif platform == "instagram_story":
        # A Story is short-lived; use the same native Meta media-insights adapter
        # while it is still available, and never pretend a post-expiry absence is zero.
        if not os.getenv("INSTAGRAM_ACCESS_TOKEN"):
            return None, "missing_instagram_access_token"
        try:
            from content_generator.analytics.insights_fetcher import _fetch_media_insights
            metrics = _fetch_media_insights(media_id)
        except Exception as exc:
            logger.debug("[platform-learning] Story measurement unavailable: %s", type(exc).__name__)
            metrics = None
        return (metrics, "measured") if metrics else (None, "api_returned_no_metrics")
    elif platform == "shopify":
        return None, "shopify_blog_analytics_not_configured"
    elif platform == "instagram":
        return None, "handled_by_instagram_insights_fetcher"
    else:
        return None, "unsupported_platform"
    return (metrics, "measured") if metrics else (None, "api_returned_no_metrics")


def fetch_pending_platform_metrics(now: dt.datetime | None = None) -> dict[str, int]:
    """Collect one due native-platform observation and update the same post-level sample."""
    posts = _read_json(POSTS_PATH, [])
    if not isinstance(posts, list) or any(not isinstance(p, dict) for p in posts):
        raise ValueError("Invalid published-post tracker schema; refusing to overwrite state")
    current = now or dt.datetime.now().astimezone()
    snapshots_written = recorded = pending = failed = unsupported = 0
    from content_generator.core.learning_engine import record_performance

    for post in posts:
        if not isinstance(post, dict):
            continue
        platform = _platform(post.get("platform"), post.get("asset_id"))
        post["platform"] = platform or post.get("platform") or "unknown"
        if post.get("insights_recorded") or post.get("measurement_terminal") or platform == "instagram":
            continue
        if _parse_time(post.get("published_at")) is None:
            post["measurement_status"] = "missing_or_invalid_publication_timestamp"
            post["measurement_terminal"] = True
            unsupported += 1
            continue
        age = _age_hours(post.get("published_at"), current)
        snapshots = post.setdefault("measurement_snapshots", [])
        if platform == "instagram_story" and age > 24 and "24h" not in {
            str(s.get("window")) for s in snapshots if isinstance(s, dict)
        }:
            post["measurement_status"] = "story_measurement_window_missed"
            post["measurement_terminal"] = True
            unsupported += 1
            continue
        completed = {str(s.get("window")) for s in snapshots if isinstance(s, dict)}
        abandoned = set(post.get("failed_windows") or [])
        missed = post.setdefault("missed_windows", {})
        for name, hours in WINDOWS:
            max_age = 24 if platform == "instagram_story" and name == "24h" else WINDOW_MAX_AGE_HOURS[name]
            if name not in completed | abandoned and age > max_age:
                abandoned.add(name)
                missed[name] = "outside_comparable_collection_window"
        post["failed_windows"] = sorted(abandoned)
        if age > WINDOW_MAX_AGE_HOURS["7d"] and not post.get("insights_recorded"):
            post["measurement_terminal"] = True
            post["measurement_status"] = "too_old_for_comparable_window"
            continue
        due = next((
            (name, hours) for name, hours in WINDOWS
            if name not in completed | abandoned
            and age >= (20 if platform == "instagram_story" and name == "24h" else hours)
            and age <= (24 if platform == "instagram_story" and name == "24h" else WINDOW_MAX_AGE_HOURS[name])
        ), None)
        if due is None:
            continue
        window, hours = due
        metrics, status = _fetch_platform_metrics(post)
        post["measurement_status"] = status
        if not metrics:
            if status in {"story_metrics_not_available_after_expiry", "shopify_blog_analytics_not_configured", "unsupported_platform"}:
                post["measurement_status"] = status
                unsupported += 1
                # Terminal, explicit status; never spin through retry attempts for
                # platforms that have no configured/available native measurement.
                post.setdefault("failed_windows", []).append(window)
                post["failed_windows"] = sorted(set(post["failed_windows"]))
                if platform in {"instagram_story", "shopify"} or status == "unsupported_platform":
                    post["measurement_terminal"] = True
                continue
            attempts = post.setdefault("fetch_attempts_by_window", {})
            attempts[window] = int(attempts.get(window, 0)) + 1
            failed += 1
            if attempts[window] >= MAX_ATTEMPTS:
                post.setdefault("failed_windows", []).append(window)
                post["failed_windows"] = sorted(set(post["failed_windows"]))
                if platform == "instagram_story":
                    post["measurement_terminal"] = True
            else:
                pending += 1
            continue

        snapshot = {
            "window": window,
            "target_hours": hours,
            "measured_at": current.isoformat(timespec="seconds"),
            "actual_age_hours": round(age, 2),
            "metrics": {k: v for k, v in metrics.items() if v is not None},
            "source": platform + "_native_api",
        }
        snapshots.append(snapshot)
        snapshots_written += 1
        terminal_window = "24h" if platform == "instagram_story" else "7d"
        # Each observation updates one sample keyed by the publication ID. This
        # makes the 24h signal available to tomorrow's prompts while keeping 72h
        # and 7d refinements from masquerading as new independent posts.
        record_performance(
            asset_id=str(post.get("asset_id") or post.get("media_id")),
            track=str(post.get("track") or "brand"),
            hook=str(post.get("hook") or ""),
            topic=str(post.get("topic") or ""),
            format_used=str(post.get("format") or platform),
            posted_at=str(post.get("published_at") or ""),
            metrics=snapshot["metrics"],
            notes=f"auto-recorded from {window} {platform} native API observation",
            kpi_at_creation=str(post.get("kpi_at_creation") or ""),
            policy_version=str(post.get("policy_version") or ""),
            attention_mechanism=str(post.get("attention_mechanism") or ""),
            hook_strategy=str(post.get("hook_strategy") or ""),
            payoff_type=str(post.get("payoff_type") or ""),
            decision_version=str(post.get("decision_version") or ""),
            scroller_state=str(post.get("scroller_state") or ""),
            psychology_frame=str(post.get("psychology_frame") or ""),
            platform=platform,
            observation_window=window,
            publication_id=str(post.get("media_id") or ""),
        )
        recorded += 1
        if window == terminal_window:
            post["insights_recorded"] = True
            if platform == "instagram_story":
                post["measurement_terminal"] = True
    _write_json(POSTS_PATH, posts)
    result = {
        "snapshots": snapshots_written,
        "recorded": recorded,
        "pending": pending,
        "failed": failed,
        "unsupported": unsupported,
        "posts": len(posts),
    }
    logger.info("[platform-learning] %s", result)
    return result
