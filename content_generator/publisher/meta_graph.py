"""
Meta Graph container lifecycle.

Publishing used to continue after a container reported ERROR or simply never
became FINISHED. Video polls stopped around two minutes and published anyway.
Transient rate-limit responses were not retried. This module fails closed
and retries only the errors Meta documents as transient.
"""
from __future__ import annotations

import logging
import time

from config.api_versions import META_GRAPH_BASE

logger = logging.getLogger(__name__)

# Meta error codes that are safe to retry. Auth (190) and permission (10/200)
# are permanent and must surface immediately.
_TRANSIENT_CODES = {1, 2, 4, 17, 32, 613}
_TRANSIENT_HTTP = {429, 500, 502, 503, 504}

_RETRY_ATTEMPTS = 4
_RETRY_BASE_DELAY = 1.0
_POLL_INTERVAL = 5.0
_VIDEO_POLL_S = 300


class ContainerNotReady(Exception):
    """Container ended in ERROR or never reached FINISHED before the deadline."""


class MetaRequestError(Exception):
    """A Graph call failed after transient retries were exhausted."""


def _is_transient(status: int, data: dict) -> bool:
    if status in _TRANSIENT_HTTP:
        return True
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return False
    if err.get("is_transient") is True:
        return True
    try:
        code = int(err.get("code"))
    except (TypeError, ValueError):
        code = None
    if code in _TRANSIENT_CODES:
        return True
    msg = str(err.get("message") or "").lower()
    return "rate limit" in msg or "temporarily unavailable" in msg


def graph_request(method: str, url: str, params: dict | None = None, timeout: int = 30) -> dict:
    """
    One Graph call. Transient HTTP and Meta errors are retried with backoff.
    A permanent error body is returned so the caller can report Meta's message.
    """
    import requests

    delay = _RETRY_BASE_DELAY
    last = "meta_request_failed"
    attempts = max(1, _RETRY_ATTEMPTS)
    safe_params = dict(params or {})
    token = safe_params.pop("access_token", None)
    headers = {"User-Agent": "PurityBeans/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(attempts):
        try:
            resp = requests.request(
                method, url, params=safe_params, headers=headers, timeout=timeout,
            )
        except requests.RequestException as exc:
            last = f"transport: {exc}"
            logger.warning("[meta] %s %s failed (%s) attempt %d/%d",
                           method, url, exc, attempt + 1, attempts)
            if attempt == attempts - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        try:
            data = resp.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if _is_transient(resp.status_code, data):
            err = data.get("error") if isinstance(data.get("error"), dict) else {}
            last = str(err.get("message") or f"HTTP {resp.status_code}")
            logger.warning("[meta] transient %s on %s (attempt %d/%d)",
                           last, url, attempt + 1, attempts)
            if attempt == attempts - 1:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30)
            continue
        return data
    raise MetaRequestError(last)


def wait_for_container(container_id: str, token: str, max_wait: int | None = 60,
                       interval: float | None = None) -> None:
    """
    Block until the container is FINISHED.

    ERROR and deadline expiry raise ContainerNotReady with Meta's status
    text when the API sent one. Callers must not publish after this raises.
    """
    deadline = time.monotonic() + max(0, int(max_wait or 0))
    pause = _POLL_INTERVAL if interval is None else interval
    last = "UNKNOWN"
    reason = ""
    while True:
        try:
            data = graph_request(
                "GET",
                f"{META_GRAPH_BASE}/{container_id}",
                {"fields": "status_code,status", "access_token": token},
                timeout=20,
            )
        except MetaRequestError as exc:
            last = "REQUEST_ERROR"
            reason = str(exc)
            data = {}
        status = str((data or {}).get("status_code") or "")
        if status:
            last = status
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            detail = (data or {}).get("status") or reason or status
            raise ContainerNotReady(f"container {container_id} {status}: {detail}")
        if time.monotonic() >= deadline:
            detail = reason or last
            raise ContainerNotReady(
                f"container {container_id} timeout after {max_wait}s (last status {detail})"
            )
        time.sleep(max(0, pause))
