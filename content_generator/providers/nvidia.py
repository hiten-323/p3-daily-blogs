"""NVIDIA NIM provider — primary LLM. OpenAI-compatible chat completions.

Base URL: https://integrate.api.nvidia.com/v1
Auth: Bearer NVIDIA_API_KEY (an nvapi- key from build.nvidia.com).
Models: NVIDIA_MODEL, a comma-separated fallback list. When it is blank the
client uses the live defaults below. meta/llama-3.3-70b-instruct reached end
of life on 2026-08-26 and the hosted API now answers HTTP 410.

404 and 410 mean that model is gone or unknown, so the next configured model
is tried immediately. Empty or whitespace-only HTTP 200 content is the same
kind of miss: run 341 and run 344 showed nemotron-3-super answering 200 with
an empty body, and editorial_review then hit its 420s hard timeout. The next
configured model is tried, and when none of them return text the router falls
through to the next provider. 429 and 5xx are retried with backoff on the
same model. Each call has a short timeout so one hung model cannot consume
the editorial deadline.
"""
from __future__ import annotations

import logging
import os
import re
import time

import requests as _http

from content_generator.providers.openai_compat import completion_body, message_text

logger = logging.getLogger(__name__)

_BASE = "https://integrate.api.nvidia.com/v1"
_URL = f"{_BASE}/chat/completions"
# Live free chat endpoints on build.nvidia.com.
# Runs 341 (2026-10-05) and 344 (2026-10-06) called nemotron-3-super first.
# It often returned HTTP 200 with empty content (reel_1, carousel, stories,
# yt_short, blog sections) and the calls that did answer took 12–17s.
# Nemotron 3.5 Lightning is NVIDIA's current text-only model with a free hosted
# endpoint. Prefer it for generation; retain Gemma, Ultra, and Super as fallbacks.
_DEFAULT_MODELS = (
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "google/gemma-4-31b-it",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
)
_DEFAULT_MODEL = _DEFAULT_MODELS[0]
_BACKOFF_S = (2, 5, 12)
# Successful super replies in run 341 finished in under 20s. Empty replies in
# run 344 sat for 23–50s and still returned nothing. 15s fails dead endpoints fast.
# Day 286 runs 38592410181/38602719185: 45s read timeouts on nearly every call,
# times 2-3 models, ate the whole job. NVIDIA is now behind Gemini, the read
# timeout stays 45s (15s timed out everything), one call has a total budget across models, and a model
# that keeps timing out / returning empty is skipped for a cooldown.
_CALL_TIMEOUT_S = int(os.getenv("NVIDIA_CALL_TIMEOUT_S", "45"))
_CALL_BUDGET_S = float(os.getenv("NVIDIA_CALL_BUDGET_S", "120"))
_SICK_AFTER = int(os.getenv("NVIDIA_SICK_AFTER", "2"))
_SICK_COOLDOWN_S = float(os.getenv("NVIDIA_SICK_COOLDOWN_S", "900"))
_MODEL_HEALTH: dict[str, dict] = {}


def _reset_model_health() -> None:
    _MODEL_HEALTH.clear()


def _model_sick(model: str) -> bool:
    h = _MODEL_HEALTH.get(model)
    if not h or h["fails"] < _SICK_AFTER:
        return False
    if time.time() >= h["until"]:
        _MODEL_HEALTH.pop(model, None)
        return False
    return True


def _note_model(model: str, ok: bool) -> None:
    if ok:
        _MODEL_HEALTH.pop(model, None)
        return
    h = _MODEL_HEALTH.setdefault(model, {"fails": 0, "until": 0.0})
    h["fails"] += 1
    if h["fails"] >= _SICK_AFTER:
        h["until"] = time.time() + _SICK_COOLDOWN_S
        logger.warning("NVIDIA %s marked unhealthy for %ds (timeouts/empty replies)", model, int(_SICK_COOLDOWN_S))  # 15s timed out on almost every call (day 286); the editorial soft deadline caps the total
_RETRY_STATUS = {429, 500, 502, 503, 504}
_UNAVAILABLE = {404, 410}
_AUTH_STATUS = {401, 403}
_NVAPI = re.compile(r"nvapi-[A-Za-z0-9_\-]+")


def get_key() -> str:
    return os.environ.get("NVIDIA_API_KEY", "").strip()


_PREFER = (
    "nvidia/nemotron-3.5-lightning-30b-a3b", "google/gemma-4-31b-it",
    "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b",
    "deepseek-ai/deepseek-v4.1-flash", "qwen/qwen3", "meta/llama-4",
    "moonshotai/kimi-k2.6", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
)
_SKIP = ("embed", "safety", "guard", "retriever", "reward", "coder", "-vl", "vision", "omni", "parse", "rerank")
_DISCOVERED: list[str] | None = None


def discover_models() -> list[str]:
    """Live chat models on this key (GET /v1/models), in preference order. Cached per process."""
    global _DISCOVERED
    if _DISCOVERED is not None:
        return _DISCOVERED
    out: list[str] = []
    key = get_key()
    if key and os.getenv("LLM_MODEL_DISCOVERY", "1") != "0":
        try:
            resp = _http.get(f"{_BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
            ids = [str(m.get("id", "")) for m in (resp.json().get("data") or [])] if resp.status_code == 200 else []
            ids = [i for i in ids if not any(x in i.lower() for x in _SKIP)]
            for pref in _PREFER:
                out += sorted([i for i in ids if i.startswith(pref) and i not in out], reverse=True)
        except Exception as e:  # discovery is best-effort
            logger.warning("NVIDIA model discovery failed: %s", _redact(str(e)))
    _DISCOVERED = out
    return out


def get_models() -> list[str]:
    """Model ids in try-order. NVIDIA_MODEL (comma list) wins; else live discovery; else defaults."""
    raw = os.environ.get("NVIDIA_MODEL", "")
    models = [part.strip() for part in raw.split(",") if part.strip()]
    if models:
        return models
    return (discover_models() or list(_DEFAULT_MODELS))[:6]


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


def _reasoning_model(model: str) -> bool:
    """Ultra (and other explicit reasoning ids) think by default.

    On 2026-10-23 viral_yt_short gave nemotron-3-ultra max_tokens=700. The
    hosted default reasoning_effort is high, so the whole budget came back as
    'The user wants me to score...' and the JSON score never started.
    """
    name = (model or "").lower()
    return "ultra" in name or "reason" in name


def _call_model(prompt: str, max_tokens: int, model: str, headers: dict) -> tuple[str | None, dict]:
    """One configured model, including the transient-error backoff."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.92,
        "max_tokens": max_tokens,
        # The Ultra API defaults stream to true. We parse one JSON body.
        "stream": False,
    }
    if _reasoning_model(model):
        payload["reasoning_effort"] = "none"
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    attempts = len(_BACKOFF_S) + 1
    last_failure: dict = {"status_code": 0, "model": model, "error": ""}

    for attempt in range(attempts):
        try:
            resp = _http.post(_URL, headers=headers, json=payload, timeout=_CALL_TIMEOUT_S)
        except Exception as e:
            logger.error(
                "NVIDIA %s request exception (attempt %d/%d): %s",
                model, attempt + 1, attempts, _redact(str(e)),
            )
            return None, {"status_code": 0, "model": model, "error": _redact(str(e))}

        if resp.status_code == 200:
            try:
                body = completion_body(resp)
                text = message_text(body["choices"][0]["message"])
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning("NVIDIA %s returned malformed success payload: %s", model, e)
                return None, {
                    "status_code": 200,
                    "model": model,
                    "error": f"malformed success payload: {e}",
                }
            if text is None or (isinstance(text, str) and not text.strip()):
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

    started = time.time()
    healthy = [m for m in models if not _model_sick(m)]
    if not healthy:
        logger.warning("NVIDIA all configured models unhealthy; failing over to the next provider")
        return None, {"status_code": 0, "model": "", "error": "all NVIDIA models unhealthy (cooldown)"}
    models = healthy
    for index, model in enumerate(models):
        if index and time.time() - started > _CALL_BUDGET_S:
            logger.warning("NVIDIA call budget %.0fs spent; failing over to the next provider", _CALL_BUDGET_S)
            return None, last_failure
        text, usage = _call_model(prompt, max_tokens, model, headers)
        if text is not None:
            _note_model(model, True)
            return text, usage
        last_failure = usage
        status = int(usage.get("status_code") or 0)
        error = str(usage.get("error") or "")
        if status == 0 or "empty content" in error:
            _note_model(model, False)
        if not _try_next_model(status, error):
            return None, last_failure
        if index + 1 < len(models):
            logger.warning(
                "NVIDIA %s %s; trying next configured model %s",
                model, _skip_reason(status, error), models[index + 1],
            )
            continue
        logger.warning(
            "NVIDIA %s %s; no further configured models",
            model, _skip_reason(status, error),
        )
        return None, last_failure

    return None, last_failure


def _try_next_model(status: int, error: str) -> bool:
    """Auth and quota stay on this model. An empty body, timeout, or 404 moves on."""
    if status in _AUTH_STATUS or status in _RETRY_STATUS:
        return False
    if status in _UNAVAILABLE or status == 0:
        return True
    return status == 200 and "empty content" in error


def _skip_reason(status: int, error: str) -> str:
    detail = error or "no body"
    if "empty content" in error:
        return f"returned empty content ({detail})"
    if status == 0:
        return f"request failed ({detail})"
    return f"HTTP {status} — model unavailable ({detail})"


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
