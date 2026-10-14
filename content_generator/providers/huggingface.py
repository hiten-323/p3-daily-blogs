"""Hugging Face Inference Providers (free monthly credits). Key: HF_TOKEN."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://router.huggingface.co/v1/chat/completions"
MODELS = models_from_env("HF_MODELS", "meta-llama/Llama-3.3-70B-Instruct,Qwen/Qwen2.5-72B-Instruct")


def get_key() -> str:
    return os.environ.get("HF_TOKEN", "").strip()


def call(prompt: str, max_tokens: int):
    return chat("HuggingFace", _URL, get_key(), MODELS, prompt, max_tokens)
