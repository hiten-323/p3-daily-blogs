"""Shared client for free-tier OpenAI-compatible chat endpoints.

Fast failover: one request per model with a short timeout, no long sleeps.
A missing key returns (None, {}) so the router skips the provider silently.
"""
from __future__ import annotations

import logging
import os

import requests as _http
from content_generator.providers.provider_budget import rate_headers

logger = logging.getLogger(__name__)

_TIMEOUT_S = int(os.getenv("FREE_LLM_TIMEOUT_S", "45"))


def chat(name: str, url: str, key: str, models: list[str], prompt: str, max_tokens: int,
         extra_headers: dict | None = None) -> tuple[str | None, dict]:
    if not key or not url:
        return None, {}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    last: dict = {"status_code": 0, "model": "", "error": "no model configured"}
    for model in (m.strip() for m in models if m and m.strip()):
        try:
            resp = _http.post(url, headers=headers, timeout=_TIMEOUT_S, json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": max_tokens,
            })
        except Exception as e:  # timeout / transport: next model, then next provider
            logger.warning("%s %s request failed: %s", name, model, type(e).__name__)
            last = {"status_code": 0, "model": model, "error": type(e).__name__}
            continue
        if resp.status_code == 200:
            try:
                body = resp.json()
                text = body["choices"][0]["message"].get("content") or ""
            except (KeyError, IndexError, TypeError, ValueError) as e:
                last = {"status_code": 200, "model": model, "error": f"malformed success payload: {e}"}
                continue
            if not str(text).strip():
                logger.warning("%s %s returned empty content", name, model)
                last = {"status_code": 200, "model": model, "error": "empty content"}
                continue
            u = body.get("usage") or {}
            return text, {"prompt_tokens": u.get("prompt_tokens"),
                          "completion_tokens": u.get("completion_tokens"), "model": model,
                          "ratelimit": rate_headers(resp)}
        last = {"status_code": resp.status_code, "model": model, "error": str(resp.text)[:300],
                "ratelimit": rate_headers(resp)}
        logger.warning("%s %s HTTP %s", name, model, resp.status_code)
        if resp.status_code in (401, 403):
            return None, last
    return None, last


def models_from_env(var: str, default: str) -> list[str]:
    return [m.strip() for m in os.getenv(var, default).split(",") if m.strip()]
