"""Shared client for free-tier OpenAI-compatible chat endpoints.

Fast failover: one request per model with a short timeout, no long sleeps.
A missing key returns (None, {}) so the router skips the provider silently.
"""
from __future__ import annotations

import json
import logging
import os

import requests as _http
from content_generator.parsers.json_parser import extract as _extract_json
from content_generator.providers.provider_budget import rate_headers

logger = logging.getLogger(__name__)

_TIMEOUT_S = int(os.getenv("FREE_LLM_TIMEOUT_S", "45"))


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "".join(parts)
    return str(value)


def _holds_json_object(text: str) -> bool:
    try:
        _extract_json(text)
    except (TypeError, ValueError):
        return False
    return True


def message_text(msg: dict) -> str:
    """Visible answer, or the reasoning field when that is where the JSON went.

    Reasoning models sometimes leave content empty and put the answer in
    reasoning_content. A think trace with no JSON object stays empty so the
    caller can try the next model. When both fields are present, the trace
    comes first so the parser's last object is the answer.
    """
    if not isinstance(msg, dict):
        return ""
    content = _as_text(msg.get("content")).strip()
    reasoning = _as_text(msg.get("reasoning_content") or msg.get("reasoning")).strip()
    if content and reasoning and content != reasoning:
        return reasoning + "\n" + content
    if content:
        return content
    if reasoning and _holds_json_object(reasoning):
        return reasoning
    return ""


def _sse_completion(raw: str) -> dict | None:
    """Reassemble an OpenAI-style SSE body. None when it is not event-stream data."""
    frames = []
    saw_data = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        saw_data = True
        data = stripped[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            frames.append(json.loads(data))
        except ValueError:
            continue
    if not saw_data or not frames:
        return None
    parts: list[str] = []
    last_message = None
    for frame in frames:
        choices = frame.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            continue
        choice = choices[0]
        message = choice.get("message")
        if isinstance(message, dict):
            last_message = message
        delta = choice.get("delta") or {}
        if isinstance(delta, dict):
            piece = _as_text(delta.get("content"))
            if piece:
                parts.append(piece)
    if parts:
        return {"choices": [{"message": {"content": "".join(parts)}}],
                "usage": (frames[-1].get("usage") if isinstance(frames[-1], dict) else {}) or {}}
    if last_message is not None:
        return {"choices": [{"message": last_message}]}
    return None


def completion_body(resp) -> dict:
    """Chat-completion JSON, including an SSE body that resp.json() cannot read.

    An empty HTTP 200 is still a failure. 'Expecting value' from json.loads('')
    is that empty body, not a score we failed to find.
    """
    raw = getattr(resp, "text", "") or ""
    try:
        body = resp.json()
    except ValueError:
        body = _sse_completion(raw)
        if body is None:
            if not str(raw).strip():
                raise ValueError("empty success body")
            raise ValueError(f"unreadable success body: {str(raw)[:80]!r}")
    if not isinstance(body, dict):
        raise ValueError("success payload was not an object")
    return body


def chat(name: str, url: str, key: str, models: list[str], prompt: str, max_tokens: int,
         extra_headers: dict | None = None, extra_body: dict | None = None) -> tuple[str | None, dict]:
    if not key or not url:
        return None, {}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    last: dict = {"status_code": 0, "model": "", "error": "no model configured"}
    for model in (m.strip() for m in models if m and m.strip()):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": max_tokens,
        }
        payload.update(extra_body or {})
        try:
            resp = _http.post(url, headers=headers, timeout=_TIMEOUT_S, json=payload)
        except Exception as e:  # timeout / transport: next model, then next provider
            logger.warning("%s %s request failed: %s", name, model, type(e).__name__)
            last = {"status_code": 0, "model": model, "error": type(e).__name__}
            continue
        if resp.status_code == 200:
            try:
                body = completion_body(resp)
                msg = body["choices"][0].get("message") or {}
                text = message_text(msg) or _as_text((body["choices"][0].get("delta") or {}).get("content"))
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
