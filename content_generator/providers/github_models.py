"""GitHub Models. The inference API was retired on 2026-07-30.

Workflows still map GITHUB_MODELS_TOKEN from GITHUB_TOKEN. The old host answers
HTTP 200 with a plaintext OK body, which is not a completion. The first such
reply skips the provider for the rest of the process, the same way a missing
key is skipped, so the router does not open the circuit breaker on it.
"""
import logging
import os

from content_generator.providers.openai_compat import chat, models_from_env

logger = logging.getLogger(__name__)

_URL = "https://models.github.ai/inference/chat/completions"
MODELS = models_from_env("GITHUB_MODELS", "openai/gpt-4.1-mini,meta/Llama-3.3-70B-Instruct")
_state = {"retired": False}


def get_key() -> str:
    return os.environ.get("GITHUB_MODELS_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    # A retired host is not a failed score. Returning no usage matches the
    # missing-key path: the router moves on and does not record a failure.
    if _state["retired"] or not get_key():
        return None, {}
    text, usage = chat("GitHubModels", _URL, get_key(), MODELS, prompt, max_tokens,
                       extra_body={"stream": False})
    if text is None and "retired endpoint placeholder" in str((usage or {}).get("error") or ""):
        _state["retired"] = True
        logger.warning(
            "GitHub Models inference is retired (HTTP 200 plaintext OK); "
            "skipping it for this process"
        )
        return None, {}
    return text, usage
