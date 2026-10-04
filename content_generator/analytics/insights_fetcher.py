"""Instagram Insights Fetcher — truthful, staged measurement for the learning loop.

Every published media object can be observed at 24h, 72h and 7d. Intermediate
snapshots are retained on the published-post record; only the 7d observation is
promoted to the learning log so one post cannot count as three independent
experiments. Account-level metrics remain account-level and are never fabricated
into post-level attribution.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import urllib.parse
import urllib.error
import urllib.request

from config.api_versions import META_GRAPH_BASE

logger = logging.getLogger(__name__)
_GRAPH_API = META_GRAPH_BASE
_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_POSTS_PATH = os.path.join(_LEARNING_DIR, "published_posts.json")
_TIMEOUT = 30
MIN_AGE_HOURS = 20
MAX_FETCH_ATTEMPTS = 5
MEASUREMENT_WINDOWS = (("24h", 24), ("72h", 72), ("7d", 168))


def _load_posts() -> list[dict]:
    if not os.path.exists(_POSTS_PATH):
        return []
    try:
        with open(_POSTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[insights] Could not read published posts: %s", e)
        return []


def _save_posts(posts: list[dict]) -> None:
    os.makedirs(_LEARNING_DIR, exist_ok=True)
    with open(_POSTS_PATH, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def track_published_post(
    media_id: str,
    asset_id: str,
    track: str = "brand",
    hook: str = "",
    topic: str = "",
    format_used: str = "",
    hashtags: str = "",
    kpi_at_creation: str = "",
    policy_version: str = "",
    attention_mechanism: str = "",
    scroller_state: str = "",
    psychology_frame: str = "",
    hook_strategy: str = "",
    payoff_type: str = "",
    decision_version: str = "",
) -> None:
    if not media_id:
        return
    posts = _load_posts()
    if any(p.get("media_id") == media_id for p in posts):
        return
    posts.append({
        "media_id": media_id,
        "asset_id": asset_id,
        "track": track,
        "hook": hook,
        "topic": topic,
        "kpi_at_creation": kpi_at_creation,
        "policy_version": policy_version,
        "attention_mechanism": attention_mechanism,
        "scroller_state": scroller_state,
        "psychology_frame": psychology_frame,
        "hook_strategy": hook_strategy,
        "payoff_type": payoff_type,
        "decision_version": decision_version,
        "format": format_used,
        "hashtags": hashtags,
        "published_at": datetime.datetime.now().isoformat(timespec="seconds"),
        # Legacy field retained for compatibility. It becomes true only after
        # the 7d learning observation is successfully recorded.
        "insights_recorded": False,
        "measurement_snapshots": [],
        "fetch_attempts_by_window": {},
    })
    _save_posts(posts)
    logger.info("[insights] Tracking published post %s (%s)", media_id, asset_id)


# ── Graph API circuit breaker ────────────────────────────────────────────────
# 2026-08-21: a generate run spent 90s issuing ~220 requests, every one of which
# returned HTTP 400. It then tripped the 60s watchdog, and the TimeoutError took
# content generation down with it — nothing learned, nothing published.
#
# Consecutive total failure is a systemic condition: an expired token, a missing
# scope, an account type change. The 56th identical 400 tells us nothing the 8th
# did not, so the breaker stops the run and reports once. This is what actually
# bounds the step's runtime — the watchdog timer cannot interrupt a running body.
_MAX_CONSECUTIVE_FAILURES = 8
_consecutive_failures = 0
_circuit_open = False


def _reset_circuit() -> None:
    """Called at the start of each run so one bad day never poisons the next."""
    global _consecutive_failures, _circuit_open
    _consecutive_failures = 0
    _circuit_open = False


def _error_detail(exc: Exception, token: str | None) -> str:
    """
    Meta puts the actual reason in the response body. str(HTTPError) is only
    "HTTP Error 400: Bad Request", which names no cause and cannot be acted on —
    every 400 in this engine's history was logged that way, so the cause was
    never visible. Read the body, and redact the token in case it is echoed.
    """
    body = ""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", "replace").strip()
        except Exception:
            body = ""
    if body and token:
        body = body.replace(token, "***")
    return f"{exc} — {body[:500]}" if body else str(exc)


def _note_failure(path: str, detail: str) -> None:
    global _consecutive_failures, _circuit_open
    _consecutive_failures += 1
    logger.warning("[insights] Graph API call failed (%s): %s", path, detail)
    if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES and not _circuit_open:
        _circuit_open = True
        logger.error(
            "[insights] %d consecutive Graph API failures — stopping this run. "
            "This is a systemic fault, not per-post. Last error: %s",
            _consecutive_failures, detail,
        )


def _graph_get(path: str, params: dict, bypass_circuit: bool = False) -> dict | None:
    global _consecutive_failures
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token or (_circuit_open and not bypass_circuit):
        return None
    url = f"{_GRAPH_API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "PurityBeans/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        payload = json.loads(resp.read().decode("utf-8"))
        _consecutive_failures = 0
        return payload
    except Exception as e:
        _note_failure(path, _error_detail(e, token))
        return None


# ── Why is insights failing? ─────────────────────────────────────────────────
# Per Meta's Instagram Media Insights reference, an app on the Facebook Login
# path (host graph.facebook.com, which is what config/api_versions.py sets)
# needs instagram_basic AND instagram_manage_insights AND pages_read_engagement.
# followers_count only needs instagram_basic — which is exactly the split the
# 2026-08-21 log showed: followers_count returned 98 while all 55 /insights
# calls returned 400.
#
# That is an inference, and the engine should not run on inferences. These three
# calls make it a statement of fact. They run only once, and only when the
# breaker has already tripped, so a healthy run pays nothing.
_INSIGHTS_SCOPES = ("instagram_basic", "instagram_manage_insights", "pages_read_engagement")


def diagnose_access() -> dict:
    """Report token scopes and account type after a systemic insights failure."""
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not token:
        return {}

    logger.error("[insights] --- ACCESS DIAGNOSTIC (insights failed systemically) ---")
    findings: dict = {}

    debug = _graph_get(
        "debug_token", {"input_token": token}, bypass_circuit=True
    ) or {}
    info = debug.get("data") or {}
    granted = set(info.get("scopes") or [])
    if granted:
        findings["scopes"] = sorted(granted)
        missing = [s for s in _INSIGHTS_SCOPES if s not in granted]
        findings["missing_scopes"] = missing
        logger.error("[insights] token type=%s valid=%s", info.get("type"), info.get("is_valid"))
        logger.error("[insights] granted scopes: %s", ", ".join(sorted(granted)) or "(none)")
        if missing:
            logger.error(
                "[insights] MISSING for media insights: %s — this is the cause. "
                "Re-authorise the app with these scopes.", ", ".join(missing),
            )
        else:
            logger.error(
                "[insights] All required scopes are present, so the scope theory is "
                "wrong — look at account type and media ownership next."
            )
    else:
        logger.error("[insights] Could not read token scopes (see error above).")

    if account_id:
        acct = _graph_get(
            account_id, {"fields": "id,username,account_type"}, bypass_circuit=True
        ) or {}
        if acct:
            findings["account_type"] = acct.get("account_type")
            logger.error(
                "[insights] account username=%s type=%s", acct.get("username"),
                acct.get("account_type"),
            )
            if str(acct.get("account_type") or "").upper() == "PERSONAL":
                logger.error(
                    "[insights] Account is PERSONAL — media insights are unavailable "
                    "on personal accounts. Convert to Business or Creator."
                )

    logger.error("[insights] --- END DIAGNOSTIC ---")
    return findings


def _fetch_media_insights(media_id: str) -> dict | None:
    fields = _graph_get(media_id, {"fields": "like_count,comments_count,media_product_type"})
    likes = fields.get("like_count") if fields else None
    comments = fields.get("comments_count") if fields else None
    is_reel = str((fields or {}).get("media_product_type", "")).upper() == "REELS"

    metric_sets = (
        (["reach", "saved", "shares", "total_interactions", "views",
          "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"] if is_reel
         else ["reach", "saved", "shares", "total_interactions"]),
        (["reach", "saved", "shares", "views"] if is_reel
         else ["reach", "saved", "shares"]),
        ["reach", "saved"],
        ["reach"],
    )
    raw = {}
    for metrics in metric_sets:
        data = _graph_get(f"{media_id}/insights", {"metric": ",".join(metrics)})
        if data and "data" in data:
            for item in data["data"]:
                values = item.get("values") or [{}]
                value = values[0].get("value")
                if value is not None:
                    raw[item.get("name", "")] = value
            if raw:
                break

    if not raw:
        logger.warning("[insights] No metrics returned for %s — not measured", media_id)
        return None

    out = {
        "views": raw.get("views"),
        "reach": raw.get("reach"),
        "saves": raw.get("saved"),
        "shares": raw.get("shares"),
        "comments": comments,
        "likes": likes,
    }
    avg_ms = raw.get("ig_reels_avg_watch_time")
    if avg_ms is not None:
        out["avg_view_duration_s"] = round(float(avg_ms) / 1000.0, 2)
    total_ms = raw.get("ig_reels_video_view_total_time")
    if total_ms is not None:
        out["watch_time_s"] = round(float(total_ms) / 1000.0, 2)
    return out


def _fetch_account_insights() -> dict:
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not account_id:
        return {}
    data = _graph_get(
        f"{account_id}/insights",
        {"metric": "profile_views,website_clicks", "period": "day"},
    )
    out = {}
    for item in ((data or {}).get("data") or []):
        values = item.get("values") or [{}]
        value = values[0].get("value")
        if value is not None:
            out[item.get("name", "")] = value
    return out


def _fetch_follower_count() -> int | None:
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not account_id:
        return None
    data = _graph_get(account_id, {"fields": "followers_count"})
    if data and data.get("followers_count") is not None:
        return int(data["followers_count"])
    return None


def _hours_since(published_at: str, now: datetime.datetime) -> float:
    try:
        published = datetime.datetime.fromisoformat(published_at)
    except Exception:
        return 0.0
    return max(0.0, (now - published).total_seconds() / 3600.0)


def _next_due_window(post: dict, now: datetime.datetime) -> tuple[str, int] | None:
    completed = {str(s.get("window")) for s in (post.get("measurement_snapshots") or [])}
    age = _hours_since(str(post.get("published_at") or ""), now)
    for name, hours in MEASUREMENT_WINDOWS:
        if name not in completed and age >= hours:
            return name, hours
    return None


def _append_account_snapshot(now: datetime.datetime, follower_count: int | None, acct: dict) -> None:
    path = os.path.join(_LEARNING_DIR, "account_metrics.json")
    try:
        rows = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
        rows.append({
            "date": now.isoformat(timespec="seconds"),
            "follower_count": follower_count,
            "profile_views": acct.get("profile_views"),
            "website_clicks": acct.get("website_clicks"),
        })
        os.makedirs(_LEARNING_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows[-365:], f, indent=2)
    except Exception as e:
        logger.debug("[insights] account snapshot failed: %s", e)


def _append_follower_snapshot(now: datetime.datetime, follower_count: int | None) -> None:
    if follower_count is None:
        return
    path = os.path.join(_LEARNING_DIR, "follower_snapshots.json")
    try:
        rows = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
        rows.append({"date": now.isoformat(timespec="seconds"), "count": follower_count})
        os.makedirs(_LEARNING_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows[-365:], f, indent=2)
    except Exception as e:
        logger.debug("[insights] follower snapshot failed: %s", e)


def fetch_pending_insights() -> dict:
    """Fetch the next due observation for each post; promote only 7d to learning."""
    if not os.getenv("INSTAGRAM_ACCESS_TOKEN"):
        logger.info("[insights] Instagram not configured — skipping insights fetch")
        return {"recorded": 0, "snapshots": 0, "pending": 0, "follower_count": None}

    from content_generator.core.learning_engine import record_performance

    _reset_circuit()
    posts = _load_posts()
    now = datetime.datetime.now()
    recorded = 0
    snapshots_written = 0
    pending = 0
    failed = 0

    follower_count = _fetch_follower_count()
    acct = _fetch_account_insights()
    _append_account_snapshot(now, follower_count, acct)
    _append_follower_snapshot(now, follower_count)

    for post in posts:
        if post.get("insights_recorded"):
            continue
        due = _next_due_window(post, now)
        if due is None:
            pending += 1
            continue
        window, hours = due
        metrics = _fetch_media_insights(str(post.get("media_id") or ""))
        if metrics is None:
            attempts = post.setdefault("fetch_attempts_by_window", {})
            attempts[window] = int(attempts.get(window, 0)) + 1
            failed += 1
            if attempts[window] >= MAX_FETCH_ATTEMPTS:
                post.setdefault("failed_windows", []).append(window)
                logger.error(
                    "[insights] %s window abandoned after %d failed attempts; "
                    "future windows remain eligible", window, attempts[window]
                )
            else:
                pending += 1
            continue

        snapshot = {
            "window": window,
            "target_hours": hours,
            "measured_at": now.isoformat(timespec="seconds"),
            "metrics": metrics,
        }
        post.setdefault("measurement_snapshots", []).append(snapshot)
        snapshots_written += 1

        # Only the terminal 7d observation enters the learning log. 24h/72h are
        # preserved for diagnostics and trajectory analysis but do not multiply
        # the apparent sample size of one creative.
        if window == "7d":
            record_performance(
                asset_id=post["asset_id"], track=post.get("track", "brand"),
                hook=post.get("hook", ""), topic=post.get("topic", ""),
                format_used=post.get("format", ""), posted_at=post.get("published_at", ""),
                metrics=metrics, notes="auto-recorded from 7d Instagram measurement window",
                kpi_at_creation=post.get("kpi_at_creation", ""),
                policy_version=post.get("policy_version", ""),
                attention_mechanism=post.get("attention_mechanism", ""),
                hook_strategy=post.get("hook_strategy", ""),
                payoff_type=post.get("payoff_type", ""),
                decision_version=post.get("decision_version", ""),
                scroller_state=post.get("scroller_state", ""),
                psychology_frame=post.get("psychology_frame", ""),
            )
            post["insights_recorded"] = True
            recorded += 1

            try:
                from content_generator.analytics.hashtag_bank import record_post_hashtags
                if post.get("hashtags"):
                    record_post_hashtags(post["hashtags"], metrics)
            except Exception as e:
                logger.debug("[insights] hashtag attribution skipped: %s", e)

        logger.info("[insights] %s window=%s %s", post.get("asset_id"), window, metrics)

    _save_posts(posts)
    if _circuit_open:
        diagnose_access()

    logger.info(
        "[insights] Done — %d learning records, %d snapshots, %d pending, %d failed, "
        "followers=%s%s",
        recorded, snapshots_written, pending, failed, follower_count,
        " [CIRCUIT OPEN — systemic Graph API failure, see errors above]" if _circuit_open else "",
    )
    return {
        "recorded": recorded,
        "snapshots": snapshots_written,
        "pending": pending,
        "failed": failed,
        "follower_count": follower_count,
    }
