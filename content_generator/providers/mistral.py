"""Mistral La Plateforme free ("Experiment") tier. Key: MISTRAL_API_KEY."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

_URL = "https://api.mistral.ai/v1/chat/completions"
MODELS = models_from_env("MISTRAL_MODELS", "mistral-small-latest,open-mistral-nemo")


def get_key() -> str:
    return os.environ.get("MISTRAL_API_KEY", "").strip()


def call(prompt: str, max_tokens: int):
    return chat("Mistral", _URL, get_key(), MODELS, prompt, max_tokens)
