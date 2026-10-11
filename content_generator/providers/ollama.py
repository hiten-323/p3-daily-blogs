"""
Ollama API provider — local or tunneled self-hosted LLM execution.

Compatible with Ollama's OpenAI-compatible /v1/chat/completions endpoint.
When Ollama is running (either locally at http://localhost:11434/v1 or via a
tunnel at OLLAMA_BASE_URL), it is automatically prepended to the LLM router.
"""
from __future__ import annotations

import logging
import os
import requests as _http

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2:3b"
_CALL_TIMEOUT_S = int(os.getenv("OLLAMA_TIMEOUT", "120"))


def get_base_url() -> str:
    raw = os.getenv("OLLAMA_BASE_URL", "").strip() or os.getenv("OLLAMA_URL", "").strip()
    if not raw:
        return DEFAULT_BASE_URL
    # Ensure /v1 suffix for OpenAI-compatible endpoint
    return raw.rstrip("/") if raw.endswith("/v1") else f"{raw.rstrip('/')}/v1"


def get_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def is_available() -> bool:
    """
    Check if Ollama is accessible and should be used.
    Requires ENABLE_OLLAMA=true or OLLAMA_BASE_URL to be configured,
    and the endpoint to be reachable.
    """
    explicit = os.getenv("ENABLE_OLLAMA", "").strip().lower()
    custom_url = os.getenv("OLLAMA_BASE_URL", "").strip() or os.getenv("OLLAMA_URL", "").strip()

    if explicit in ("false", "0", "no"):
        return False

    # Active only if explicitly enabled or custom URL provided
    if explicit not in ("true", "1", "yes") and not custom_url:
        return False

    # Probe endpoint with 0.8s timeout
    base = get_base_url()
    try:
        resp = _http.get(f"{base}/models", timeout=0.8)
        return resp.status_code == 200
    except Exception:
        return False


def get_key() -> str:
    """Return synthetic key if Ollama is accessible."""
    return "ollama-active" if is_available() else ""


def health_check() -> str:
    """Return 'OK', 'skipped', or error."""
    if not is_available():
        return "skipped"
    base = get_base_url()
    try:
        resp = _http.get(f"{base}/models", timeout=3.0)
        if resp.status_code == 200:
            return "OK"
        return f"HTTP {resp.status_code}"
    except Exception as exc:
        return f"unreachable: {exc}"


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """
    Call Ollama /v1/chat/completions.
    Returns (text | None, usage_dict).
    """
    if not is_available():
        return None, {}

    base = get_base_url()
    model = get_model()
    url = f"{base}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": max_tokens,
    }

    try:
        resp = _http.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=_CALL_TIMEOUT_S,
        )
    except Exception as exc:
        logger.warning("Ollama %s request exception: %s", model, exc)
        return None, {"status_code": 0, "model": model, "error": str(exc)}

    if resp.status_code != 200:
        logger.warning("Ollama %s HTTP %s: %s", model, resp.status_code, resp.text[:200])
        return None, {"status_code": resp.status_code, "model": model, "error": resp.text[:200]}

    try:
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Ollama %s returned malformed response: %s", model, exc)
        return None, {"status_code": 200, "model": model, "error": f"malformed response: {exc}"}

    usage = body.get("usage") or {}
    return text, {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model": model,
    }
