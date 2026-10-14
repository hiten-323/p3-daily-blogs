"""OpenRouter API provider (last-resort fallback)."""
import os
import logging
import requests as _http

from content_generator.rotation import WEBSITE_URL

logger = logging.getLogger(__name__)

_URL = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter's free router is maintained as a current pool rather than pinning a
# model that can disappear without notice.
# Pinned instruct models, NOT the openrouter/free auto-router.
#
# The router picks from the whole free pool, which contains
# nvidia/nemotron-3.5-content-safety (a classifier), several reasoning models,
# code models and finance/health-tuned models. On 2026-09-07 it answered
# yt_short with "User Safety: safe" (17 chars) and other labels with reasoning
# prose — "Let me analyze this complex request carefully..." — because it had
# routed to a classifier and to reasoning models. Every one of those parsed to
# nothing and the day fell through to fallback.
#
# These four are instruct-tuned and advertise JSON support; nemotron-3-super
# additionally supports strict structured_outputs.
_DEFAULT_FREE = (
    "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,"
    "minimax/minimax-m2.7:free,nvidia/nemotron-3-super-120b-a12b:free"
)
# Only ':free' models are ever called, so OpenRouter never bills. A configured
# model without the suffix is dropped.
MODELS: list[str] = [
    m.strip() for m in os.getenv("OPENROUTER_MODELS", _DEFAULT_FREE).split(",")
    if m.strip().endswith(":free")
] or _DEFAULT_FREE.split(",")


def get_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """Return the first usable response; model-specific failures fall through."""
    key = get_key()
    if not key:
        return None, {}

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": f"https://{WEBSITE_URL}",
        "X-Title": "Purity Beans Social Engine",
    }
    last_failure: dict = {}

    for model in (m.strip() for m in MODELS if m.strip()):
        try:
            resp = _http.post(
                _URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.92,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
        except Exception as e:
            logger.error("OpenRouter %s request exception: %s", model, e)
            last_failure = {"status_code": 0, "model": model, "error": str(e)}
            continue

        if resp.status_code == 200:
            try:
                body = resp.json()
                text = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning("OpenRouter %s returned malformed success payload: %s", model, e)
                last_failure = {"status_code": 200, "model": model,
                                "error": f"malformed success payload: {e}"}
                continue
            u = body.get("usage", {})
            return text, {
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "model": model,
            }

        last_failure = {"status_code": resp.status_code, "model": model,
                        "error": resp.text}
        logger.warning("OpenRouter %s %s: %s", model, resp.status_code, resp.text[:200])
        if resp.status_code in (401, 403):
            return None, last_failure
        continue

    return None, last_failure
