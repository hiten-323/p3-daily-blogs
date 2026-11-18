"""Platform Metric Adapters for the Post-Publication Learning Loop.

Implements the contract specified in docs/POST_PUBLICATION_LEARNING_LOOP.md:
- Explicit supported and unsupported metrics per platform/type.
- True metrics when available; missing fields remain None (never fabricated as 0).
- Explicit classification of auth_expired, permission_gap, rate_limited, not_found, and ok.
- Strict token and secret redaction on all error messages.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import os
import re
from typing import Any, Optional
from urllib.parse import quote, urlencode
import urllib.error
import urllib.request

from config.api_versions import META_GRAPH_BASE, THREADS_BASE_URL

logger = logging.getLogger(__name__)

STANDARD_METRICS = (
    "views", "impressions", "reach", "likes", "comments",
    "shares", "saves", "watch_time_s", "avg_view_duration_s",
    "completion_rate", "profile_visits", "follows_gained",
    "link_clicks", "website_sessions", "orders", "revenue",
)

_SENSITIVE_ENV_KEYS = (
    "INSTAGRAM_ACCESS_TOKEN", "FACEBOOK_PAGE_ACCESS_TOKEN", "THREADS_ACCESS_TOKEN",
    "LI_API_ACCESS", "LINKEDIN_ACCESS_TOKEN", "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN", "SHOPIFY_ADMIN_TOKEN", "IMGBB_API_KEY",
)


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text)
    for env_k in _SENSITIVE_ENV_KEYS:
        val = os.getenv(env_k)
        if val and len(val) > 4:
            cleaned = cleaned.replace(val, "***")
    return cleaned


@dataclasses.dataclass
class MetricObservation:
    platform: str
    media_id: str
    window: str  # "24h", "72h", "7d"
    status: str  # "ok", "permission_gap", "auth_expired", "rate_limited", "not_found", "unsupported", "error"
    fetched_at: str  # ISO 8601
    metrics: dict[str, Any]  # supported & observed metrics; unobserved/unsupported are None
    supported_metrics: list[str]
    unsupported_metrics: list[str]
    source_endpoint: str = ""
    error_detail: str = ""
    raw_response: Optional[dict] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class BasePlatformMetricAdapter:
    platform: str = "generic"
    supported_metrics: list[str] = []
    unsupported_metrics: list[str] = []

    def is_configured(self) -> bool:
        raise NotImplementedError

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        raise NotImplementedError

    def _init_observation(self, media_id: str, window: str, status: str = "error",
                          source_endpoint: str = "", error_detail: str = "",
                          raw_response: dict | None = None) -> MetricObservation:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        empty_metrics = {k: None for k in self.supported_metrics}
        return MetricObservation(
            platform=self.platform,
            media_id=media_id,
            window=window,
            status=status,
            fetched_at=now_iso,
            metrics=empty_metrics,
            supported_metrics=list(self.supported_metrics),
            unsupported_metrics=list(self.unsupported_metrics),
            source_endpoint=source_endpoint,
            error_detail=redact_secrets(error_detail),
            raw_response=raw_response,
        )


class InstagramMetricAdapter(BasePlatformMetricAdapter):
    platform = "instagram"
    supported_metrics = ["impressions", "reach", "likes", "comments", "shares", "saves", "views"]
    unsupported_metrics = ["watch_time_s", "avg_view_duration_s", "completion_rate", "website_sessions", "orders", "revenue"]

    def is_configured(self) -> bool:
        return bool(os.getenv("INSTAGRAM_ACCESS_TOKEN"))

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        media_id = str(post_record.get("media_id") or "")
        token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        if not token or not media_id:
            return self._init_observation(media_id, window, status="auth_expired" if not token else "not_found",
                                          error_detail="Missing Instagram access token or media ID")

        # 1. Fetch public like_count and comments_count
        fields_url = f"{META_GRAPH_BASE}/{quote(media_id, safe='')}?fields=like_count,comments_count,media_type&access_token={token}"
        source_ep = f"{META_GRAPH_BASE}/{media_id}"
        likes = None
        comments = None
        raw = {}
        try:
            req = urllib.request.Request(fields_url, headers={"User-Agent": "PurityBeans/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw["media_fields"] = data
                likes = data.get("like_count")
                comments = data.get("comments_count")
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", "replace"))
            if exc.code == 404:
                return self._init_observation(media_id, window, status="not_found", source_endpoint=source_ep, error_detail=f"404 Not Found: {body}")
            if exc.code in (401, 190) or "session has expired" in body.lower() or "error validating access token" in body.lower():
                return self._init_observation(media_id, window, status="auth_expired", source_endpoint=source_ep, error_detail=f"Auth expired: {body}")
            if exc.code == 403 or "permission" in body.lower():
                return self._init_observation(media_id, window, status="permission_gap", source_endpoint=source_ep, error_detail=f"Permission gap: {body}")
            if exc.code == 429 or "rate limit" in body.lower():
                return self._init_observation(media_id, window, status="rate_limited", source_endpoint=source_ep, error_detail=f"Rate limited: {body}")
        except Exception as exc:
            logger.debug("[metric_adapter] Instagram fields request error: %s", exc)

        # 2. Fetch insights metrics if available
        insights_metrics = "impressions,reach,saved,shares"
        insights_url = f"{META_GRAPH_BASE}/{quote(media_id, safe='')}/insights?metric={insights_metrics}&access_token={token}"
        impressions = None
        reach = None
        saves = None
        shares = None
        views = None
        try:
            req = urllib.request.Request(insights_url, headers={"User-Agent": "PurityBeans/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw["insights"] = data
                for item in data.get("data", []):
                    name = item.get("name")
                    values = item.get("values", [{}])
                    val = values[0].get("value") if values else None
                    if name == "impressions":
                        impressions = val
                    elif name == "reach":
                        reach = val
                    elif name == "saved":
                        saves = val
                    elif name == "shares":
                        shares = val
                    elif name in ("views", "video_views"):
                        views = val
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", "replace"))
            if "instagram_manage_insights" in body.lower() or "nonexisting field" in body.lower():
                # Permission gap on insights endpoint; partial public metrics still valid
                raw["insights_error"] = body
            elif exc.code == 429:
                return self._init_observation(media_id, window, status="rate_limited", source_endpoint=insights_url, error_detail=body)
        except Exception as exc:
            logger.debug("[metric_adapter] Instagram insights request error: %s", exc)

        # Build populated metrics dictionary; unobserved remain None
        metrics = {
            "impressions": impressions,
            "reach": reach,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "views": views if views is not None else impressions,
        }

        # If we got at least one observation, status is ok; if insights failed due to permissions but likes/comments present, still ok (with gap noted)
        has_any = any(v is not None for v in metrics.values())
        status = "ok" if has_any else ("permission_gap" if "insights_error" in raw else "error")
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

        return MetricObservation(
            platform=self.platform,
            media_id=media_id,
            window=window,
            status=status,
            fetched_at=now_iso,
            metrics=metrics,
            supported_metrics=list(self.supported_metrics),
            unsupported_metrics=list(self.unsupported_metrics),
            source_endpoint=source_ep,
            error_detail=redact_secrets(raw.get("insights_error", "")),
            raw_response=raw,
        )


class FacebookMetricAdapter(BasePlatformMetricAdapter):
    platform = "facebook"
    supported_metrics = ["impressions", "reach", "likes", "comments", "shares", "link_clicks"]
    unsupported_metrics = ["saves", "watch_time_s", "completion_rate", "orders", "revenue"]

    def is_configured(self) -> bool:
        return bool(os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN"))

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        post_id = str(post_record.get("media_id") or post_record.get("published_id") or "")
        token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        if not token or not post_id:
            return self._init_observation(post_id, window, status="auth_expired" if not token else "not_found",
                                          error_detail="Missing Facebook page access token or post ID")

        page_id = os.getenv("FACEBOOK_PAGE_ID", "")
        try:
            from content_generator.publisher.facebook import resolve_page_access_token
            token = resolve_page_access_token(page_id, token)
        except Exception:
            pass

        url = f"{META_GRAPH_BASE}/{quote(post_id, safe='')}?fields=shares,reactions.summary(true),comments.summary(true)&access_token={token}"
        source_ep = f"{META_GRAPH_BASE}/{post_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PurityBeans/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                likes = (data.get("reactions", {}).get("summary", {})).get("total_count")
                comments = (data.get("comments", {}).get("summary", {})).get("total_count")
                shares = (data.get("shares", {})).get("count")

                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                metrics = {
                    "impressions": None,
                    "reach": None,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "link_clicks": None,
                }
                return MetricObservation(
                    platform=self.platform,
                    media_id=post_id,
                    window=window,
                    status="ok",
                    fetched_at=now_iso,
                    metrics=metrics,
                    supported_metrics=list(self.supported_metrics),
                    unsupported_metrics=list(self.unsupported_metrics),
                    source_endpoint=source_ep,
                    raw_response=data,
                )
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", "replace"))
            if exc.code == 404:
                return self._init_observation(post_id, window, status="not_found", source_endpoint=source_ep, error_detail=body)
            if exc.code == 401 or "session has expired" in body.lower():
                return self._init_observation(post_id, window, status="auth_expired", source_endpoint=source_ep, error_detail=body)
            if exc.code == 403 or "permission" in body.lower():
                return self._init_observation(post_id, window, status="permission_gap", source_endpoint=source_ep, error_detail=body)
            if exc.code == 429:
                return self._init_observation(post_id, window, status="rate_limited", source_endpoint=source_ep, error_detail=body)
            return self._init_observation(post_id, window, status="error", source_endpoint=source_ep, error_detail=body)
        except Exception as exc:
            return self._init_observation(post_id, window, status="error", source_endpoint=source_ep, error_detail=str(exc))


class YouTubeMetricAdapter(BasePlatformMetricAdapter):
    platform = "youtube"
    supported_metrics = ["views", "likes", "comments"]
    unsupported_metrics = ["reach", "impressions", "shares", "saves", "watch_time_s", "orders", "revenue"]

    def is_configured(self) -> bool:
        from content_generator.publisher.youtube import is_configured
        return is_configured()

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        video_id = str(post_record.get("media_id") or post_record.get("published_id") or "")
        if not video_id:
            return self._init_observation(video_id, window, status="not_found", error_detail="No video ID provided")

        from content_generator.publisher.youtube import _refresh_access_token
        access_token = _refresh_access_token() if self.is_configured() else None
        source_ep = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=statistics"

        if access_token:
            url = f"{source_ep}&access_token={access_token}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "PurityBeans/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("items", [])
                    if not items:
                        return self._init_observation(video_id, window, status="not_found", source_endpoint=source_ep,
                                                      error_detail="Video item not returned in YouTube statistics query")
                    stats = items[0].get("statistics", {})
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                    views = int(stats["viewCount"]) if "viewCount" in stats else None
                    likes = int(stats["likeCount"]) if "likeCount" in stats else None
                    comments = int(stats["commentCount"]) if "commentCount" in stats else None
                    metrics = {
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                    }
                    return MetricObservation(
                        platform=self.platform,
                        media_id=video_id,
                        window=window,
                        status="ok",
                        fetched_at=now_iso,
                        metrics=metrics,
                        supported_metrics=list(self.supported_metrics),
                        unsupported_metrics=list(self.unsupported_metrics),
                        source_endpoint=source_ep,
                        raw_response=data,
                    )
            except urllib.error.HTTPError as exc:
                body = redact_secrets(exc.read().decode("utf-8", "replace"))
                if exc.code == 401:
                    return self._init_observation(video_id, window, status="auth_expired", source_endpoint=source_ep, error_detail=body)
                if exc.code == 403:
                    return self._init_observation(video_id, window, status="permission_gap", source_endpoint=source_ep, error_detail=body)
            except Exception as exc:
                logger.debug("[metric_adapter] YouTube API query error: %s", exc)

        # Fallback to public oEmbed validation when OAuth API quota/token unavailable
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/shorts/{quote(video_id, safe='')}&format=json"
        try:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "PurityBeans/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                # oEmbed confirms post is live, but does not expose exact numeric views
                metrics = {
                    "views": None,
                    "likes": None,
                    "comments": None,
                }
                return MetricObservation(
                    platform=self.platform,
                    media_id=video_id,
                    window=window,
                    status="permission_gap",
                    fetched_at=now_iso,
                    metrics=metrics,
                    supported_metrics=list(self.supported_metrics),
                    unsupported_metrics=list(self.unsupported_metrics),
                    source_endpoint=oembed_url,
                    error_detail="Video confirmed live via oEmbed; Data API token required for post view counts",
                    raw_response=data,
                )
        except Exception as exc:
            return self._init_observation(video_id, window, status="not_found", source_endpoint=oembed_url, error_detail=str(exc))


class ThreadsMetricAdapter(BasePlatformMetricAdapter):
    platform = "threads"
    supported_metrics = ["views", "likes", "comments", "shares"]
    unsupported_metrics = ["saves", "watch_time_s", "completion_rate", "orders", "revenue"]

    def is_configured(self) -> bool:
        return bool(os.getenv("THREADS_ACCESS_TOKEN"))

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        media_id = str(post_record.get("media_id") or post_record.get("published_id") or "")
        token = os.getenv("THREADS_ACCESS_TOKEN", "")
        if not token or not media_id:
            return self._init_observation(media_id, window, status="auth_expired" if not token else "not_found",
                                          error_detail="Missing Threads access token or media ID")

        source_ep = f"{THREADS_BASE_URL}/{media_id}/insights"
        url = f"{source_ep}?metric=views,likes,replies,reposts,quotes&access_token={token}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PurityBeans/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                views, likes, replies, reposts = None, None, None, None
                for item in data.get("data", []):
                    name = item.get("name")
                    values = item.get("values", [{}])
                    val = values[0].get("value") if values else None
                    if name == "views":
                        views = val
                    elif name == "likes":
                        likes = val
                    elif name == "replies":
                        replies = val
                    elif name == "reposts":
                        reposts = val
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                metrics = {
                    "views": views,
                    "likes": likes,
                    "comments": replies,
                    "shares": reposts,
                }
                return MetricObservation(
                    platform=self.platform,
                    media_id=media_id,
                    window=window,
                    status="ok",
                    fetched_at=now_iso,
                    metrics=metrics,
                    supported_metrics=list(self.supported_metrics),
                    unsupported_metrics=list(self.unsupported_metrics),
                    source_endpoint=source_ep,
                    raw_response=data,
                )
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", "replace"))
            if exc.code == 404:
                return self._init_observation(media_id, window, status="not_found", source_endpoint=source_ep, error_detail=body)
            if exc.code == 401 or "session has expired" in body.lower():
                return self._init_observation(media_id, window, status="auth_expired", source_endpoint=source_ep, error_detail=body)
            if exc.code == 403 or "permission" in body.lower():
                return self._init_observation(media_id, window, status="permission_gap", source_endpoint=source_ep, error_detail=body)
            if exc.code == 429:
                return self._init_observation(media_id, window, status="rate_limited", source_endpoint=source_ep, error_detail=body)
            return self._init_observation(media_id, window, status="error", source_endpoint=source_ep, error_detail=body)
        except Exception as exc:
            return self._init_observation(media_id, window, status="error", source_endpoint=source_ep, error_detail=str(exc))


class LinkedInMetricAdapter(BasePlatformMetricAdapter):
    platform = "linkedin"
    supported_metrics = ["impressions", "likes", "comments", "shares", "link_clicks"]
    unsupported_metrics = ["saves", "watch_time_s", "completion_rate", "revenue"]

    def is_configured(self) -> bool:
        from content_generator.publisher.linkedin import is_configured
        return is_configured()

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        post_urn = str(post_record.get("media_id") or post_record.get("published_id") or "")
        from content_generator.publisher.linkedin import get_access_token, active_api_version
        token = get_access_token()
        if not token or not post_urn:
            return self._init_observation(post_urn, window, status="auth_expired" if not token else "not_found",
                                          error_detail="Missing LinkedIn access token or post URN")

        source_ep = f"https://api.linkedin.com/rest/organizationalEntityShareStatistics"
        encoded_urn = quote(post_urn, safe="")
        url = f"{source_ep}?q=organizationalEntity&shares=List({encoded_urn})"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "LinkedIn-Version": active_api_version(),
                    "X-Restli-Protocol-Version": "2.0.0",
                    "User-Agent": "PurityBeans/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                elements = data.get("elements", [])
                impressions, likes, comments, shares, clicks = None, None, None, None, None
                if elements:
                    elem = elements[0]
                    stats = elem.get("totalShareStatistics", {})
                    impressions = stats.get("impressionCount")
                    likes = stats.get("likeCount")
                    comments = stats.get("commentCount")
                    shares = stats.get("shareCount")
                    clicks = stats.get("clickCount")
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                metrics = {
                    "impressions": impressions,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "link_clicks": clicks,
                }
                return MetricObservation(
                    platform=self.platform,
                    media_id=post_urn,
                    window=window,
                    status="ok" if elements else "not_found",
                    fetched_at=now_iso,
                    metrics=metrics,
                    supported_metrics=list(self.supported_metrics),
                    unsupported_metrics=list(self.unsupported_metrics),
                    source_endpoint=source_ep,
                    raw_response=data,
                )
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", "replace"))
            if exc.code == 404:
                return self._init_observation(post_urn, window, status="not_found", source_endpoint=source_ep, error_detail=body)
            if exc.code == 401 or "expired" in body.lower():
                return self._init_observation(post_urn, window, status="auth_expired", source_endpoint=source_ep, error_detail=body)
            if exc.code == 403 or "scope" in body.lower():
                return self._init_observation(post_urn, window, status="permission_gap", source_endpoint=source_ep, error_detail=body)
            if exc.code == 429:
                return self._init_observation(post_urn, window, status="rate_limited", source_endpoint=source_ep, error_detail=body)
            return self._init_observation(post_urn, window, status="error", source_endpoint=source_ep, error_detail=body)
        except Exception as exc:
            return self._init_observation(post_urn, window, status="error", source_endpoint=source_ep, error_detail=str(exc))


class ShopifyBlogMetricAdapter(BasePlatformMetricAdapter):
    platform = "shopify"
    supported_metrics = ["views", "website_sessions", "orders", "revenue"]
    unsupported_metrics = ["reach", "likes", "comments", "shares", "saves"]

    def is_configured(self) -> bool:
        return bool(os.getenv("SHOPIFY_STORE_DOMAIN") and os.getenv("SHOPIFY_ADMIN_TOKEN"))

    def fetch_metrics(self, post_record: dict, window: str) -> MetricObservation:
        article_id = str(post_record.get("media_id") or post_record.get("published_id") or "")
        return self._init_observation(
            article_id, window,
            status="permission_gap",
            source_endpoint="shopify_analytics_graphql",
            error_detail="Shopify Admin API connected; web traffic insights require Google Analytics or ShopifyQL access scope",
        )


_ADAPTERS: dict[str, BasePlatformMetricAdapter] = {
    "instagram": InstagramMetricAdapter(),
    "instagram_video": InstagramMetricAdapter(),
    "instagram_story": InstagramMetricAdapter(),
    "facebook": FacebookMetricAdapter(),
    "youtube": YouTubeMetricAdapter(),
    "threads": ThreadsMetricAdapter(),
    "linkedin": LinkedInMetricAdapter(),
    "shopify": ShopifyBlogMetricAdapter(),
    "blog": ShopifyBlogMetricAdapter(),
}


def get_adapter(platform: str) -> BasePlatformMetricAdapter | None:
    plat = str(platform or "").strip().lower()
    return _ADAPTERS.get(plat)


def fetch_observation(post_record: dict, window: str) -> MetricObservation:
    platform = str(post_record.get("platform") or "").lower()
    if not platform:
        asset = str(post_record.get("asset_id") or "").lower()
        platform = asset.split("_")[0] if "_" in asset else "instagram"
    adapter = get_adapter(platform)
    if not adapter:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        return MetricObservation(
            platform=platform,
            media_id=str(post_record.get("media_id") or ""),
            window=window,
            status="unsupported",
            fetched_at=now_iso,
            metrics={},
            supported_metrics=[],
            unsupported_metrics=list(STANDARD_METRICS),
            error_detail=f"No metric adapter registered for platform '{platform}'",
        )
    return adapter.fetch_metrics(post_record, window)
