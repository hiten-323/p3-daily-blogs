"""Cloudflare Workers AI free tier (10k neurons/day), OpenAI-compatible endpoint.
Needs CLOUDFLARE_API_TOKEN (Workers AI permission) and CLOUDFLARE_ACCOUNT_ID."""
import os

from content_generator.providers.openai_compat import chat, models_from_env

MODELS = models_from_env("CLOUDFLARE_MODELS", "@cf/meta/llama-3.3-70b-instruct-fp8-fast,@cf/mistralai/mistral-small-3.1-24b-instruct")


def _account() -> str:
    return os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()


def url() -> str:
    acct = _account()
    return f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1/chat/completions" if acct else ""


def get_key() -> str:
    # Both values are required; report "no key" unless both exist.
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    return token if token and _account() else ""


def call(prompt: str, max_tokens: int):
    return chat("Cloudflare", url(), get_key(), MODELS, prompt, max_tokens)
