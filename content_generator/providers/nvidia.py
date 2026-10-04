"""NVIDIA NIM provider — primary LLM. OpenAI-compatible chat completions.

Base URL: https://integrate.api.nvidia.com/v1
Auth: Bearer NVIDIA_API_KEY (an nvapi- key from build.nvidia.com).
Model: NVIDIA_MODEL, default meta/llama-3.3-70b-instruct.

429 and 5xx are retried with backoff inside this client. When those retries
are exhausted the router falls through to the next provider.
"""
from __future__ import annotations

import logging
import os
import re
import time

import requests as _http

logger = logging.getLogger(__name__)

_BASE = "https://integrate.api.nvidia.com/v1"
_URL = f"{_BASE}/chat/completions"
_DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"
_BACKOFF_S = (2, 5, 12)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_NVAPI = re.compile(r"nvapi-[A-Za-z0-9_\-]+")


def get_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "").strip()


def get_model() -> str:
    return os.environ.get("NVIDIA_MODEL", "").strip() or _DEFAULT_MODEL


def _redact(text: str) -> str:
    key = get_key()
    out = str(text or "")
    if key:
        out = out.replace(key, "***")
    return _NVAPI.sub("nvapi-***", out)


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """Return (text | None, usage_dict). A missing key is skipped, not an error."""
    key = get_key()
    if not key:
        return None, {}

    model = get_model()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.92,
        "max_tokens": max_tokens,
    }
    attempts = len(_BACKOFF_S) + 1
    last_failure: dict = {"status_code": 0, "model": model, "error": ""}

    for attempt in range(attempts):
        try:
            resp = _http.post(_URL, headers=headers, json=payload, timeout=120)
        except Exception as e:
            logger.error(
                "NVIDIA %s request exception (attempt %d/%d): %s",
                model, attempt + 1, attempts, _redact(str(e)),
            )
            last_failure = {"status_code": 0, "model": model, "error": _redact(str(e))}
            return None, last_failure

        if resp.status_code == 200:
            try:
                body = resp.json()
                text = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning("NVIDIA %s returned malformed success payload: %s", model, e)
                return None, {
                    "status_code": 200,
                    "model": model,
                    "error": f"malformed success payload: {e}",
                }
            if not text:
                logger.warning("NVIDIA %s returned empty content", model)
                return None, {"status_code": 200, "model": model, "error": "empty content"}
            usage = body.get("usage") or {}
            return text, {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "model": model,
            }

        detail = _redact(resp.text[:300])
        last_failure = {"status_code": resp.status_code, "model": model, "error": detail}
        if resp.status_code in _RETRY_STATUS and attempt < attempts - 1:
            wait = _BACKOFF_S[attempt]
            logger.warning(
                "NVIDIA %s HTTP %s — attempt %d/%d — backing off %ss",
                model, resp.status_code, attempt + 1, attempts, wait,
            )
            time.sleep(wait)
            continue

        logger.warning("NVIDIA %s HTTP %s: %s", model, resp.status_code, detail)
        return None, last_failure

    return None, last_failure


def health_check() -> str:
    """One request. Returns 'OK', 'skipped', or an HTTP error. Never includes the key."""
    key = get_key()
    if not key:
        return "skipped"
    try:
        resp = _http.get(
            f"{_BASE}/models",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=15,
        )
    except Exception as e:
        return _redact(f"{type(e).__name__}: {e}")
    if resp.status_code == 200:
        return "OK"
    body = " ".join((resp.text or "").split())[:160]
    return _redact(f"HTTP {resp.status_code} {body}".strip())
