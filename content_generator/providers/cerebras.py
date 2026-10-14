"""Cerebras Cloud API provider — generous free tier, very fast inference."""
import os
import logging
import requests as _http

logger = logging.getLogger(__name__)

_URL = "https://api.cerebras.ai/v1/chat/completions"

# zai-glm-4.7 returned 404 model_archived on 2026-09-07; qwen-3.8-27b replaces it.
# NOTE gpt-oss-120b returned 402 payment_required the same run while the catalogue
# lists it free-tier — that is an ACCOUNT state, not a model id, and no value here
# fixes it. Check the Cerebras billing tab if 402s continue.
MODELS: list[str] = os.getenv(
    "CEREBRAS_MODELS",
    "gpt-oss-120b,qwen-3.8-27b",
).split(",")


def get_key() -> str:
    return os.environ.get("CEREBRAS_API_KEY", "").strip()


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    import time
    BACKOFF = [2, 5]  # quick failover; the router moves on to the next free provider
    key = get_key()
    if not key:
        return None, {}

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_failure: dict = {}

    for model in (m.strip() for m in MODELS if m.strip()):
        for attempt in range(2):
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
                    timeout=45,
                )
            except Exception as e:
                logger.error("Cerebras %s request exception (attempt %d/2): %s", model, attempt + 1, e)
                last_failure = {"status_code": 0, "model": model, "error": str(e)}
                if attempt < 1:
                    time.sleep(BACKOFF[attempt])
                    continue
                break

            if resp.status_code == 200:
                try:
                    body = resp.json()
                    msg = body["choices"][0]["message"]
                except (KeyError, IndexError, TypeError, ValueError) as e:
                    logger.warning("Cerebras %s returned malformed success payload: %s", model, e)
                    last_failure = {"status_code": 200, "model": model,
                                    "error": f"malformed success payload: {e}"}
                    break
                # reasoning models put output in reasoning_content when content is empty
                text = msg.get("content") or msg.get("reasoning_content") or ""
                if not text:
                    logger.warning("Cerebras %s returned empty content", model)
                    last_failure = {"status_code": 200, "model": model,
                                    "error": "empty content"}
                    break
                u = body.get("usage", {})
                return text, {
                    "prompt_tokens": u.get("prompt_tokens"),
                    "completion_tokens": u.get("completion_tokens"),
                    "model": model,
                }

            last_failure = {"status_code": resp.status_code, "model": model,
                            "error": resp.text}
            if resp.status_code == 429:
                logger.warning("Cerebras %s rate limited (429) — attempt %d/2 — sleeping", model, attempt + 1)
                if attempt < 1:
                    time.sleep(BACKOFF[attempt])
                    continue
                # Quota may be model-specific; try the next configured model.
                break

            logger.warning("Cerebras %s %s: %s", model, resp.status_code, resp.text[:200])
            if resp.status_code in (401, 403):
                return None, last_failure
            # Model/client/server errors may affect only this model; continue.
            break

    return None, last_failure
