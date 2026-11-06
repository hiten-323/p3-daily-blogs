"""GitHub Models (free, rate-limited). Uses GITHUB_MODELS_TOKEN, which the
workflows map from the built-in GITHUB_TOKEN (needs `permissions: models: read`)."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://models.github.ai/inference/chat/completions"
MODELS = models_from_env("GITHUB_MODELS", "openai/gpt-4.1-mini,meta/Llama-3.3-70B-Instruct")


def get_key() -> str:
    return os.environ.get("GITHUB_MODELS_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    # The hosted inference API can answer HTTP 200 with an SSE body. Ask for a
    # single JSON object; completion_body still reassembles a stream if one arrives.
    # A retired catalog answers HTTP 200 with the plaintext body "OK". That is a
    # skip, the same as a missing key, so it does not open the circuit breaker.
    text, usage = chat("GitHubModels", _URL, get_key(), MODELS, prompt, max_tokens,
                       extra_body={"stream": False})
    err = str((usage or {}).get("error") or "")
    if text is None and "unreadable success body" in err and "'OK'" in err:
        return None, {}
    return text, usage
