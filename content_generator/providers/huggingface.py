"""Hugging Face Inference Providers (free monthly credits). Key: HF_TOKEN."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://router.huggingface.co/v1/chat/completions"
# 2026-11-06: Qwen/Qwen3-8B is gone from the router catalog (HTTP 400
# model_not_supported). The chain is models that catalog still lists.
# A 402 on Llama is billing, not a missing id.
MODELS = models_from_env(
    "HF_MODELS",
    "meta-llama/Llama-3.3-70B-Instruct,Qwen/Qwen3-32B,"
    "meta-llama/Llama-3.1-8B-Instruct,google/gemma-3-4b-it",
)


def get_key() -> str:
    return os.environ.get("HF_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    return chat("HuggingFace", _URL, get_key(), MODELS, prompt, max_tokens)
