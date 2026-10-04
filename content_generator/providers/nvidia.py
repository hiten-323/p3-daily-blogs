"""NVIDIA NIM provider — primary LLM. OpenAI-compatible chat completions.

Base URL: https://integrate.api.nvidia.com/v1
Auth: Bearer NVIDIA_API_KEY (an nvapi- key from build.nvidia.com).
Models: NVIDIA_MODEL, a comma-separated fallback list. When it is blank the
client uses the live defaults below. meta/llama-3.3-70b-instruct reached end
of life on 2026-08-26 and the hosted API now answers HTTP 410.

404 and 410 mean that model is gone or unknown, so the next configured model
is tried immediately. 429 and 5xx are retried with backoff on the same model.
When those retries are exhausted the router falls through to the next provider.
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
# Live free chat endpoints on build.nvidia.com as of 2026-10-04.
# Super is the large general-purpose model whose hosted sample is a plain
# chat completion. Ultra and Gemma 4 31B IT are the current fallbacks.
_DEFAULT_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "google/gemma-4-31b-it",
)
_DEFAULT_MODEL = _DEFAULT_MODELS[0]
_BACKOFF_S = (2, 5, 12)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_UNAVAILABLE = {404, 410}
_NVAPI = re.compile(r"nvapi-[A-Za-z0-9_\-]+")


def get_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "").strip()


def get_models() -> list[str]:
    """Model ids in try-order. A blank NVIDIA_MODEL keeps the live defaults."""
    raw = os.environ.get("NVIDIA_MODEL", "")
    if not raw.strip():
        return list(_DEFAULT_MODELS)
    models = [part.strip() for part in raw.split(",") if part.strip()]
    return models or list(_DEFAULT_MODELS)


def get_model() -> str:
    """Primary model. Single-model callers, including the dry-run probe, use this."""
    models = get_models()
    return models[0] if models else _DEFAULT_MODEL


def _redact(text: str) -> str:
    key = get_key()
    out = str(text or "")
    if key:
        out = out.replace(key, "***")
    return _NVAPI.sub("nvapi-***", out)


def _call_model(prompt: str, max_tokens: int, model: str, headers: dict) -> tuple[str | None, dict]:
    """One configured model, including the transient-error backoff."""
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
            return None, {"status_code": 0, "model": model, "error": _redact(str(e))}

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
        if resp.status_code in _UNAVAILABLE:
            return None, last_failure
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


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """Return (text | None, usage_dict). A missing key is skipped, not an error."""
    key = get_key()
    if not key:
        return None, {}

    models = get_models()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_failure: dict = {"status_code": 0, "model": "", "error": "no NVIDIA model configured"}

    for index, model in enumerate(models):
        text, usage = _call_model(prompt, max_tokens, model, headers)
        if text is not None:
            return text, usage
        last_failure = usage
        status = int(usage.get("status_code") or 0)
        if status not in _UNAVAILABLE:
            return None, last_failure
        if index + 1 < len(models):
            logger.warning(
                "NVIDIA %s HTTP %s — model unavailable (%s); trying next configured model %s",
                model, status, usage.get("error") or "no body", models[index + 1],
            )
            continue
        logger.warning(
            "NVIDIA %s HTTP %s — model unavailable (%s); no further configured models",
            model, status, usage.get("error") or "no body",
        )
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
