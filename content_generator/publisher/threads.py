"""
Threads auto-publisher — posts text and image threads via official Meta Threads API.

Meta Threads API flow:
  1. POST /{threads-user-id}/threads?media_type=TEXT&text={text}&access_token={token}
     -> returns container_id
  2. POST /{threads-user-id}/threads_publish?creation_id={container_id}&access_token={token}
     -> returns post_id

Required secrets (GitHub Actions):
  THREADS_USER_ID      — Your Threads account user ID
  THREADS_ACCESS_TOKEN — Long-lived Threads access token with threads_content_publish scope

Auto-skips cleanly if secrets are not set.
"""
from __future__ import annotations
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from config.api_versions import THREADS_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT_S = 25
_THREADS_CHAR_LIMIT = 500


def is_configured() -> bool:
    """True if Threads user ID and access token are configured."""
    return bool(os.getenv("THREADS_USER_ID")) and bool(os.getenv("THREADS_ACCESS_TOKEN"))


def _extract_thread_text(content: dict) -> str:
    """Extract text suitable for Threads (< 500 characters)."""
    tp = content.get("threads_post")
    if isinstance(tp, str) and tp.strip():
        return tp.strip()[:_THREADS_CHAR_LIMIT]

    if isinstance(tp, dict):
        text = str(tp.get("text") or tp.get("body") or tp.get("content") or "").strip()
        if text:
            return text[:_THREADS_CHAR_LIMIT]

    # Fallback to LinkedIn hook + CTA or Reel hook
    li = content.get("linkedin_post")
    if isinstance(li, dict):
        hook = str(li.get("hook") or "").strip()
        cta = str(li.get("cta") or "").strip()
        website = os.getenv("WEBSITE_URL", "https://p3online.in")
        combined = f"{hook}\n\n100% coffee. Zero chicory. {website}\n#PurityBeans #PureCoffee"
        return combined[:_THREADS_CHAR_LIMIT]

    reels = content.get("reels") or []
    if reels and isinstance(reels[0], dict):
        hook = str(reels[0].get("hook") or reels[0].get("hook_text") or "").strip()
        if hook:
            website = os.getenv("WEBSITE_URL", "https://p3online.in")
            combined = f"{hook}\n\n{website}\n#PurityBeans"
            return combined[:_THREADS_CHAR_LIMIT]

    return ""


def _post_request(url: str, params: dict) -> dict:
    """Execute a POST request with form-encoded data against Threads API."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "PurityBeans/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def create_thread_container(user_id: str, token: str, text: str, image_url: str | None = None) -> str:
    """Step 1: Create a media container for Threads."""
    url = f"{THREADS_BASE_URL}/{urllib.parse.quote(user_id, safe='')}/threads"
    params = {
        "access_token": token,
        "text": text[:_THREADS_CHAR_LIMIT],
    }
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"

    res = _post_request(url, params)
    container_id = res.get("id")
    if not container_id:
        raise ValueError(f"No container ID returned: {res}")
    return str(container_id)


def publish_thread_container(user_id: str, token: str, container_id: str) -> str:
    """Step 2: Publish the media container."""
    url = f"{THREADS_BASE_URL}/{urllib.parse.quote(user_id, safe='')}/threads_publish"
    params = {
        "access_token": token,
        "creation_id": container_id,
    }
    res = _post_request(url, params)
    post_id = res.get("id")
    if not post_id:
        raise ValueError(f"No post ID returned: {res}")
    return str(post_id)


def post_content(content: dict, day: int = 0) -> dict:
    """
    Publish today's content to Threads.
    Returns:
        {"success": bool, "post_id": str, "url": str, "error": str|None, "attempted": bool}
    """
    if not is_configured():
        logger.info("[threads] Not configured — THREADS_USER_ID or THREADS_ACCESS_TOKEN missing")
        return {
            "success": False,
            "attempted": False,
            "skipped": True,
            "post_id": "",
            "url": "",
            "error": "not_configured",
        }

    text = _extract_thread_text(content)
    if not text:
        logger.warning("[threads] No thread text found in content — skipping")
        return {
            "success": False,
            "attempted": False,
            "skipped": True,
            "post_id": "",
            "url": "",
            "error": "no_content",
        }

    user_id = os.getenv("THREADS_USER_ID", "").strip()
    token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()

    try:
        container_id = create_thread_container(user_id, token, text)
        post_id = publish_thread_container(user_id, token, container_id)
        url = f"https://www.threads.net/post/{post_id}"
        logger.info("[threads] Day %d posted successfully | id=%s", day, post_id)
        return {
            "success": True,
            "attempted": True,
            "skipped": False,
            "post_id": post_id,
            "url": url,
            "error": None,
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.error("[threads] HTTP %d error: %s", exc.code, body)
        return {
            "success": False,
            "attempted": True,
            "skipped": False,
            "post_id": "",
            "url": "",
            "error": f"HTTP {exc.code}: {body}",
        }
    except Exception as exc:
        logger.error("[threads] Publish exception: %s", exc)
        return {
            "success": False,
            "attempted": True,
            "skipped": False,
            "post_id": "",
            "url": "",
            "error": str(exc),
        }
