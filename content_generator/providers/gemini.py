"""Gemini API provider."""
import os
import logging
import requests as _http
from content_generator.providers.provider_budget import rate_headers

logger = logging.getLogger(__name__)

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Gemini 2.0 Flash was shut down on June 1, 2026. Keep the model configurable,
# but use the current stable production model by default.
# gemini-3.8-flash is current and not deprecated, but it is absent from the
# free-tier rate-limit table — which is why 2026-09-07 saw 503 then 429 quota
# exhausted. Flash-Lite has the largest free TPM allowance and 10k RPD.
_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def get_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """Return (text | None, usage_dict)."""
    key = get_key()
    if not key:
        return None, {}

    url = f"{_BASE}/{_MODEL}:generateContent?key={key}"
    try:
        resp = _http.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                # Gemini 3.8 migration: temperature is intentionally omitted.
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=120,
        )
    except Exception as e:
        logger.error("Gemini request exception: %s", type(e).__name__)
        # Transport error, not "no key": report it so the router counts it correctly.
        return None, {"status_code": 0, "model": _MODEL, "error": type(e).__name__}

    if resp.status_code != 200:
        logger.warning("Gemini %s model=%s: %s", resp.status_code, _MODEL, resp.text[:200])
        return None, {"status_code": resp.status_code, "model": _MODEL,
                      "error": resp.text, "ratelimit": rate_headers(resp)}

    try:
        data = resp.json()
    except ValueError as e:
        logger.warning("Gemini model=%s returned invalid JSON: %s", _MODEL, e)
        return None, {"status_code": 200, "model": _MODEL, "error": "invalid JSON response"}

    candidates = data.get("candidates", [])
    if not candidates:
        logger.warning("Gemini model=%s returned no candidates", _MODEL)
        return None, {"status_code": 200, "model": _MODEL, "error": "no candidates"}

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()

    meta = data.get("usageMetadata", {})
    usage = {
        "prompt_tokens": meta.get("promptTokenCount"),
        "completion_tokens": meta.get("candidatesTokenCount"),
        "model": _MODEL,
        "ratelimit": rate_headers(resp),
    }

    if not text:
        logger.warning("Gemini model=%s candidate had no text", _MODEL)
        usage.update({"status_code": 200, "error": "empty content"})
        return None, usage

    return text, usage
