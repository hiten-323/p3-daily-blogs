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
    """True if Threads access token is configured."""
    return bool(os.getenv("THREADS_ACCESS_TOKEN"))


def _extract_thread_text(content: dict) -> str:
    """Extract text suitable for Threads (< 500 characters)."""
    tp = content.get("threads_post")
    if isinstance(tp, str) and tp.strip():
        return tp.strip()[:_THREADS_CHAR_LIMIT]

    if isinstance(tp, dict):
        text = str(tp.get("text") or tp.get("body") or tp.get("content") or "").strip()
        if text:
            return text[:_THREADS_CHAR_LIMIT]

    # Never silently repurpose another platform's asset. Missing native Threads
    # copy is a generation failure and must be held for regeneration.
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


def get_container_status(container_id: str, token: str) -> str:
    url = (f"{THREADS_BASE_URL}/{urllib.parse.quote(container_id, safe='')}?"
           + urllib.parse.urlencode({"fields": "status,error_message", "access_token": token}))
    req = urllib.request.Request(url, headers={"User-Agent": "PurityBeans/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as response:
        data = json.loads(response.read().decode("utf-8"))
    status = str(data.get("status") or "").upper()
    if status == "ERROR":
        raise ValueError(f"Threads container error: {data.get('error_message') or data}")
    return status


def wait_for_container(container_id: str, token: str, *, timeout_s: float = 120,
                       interval_s: float = 3, sleep=None, status_fn=None) -> str:
    """Poll until FINISHED. Publishing before that returns 400 'Media Not Found'."""
    import time
    sleep = sleep or time.sleep
    status_fn = status_fn or get_container_status
    waited, status, errors = 0.0, "", 0
    while waited <= timeout_s:
        try:
            status = status_fn(container_id, token)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as exc:
            if isinstance(exc, ValueError) and "container error" in str(exc):
                raise
            errors += 1
            status = f"status unavailable ({exc})"
            if errors >= 3:
                # Status endpoint unreadable: let publish try; its 400 retry covers a not-ready container.
                logger.warning("[threads] container status unreadable; publishing with retry")
                return "UNKNOWN"
        if status in ("FINISHED", "PUBLISHED"):
            return status
        if status == "EXPIRED":
            raise ValueError("Threads container expired before publish")
        sleep(interval_s)
        waited += interval_s
    raise TimeoutError(f"Threads container {container_id} not FINISHED after {timeout_s}s (last {status})")


def publish_thread_container(user_id: str, token: str, container_id: str, *,
                             attempts: int = 4, sleep=None, status_fn=None, post_fn=None) -> str:
    """Step 2: wait for FINISHED, then publish; retry 'Media Not Found' 400s."""
    import time
    sleep = sleep or time.sleep
    post_fn = post_fn or _post_request
    last: Exception | None = None
    for attempt in range(max(1, attempts)):
        wait_for_container(container_id, token, sleep=sleep, status_fn=status_fn)
        try:
            return _publish_once(user_id, token, container_id, post_fn)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            last = exc
            if exc.code != 400 and exc.code < 500:
                raise
            logger.warning("[threads] publish attempt %d failed (%s %s); retrying",
                           attempt + 1, exc.code, body[:120])
            sleep(min(30, 5 * (attempt + 1)))
    raise RuntimeError(f"Threads publish failed after {attempts} attempts: {last}")


def _publish_once(user_id: str, token: str, container_id: str, post_fn) -> str:
    """Publish the media container."""
    url = f"{THREADS_BASE_URL}/{urllib.parse.quote(user_id, safe='')}/threads_publish"
    params = {
        "access_token": token,
        "creation_id": container_id,
    }
    res = post_fn(url, params)
    post_id = res.get("id")
    if not post_id:
        raise ValueError(f"No post ID returned: {res}")
    return str(post_id)


def _media_id_to_shortcode(media_id: str | int) -> str:
    """Convert numeric Meta media ID to canonical base64 shortcode."""
    try:
        num = int(media_id)
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        shortcode = ""
        while num > 0:
            remainder = num % 64
            num = num // 64
            shortcode = alphabet[remainder] + shortcode
        return shortcode
    except Exception:
        return ""


def get_thread_permalink(post_id: str, token: str) -> str:
    """Fetch the canonical public permalink from the Threads Graph API."""
    try:
        url = f"{THREADS_BASE_URL}/{urllib.parse.quote(post_id, safe='')}?fields=permalink&access_token={urllib.parse.quote(token, safe='')}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PurityBeans/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as response:
            res = json.loads(response.read().decode("utf-8"))
            permalink = res.get("permalink")
            if permalink:
                return str(permalink).strip()
    except Exception as e:
        logger.debug("[threads] Could not fetch permalink for %s: %s", post_id, e)
    return ""


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

    from content_generator.publisher.prepublish_gate import authorize_publish
    gate = authorize_publish(content, "threads")
    if not gate["allowed"]:
        logger.warning("[threads] Pre-publish gate blocked content: %s", gate["reason"])
        return {"success": False, "attempted": False, "skipped": True, "post_id": "", "url": "", "error": "prepublish_gate:" + gate["reason"], "gate": gate}

    user_id = os.getenv("THREADS_USER_ID", "me").strip() or "me"
    token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()

    try:
        container_id = create_thread_container(user_id, token, text)
        post_id = publish_thread_container(user_id, token, container_id)

        # 1. Prefer canonical permalink directly from Threads Graph API
        url = get_thread_permalink(post_id, token)
        if not url:
            # 2. Convert numeric media ID to base64 shortcode (/t/{shortcode})
            shortcode = _media_id_to_shortcode(post_id)
            if shortcode:
                url = f"https://www.threads.net/t/{shortcode}"
            else:
                url = f"https://www.threads.net/post/{post_id}"

        logger.info("[threads] Day %d posted successfully | id=%s url=%s", day, post_id, url)
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
