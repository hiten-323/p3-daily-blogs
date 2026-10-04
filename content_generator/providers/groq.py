"""Groq API provider."""
import os
import logging
import requests as _http

logger = logging.getLogger(__name__)

_URL = "https://api.groq.com/openai/v1/chat/completions"

# Env-configurable so models can be updated without a code change
# 2026-09-07: both llama models returned 404 "does not exist or you do not have
# access to it". They are NOT decommissioned — Groq still lists them as
# production — but their free-tier limit now reads ContactSales, so the second
# half of that error is the operative one. gpt-oss-120b/20b are production AND
# free-tier (250K TPM / 1K RPM). Never add openai/gpt-oss-safeguard-20b or
# llama-prompt-guard-*: they are classifiers and answer with a verdict, not content.
MODELS: list[str] = os.getenv(
    "GROQ_MODELS",
    "openai/gpt-oss-120b,openai/gpt-oss-20b",
).split(",")


def get_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


# Free-tier TPM is 8k. A single 11–13k-token prompt is a 413 before any model
# runs. Skip the request and let the router use the next provider.
_TOKEN_LIMIT = int(os.getenv("GROQ_MAX_PROMPT_TOKENS", "8000"))


def _estimated_tokens(prompt: str, max_tokens: int) -> int:
    return max(1, len(prompt) // 4) + max(0, int(max_tokens))


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """
    Tries each model in MODELS in order.
    Returns (text | None, usage_dict) for the first successful response.
    A model-specific failure falls through to the next configured model;
    authentication failures stop immediately because the same key is shared.
    """
    key = get_key()
    if not key:
        return None, {}

    estimate = _estimated_tokens(prompt, max_tokens)
    if estimate > _TOKEN_LIMIT:
        logger.warning(
            "Groq skipped — request is about %d tokens, over the %d token limit",
            estimate, _TOKEN_LIMIT,
        )
        return None, {
            "status_code": 413,
            "model": "",
            "error": f"skipped: ~{estimate} tokens exceeds {_TOKEN_LIMIT}",
        }

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
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
            logger.error("Groq %s request exception: %s", model, e)
            continue

        if resp.status_code == 200:
            try:
                body = resp.json()
                text = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning("Groq %s returned malformed success payload: %s", model, e)
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
        logger.warning("Groq %s %s: %s", model, resp.status_code, resp.text[:200])
        if resp.status_code in (401, 403):
            return None, last_failure
        # 429/4xx/5xx can be model-specific; give the next configured model a chance.
        continue

    return None, last_failure
