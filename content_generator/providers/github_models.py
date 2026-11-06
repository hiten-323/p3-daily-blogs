"""GitHub Models (free, rate-limited). Uses GITHUB_MODELS_TOKEN, which the
workflows map from the built-in GITHUB_TOKEN (needs `permissions: models: read`)."""
import logging
import os
import re

from content_generator.providers.openai_compat import chat, models_from_env

logger = logging.getLogger(__name__)
# The host was retired and now answers HTTP 200 with a plaintext OK. repr()
# of that body is the substring below. It is not a completion.
_RETIRED_OK = re.compile(r"unreadable success body: 'OK(?:\\r\\n|\\n)?'")

_URL = "https://models.github.ai/inference/chat/completions"
MODELS = models_from_env("GITHUB_MODELS", "openai/gpt-4.1-mini,meta/Llama-3.3-70B-Instruct")


def get_key() -> str:
    return os.environ.get("GITHUB_MODELS_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    # The hosted inference API can answer HTTP 200 with an SSE body. Ask for a
    # single JSON object; completion_body still reassembles a stream if one arrives.
    text, usage = chat("GitHubModels", _URL, get_key(), MODELS, prompt, max_tokens,
                       extra_body={"stream": False})
    if text is None and _RETIRED_OK.search(str((usage or {}).get("error") or "")):
        # A dead host must not open the circuit breaker and hide later providers.
        logger.warning("GitHub Models returned the retired OK placeholder; skipping")
        return None, {}
    return text, usage
