"""GitHub Models inference was retired on 2026-07-30.

Workflows still map GITHUB_MODELS_TOKEN from GITHUB_TOKEN. The old host answers
HTTP 200 with a plaintext OK body, which is not a completion and used to open
the circuit breaker. The provider is not called unless GITHUB_MODELS_ENABLED
is true. There is no free GitHub-hosted replacement. Gemini, Groq, Cerebras,
OpenRouter (:free), Hugging Face, and NVIDIA stay in the chain.
"""
import logging
import os

from content_generator.providers.openai_compat import chat, models_from_env

logger = logging.getLogger(__name__)

_URL = "https://models.github.ai/inference/chat/completions"
MODELS = models_from_env("GITHUB_MODELS", "openai/gpt-4.1-mini,meta/Llama-3.3-70B-Instruct")
_logged = False


def enabled() -> bool:
    return os.getenv("GITHUB_MODELS_ENABLED", "").strip().lower() in ("1", "true", "yes")


def get_key() -> str:
    if not enabled():
        return ""
    return (
        os.environ.get("GITHUB_MODELS_TOKEN", "").strip()
        or os.environ.get("GH_MODELS_TOKEN", "").strip()
    )


def retired_notice() -> str:
    return (
        "GitHub Models was retired on 2026-07-30 and is not called. "
        "Free providers still in the chain: gemini, groq, cerebras, openrouter, "
        "huggingface, nvidia"
    )


def call(prompt: str, max_tokens: int):
    global _logged
    if not enabled():
        if not _logged:
            logger.info("[llm] %s", retired_notice())
            _logged = True
        return None, {}
    text, usage = chat(
        "GitHubModels", _URL, get_key(), MODELS, prompt, max_tokens,
        extra_body={"stream": False},
    )
    if text is None and "retired endpoint placeholder" in str((usage or {}).get("error") or ""):
        logger.warning(
            "[llm] GitHub Models answered with the retired-endpoint OK placeholder; skipping"
        )
        return None, {}
    return text, usage
