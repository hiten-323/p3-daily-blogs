"""Read-back verification for published objects; never infer live status from a POST response."""
from __future__ import annotations

import os
from urllib.parse import quote, urlparse

import requests


def verify_remote_post(platform: str, record: dict) -> dict:
    """Return {state: found|missing|unknown|exists_not_public, method, detail}."""
    platform = str(platform or "").lower()
    remote_id = str(record.get("remote_id") or "").strip()
    url = str(record.get("url") or "").strip()
    if not remote_id and not url:
        return {"state": "unknown", "method": "none", "detail": "no remote ID or URL to verify"}

    try:
        if platform in ("instagram", "instagram_video", "instagram_story", "facebook", "threads"):
            from config.api_versions import META_GRAPH_BASE, THREADS_BASE_URL
            graph_base = THREADS_BASE_URL if platform == "threads" else META_GRAPH_BASE
            if platform == "facebook":
                token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
                fields = "id,permalink_url,created_time"
            elif platform == "threads":
                token = os.getenv("THREADS_ACCESS_TOKEN", "")
                fields = "id,permalink,timestamp"
            else:
                token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
                fields = "id,permalink,timestamp,media_type"
            if not token or not remote_id:
                return {"state": "unknown", "method": "meta_graph_readback", "detail": "missing token or remote ID"}
            response = requests.get(
                f"{graph_base.rstrip('/')}/{quote(remote_id, safe='')}",
                params={"fields": fields, "access_token": token}, timeout=15,
            )
            if response.status_code == 200:
                payload = response.json()
                if str(payload.get("id", "")) == remote_id:
                    return {"state": "found", "method": "meta_graph_readback", "detail": "remote object ID confirmed"}
                return {"state": "unknown", "method": "meta_graph_readback", "detail": "read-back response did not match ID"}
            if response.status_code == 404:
                return {"state": "missing", "method": "meta_graph_readback", "detail": "platform returned 404 for remote ID"}
            return {"state": "unknown", "method": "meta_graph_readback", "detail": f"HTTP {response.status_code}"}

        if platform == "linkedin":
            token = os.getenv("LI_API_ACCESS", "")
            if not token or not remote_id:
                return {"state": "unknown", "method": "linkedin_posts_readback", "detail": "missing token or remote ID"}
            response = requests.get(
                "https://api.linkedin.com/rest/posts/" + quote(remote_id, safe=""),
                headers={
                    "Authorization": f"Bearer {token}",
                    "LinkedIn-Version": os.getenv("LI_API_VERSION", "202506"),
                    "X-Restli-Protocol-Version": "2.0.0",
                }, timeout=15,
            )
            if response.status_code == 200:
                payload = response.json()
                if str(payload.get("id", "")) == remote_id:
                    return {"state": "found", "method": "linkedin_posts_readback", "detail": "remote post ID confirmed"}
                return {"state": "unknown", "method": "linkedin_posts_readback", "detail": "read-back response did not match ID"}
            if response.status_code == 404:
                return {"state": "missing", "method": "linkedin_posts_readback", "detail": "platform returned 404 for remote ID"}
            return {"state": "unknown", "method": "linkedin_posts_readback", "detail": f"HTTP {response.status_code}"}

        if platform == "youtube":
            if not remote_id:
                return {"state": "unknown", "method": "youtube_data_api", "detail": "missing video ID"}
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            credentials = Credentials(
                token=None,
                refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("YOUTUBE_CLIENT_ID"),
                client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
            )
            if not all((credentials.refresh_token, credentials.client_id, credentials.client_secret)):
                return {"state": "unknown", "method": "youtube_data_api", "detail": "missing OAuth credentials"}
            credentials.refresh(Request())
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "id,status", "id": remote_id},
                headers={"Authorization": f"Bearer {credentials.token}"}, timeout=15,
            )
            if response.status_code != 200:
                return {"state": "unknown", "method": "youtube_data_api", "detail": f"HTTP {response.status_code}"}
            items = response.json().get("items", [])
            if not items:
                return {"state": "missing", "method": "youtube_data_api", "detail": "video ID not returned by Data API"}
            status = (items[0].get("status") or {})
            if status.get("privacyStatus") == "private":
                return {"state": "exists_not_public", "method": "youtube_data_api", "detail": "video exists but is private"}
            return {"state": "found", "method": "youtube_data_api", "detail": f"video exists; privacy={status.get('privacyStatus', 'unknown')}"}

        if platform in ("blog", "shopify"):
            domain = os.getenv("SHOPIFY_STORE_DOMAIN", "").strip()
            token = os.getenv("SHOPIFY_ADMIN_TOKEN", "").strip()
            blog_id = os.getenv("SHOPIFY_BLOG_ID", "").strip()
            if domain and token and blog_id and remote_id:
                from config.api_versions import SHOPIFY_API_VERSION
                domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
                response = requests.get(
                    f"https://{domain}/admin/api/{SHOPIFY_API_VERSION}/blogs/{quote(blog_id, safe='')}/articles/{quote(remote_id, safe='')}.json",
                    headers={"X-Shopify-Access-Token": token}, timeout=15,
                )
                if response.status_code == 200 and response.json().get("article", {}).get("id") is not None:
                    article = response.json()["article"]
                    if article.get("published_at"):
                        return {"state": "found", "method": "shopify_article_readback", "detail": "published article ID confirmed"}
                    return {"state": "exists_not_public", "method": "shopify_article_readback", "detail": "article exists but is not published"}
                if response.status_code == 404:
                    return {"state": "missing", "method": "shopify_article_readback", "detail": "article ID not found"}
                return {"state": "unknown", "method": "shopify_article_readback", "detail": f"HTTP {response.status_code}"}
            if url:
                response = requests.get(url, timeout=15, allow_redirects=True)
                if response.status_code == 404:
                    return {"state": "missing", "method": "public_url_readback", "detail": "public article URL returned 404"}
                if response.status_code < 400:
                    return {"state": "found", "method": "public_url_readback", "detail": "public article URL returned a successful response"}
                return {"state": "unknown", "method": "public_url_readback", "detail": f"HTTP {response.status_code}"}
            return {"state": "unknown", "method": "shopify_article_readback", "detail": "missing Shopify credentials, ID, and URL"}

        if url:
            response = requests.get(url, timeout=15, allow_redirects=True)
            if response.status_code == 404:
                return {"state": "missing", "method": "public_url_readback", "detail": "published URL returned 404"}
            if response.status_code < 400:
                return {"state": "found", "method": "public_url_readback", "detail": "published URL returned a successful response"}
            return {"state": "unknown", "method": "public_url_readback", "detail": f"HTTP {response.status_code}"}
        return {"state": "unknown", "method": "none", "detail": f"no verifier for {platform}"}
    except Exception as exc:
        return {"state": "unknown", "method": "platform_readback", "detail": f"{type(exc).__name__}: {exc}"}
