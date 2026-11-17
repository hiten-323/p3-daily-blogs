"""xAI (Grok) API: the main writer and scorer (owner decision, 17 Nov 2026).

OpenAI-compatible chat completions at https://api.x.ai/v1/chat/completions.
xAI is a different company and service from Groq (groq.py).

Key: XAI_API_KEY (GROK_API_KEY is accepted as an alias). A missing key returns
(None, {}) so the router skips xAI instantly and the free chain carries on.
On 429 or 5xx the router moves down the existing chain (llm_router._try_provider).

Models (docs.x.ai/docs/models, Nov 2026): grok-4.7 is the most capable model;
grok-4.3 is the cheaper backup. XAI_MODELS overrides without a code change.
"""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://api.x.ai/v1/chat/completions"
MODELS = models_from_env("XAI_MODELS", "grok-4.7,grok-4.3")
KEY_ENV_NAMES = ("XAI_API_KEY", "GROK_API_KEY")
# Grok 4.x reasons before answering and the reasoning counts against the
# completion budget. A scorer's 800-token cap could leave no room for the JSON.
_MIN_COMPLETION_TOKENS = int(os.getenv("XAI_MIN_COMPLETION_TOKENS", "4000"))


def key_source() -> str:
    """Name of the env var the key came from ('' when none). Never the value."""
    for name in KEY_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    return ""


def get_key() -> str:
    name = key_source()
    return os.environ.get(name, "").strip() if name else ""


def call(prompt: str, max_tokens: int):
    key = get_key()
    if not key:
        return None, {}
    budget = max(int(max_tokens or 0), _MIN_COMPLETION_TOKENS)
    return chat("xAI", _URL, key, MODELS, prompt, budget, extra_body={"stream": False})
