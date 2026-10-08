"""One real chat completion per LLM provider, for the dry-run workflow.

No retries and no /models listing. NVIDIA is a chat completion, same as production.
An HTTP 200 whose message content is empty or whitespace fails the NVIDIA check:
that is the failure mode that burned the editorial deadline in run 341.
"""
from __future__ import annotations

import json
import logging

import requests

from content_generator.providers import cerebras, deepseek, gemini, groq, nvidia, openrouter
from content_generator.providers.llm_router import _KEY_GETTERS, _redact
from content_generator.rotation import WEBSITE_URL

logger = logging.getLogger(__name__)

_MAX_TOKENS = 16
_PROMPT = "Reply with OK."
_TIMEOUT = 20


def _first_model(models: list[str]) -> str:
    for model in models:
        text = str(model).strip()
        if text:
            return text
    return ""


def _clip(text: str, key: str) -> str:
    out = _redact(str(text or ""), limit=160)
    if key:
        out = out.replace(key, "***")
    return " ".join(out.split())[:160]


def _message_text(resp: requests.Response) -> str:
    """OpenAI-style message content. Missing or unparsable content is empty."""
    raw = getattr(resp, "text", "") or ""
    try:
        body = json.loads(raw)
        content = body["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return ""
    if content is None:
        return ""
    return str(content)


def _outcome(resp: requests.Response, key: str, *, reject_empty: bool = False) -> str:
    if resp.status_code == 200:
        if reject_empty and not _message_text(resp).strip():
            return "empty content"
        return "OK"
    body = " ".join((resp.text or "").split())
    return _clip(f"HTTP {resp.status_code} {body}".strip(), key)


def _post(
    url: str,
    *,
    headers: dict,
    payload: dict,
    key: str,
    params: dict | None = None,
    reject_empty: bool = False,
) -> str:
    try:
        resp = requests.post(url, headers=headers, json=payload, params=params, timeout=_TIMEOUT)
    except Exception as exc:
        return _clip(f"{type(exc).__name__}: {exc}", key)
    return _outcome(resp, key, reject_empty=reject_empty)


def _openai_chat(
    url: str,
    key: str,
    model: str,
    extra_headers: dict | None = None,
    *,
    reject_empty: bool = False,
) -> str:
    if not key or not model:
        return "skipped"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return _post(
        url,
        headers=headers,
        payload={
            "model": model,
            "messages": [{"role": "user", "content": _PROMPT}],
            "temperature": 0,
            "max_tokens": _MAX_TOKENS,
        },
        key=key,
        reject_empty=reject_empty,
    )


def _gemini_chat(key: str) -> str:
    if not key:
        return "skipped"
    model = (gemini._MODEL or "").strip()
    if not model:
        return "skipped"
    return _post(
        f"{gemini._BASE}/{model}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": key},
        payload={
            "contents": [{"parts": [{"text": _PROMPT}]}],
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        },
        key=key,
    )


def probe_results() -> list[tuple[str, str]]:
    """One tiny chat call per provider. Missing keys are skipped, not errors."""
    return [
        ("nvidia", _openai_chat(nvidia._URL, nvidia.get_key(), nvidia.get_model(), reject_empty=True)),
        ("groq", _openai_chat(groq._URL, groq.get_key(), _first_model(groq.MODELS))),
        ("gemini", _gemini_chat(gemini.get_key())),
        ("cerebras", _openai_chat(cerebras._URL, cerebras.get_key(), _first_model(cerebras.MODELS))),
        ("deepseek", _openai_chat(deepseek._URL, deepseek.get_key(), _first_model(deepseek.MODELS))),
        (
            "openrouter",
            _openai_chat(
                openrouter._URL,
                openrouter.get_key(),
                _first_model(openrouter.MODELS),
                {
                    "HTTP-Referer": f"https://{WEBSITE_URL}",
                    "X-Title": "Purity Beans Social Engine",
                },
            ),
        ),
    ]


def main() -> int:
    present = [name for name, getter in _KEY_GETTERS if getter()]
    summary = "providers with keys: " + (", ".join(present) if present else "(none)")
    print(summary)
    logger.info("[llm] %s", summary)
    rows = probe_results()
    for name, status in rows:
        row = f"{name}: {status}"
        print(row)
        logger.info("[llm] probe %s", row)
    nvidia_status = dict(rows).get("nvidia", "skipped")
    if nvidia_status == "empty content":
        print("::error::NVIDIA probe returned empty content")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
