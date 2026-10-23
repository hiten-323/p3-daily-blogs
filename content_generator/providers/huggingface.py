"""Hugging Face Inference Providers (free monthly credits). Key: HF_TOKEN."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://router.huggingface.co/v1/chat/completions"
# 2026-10-23: Qwen/Qwen2.5-72B-Instruct is not on the HF router. The account
# got HTTP 400 model_not_supported ("not supported by any provider you have
# enabled") and that 400 was the provider's last error, so the cascade stopped
# looking like a dead model id. Qwen/Qwen3-8B is a live router model
# (nscale, featherless-ai). Llama-3.3-70B-Instruct stays; a 402 there is
# billing, not a missing id.
MODELS = models_from_env(
    "HF_MODELS",
    "meta-llama/Llama-3.3-70B-Instruct,Qwen/Qwen3-8B",
)


def get_key() -> str:
    return os.environ.get("HF_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    return chat("HuggingFace", _URL, get_key(), MODELS, prompt, max_tokens)
