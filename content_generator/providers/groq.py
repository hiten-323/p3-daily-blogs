"""Groq API provider."""
import os
import re
import logging
import requests as _http
from content_generator.providers.openai_compat import message_text
from content_generator.providers.provider_budget import rate_headers

logger = logging.getLogger(__name__)

_URL = "https://api.groq.com/openai/v1/chat/completions"

# Env-configurable so models can be updated without a code change
# 2026-09-07: both llama models returned 404 "does not exist or you do not have
# access to it". They are NOT decommissioned — Groq still lists them as
# production — but their free-tier limit now reads ContactSales, so the second
# half of that error is the operative one. gpt-oss-120b/20b are production AND
# free-tier (250K TPM / 1K RPM). Never add openai/gpt-oss-safeguard-20b or
# llama-prompt-guard-*: they are classifiers and answer with a verdict, not content.
MODELS: list[str] = os.getenv(
    "GROQ_MODELS",
    "openai/gpt-oss-120b,openai/gpt-oss-20b",
).split(",")


def get_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


# Free-tier TPM is 8k. A single 11–13k-token prompt is a 413 before any model
# runs. Skip the request and let the router use the next provider.
_TOKEN_LIMIT = int(os.getenv("GROQ_MAX_PROMPT_TOKENS", "8000"))


def _estimated_tokens(prompt: str, max_tokens: int) -> int:
    return max(1, len(prompt) // 4) + max(0, int(max_tokens))


_PRIORITY = re.compile(
    r"never|must|only|do not|don't|banned|forbid|fssai|chicory|₹|rs\b|price|%|pure|"
    r"ultra blend|bold|prima|purica|purista|json|return|follow|p3online",
    re.IGNORECASE,
)


def compact_prompt(prompt: str, budget_tokens: int) -> str | None:
    """Fit a long prompt under Groq's TPM limit by chunking it into paragraphs.

    The USER REQUEST tail is always kept whole. From everything before it,
    rule/claim/price paragraphs are kept first, then the rest, in original
    order, until the budget is used. The downstream claim and editorial gates
    still check the output, so nothing is relaxed.
    """
    budget_chars = max(0, int(budget_tokens)) * 4
    text = str(prompt or "")
    marker = "USER REQUEST:"
    head, tail = (text.rsplit(marker, 1) if marker in text else ("", text))
    tail = (marker + tail) if head else tail
    if len(tail) > budget_chars:
        # The request itself is too long: chunk it the same way, keeping its last paragraph.
        paras = [p for p in tail.split("\n\n") if p.strip()]
        if not paras:
            return None
        last = paras[-1]
        rest = _pick(paras[:-1], budget_chars - len(last) - 2)
        out = "\n\n".join(rest + [last])
        return out if len(out) <= budget_chars else None
    paras = [p for p in head.split("\n\n") if p.strip()]
    keep = _pick(paras, budget_chars - len(tail) - 2)
    return "\n\n".join(keep + [tail])


def _pick(paras: list[str], budget: int) -> list[str]:
    order = sorted(range(len(paras)), key=lambda i: (0 if _PRIORITY.search(paras[i]) else 1, i))
    chosen, used = set(), 0
    for i in order:
        size = len(paras[i]) + 2
        if used + size <= budget:
            chosen.add(i)
            used += size
        elif _PRIORITY.search(paras[i]) and budget - used > 200:
            # Split a long rule paragraph into lines and keep what fits.
            lines, part = paras[i].split("\n"), []
            for line in lines:
                if used + len(line) + 1 <= budget and _PRIORITY.search(line):
                    part.append(line)
                    used += len(line) + 1
            if part:
                paras[i] = "\n".join(part)
                chosen.add(i)
    return [paras[i] for i in sorted(chosen)]


def call(prompt: str, max_tokens: int) -> tuple[str | None, dict]:
    """
    Tries each model in MODELS in order.
    Returns (text | None, usage_dict) for the first successful response.
    A model-specific failure falls through to the next configured model;
    authentication failures stop immediately because the same key is shared.
    """
    key = get_key()
    if not key:
        return None, {}

    estimate = _estimated_tokens(prompt, max_tokens)
    if estimate > _TOKEN_LIMIT:
        compact = compact_prompt(prompt, _TOKEN_LIMIT - int(max_tokens))
        if compact and _estimated_tokens(compact, max_tokens) <= _TOKEN_LIMIT:
            logger.info("Groq prompt chunked from ~%d to ~%d tokens", estimate,
                        _estimated_tokens(compact, max_tokens))
            prompt, estimate = compact, _estimated_tokens(compact, max_tokens)
    if estimate > _TOKEN_LIMIT:
        logger.warning(
            "Groq skipped — request is about %d tokens, over the %d token limit",
            estimate, _TOKEN_LIMIT,
        )
        return None, {
            "status_code": 413,
            "model": "",
            "error": f"skipped: ~{estimate} tokens exceeds {_TOKEN_LIMIT}",
        }

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    last_failure: dict = {}

    for model in (m.strip() for m in MODELS if m.strip()):
        try:
            resp = _http.post(
                _URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.92,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
        except Exception as e:
            logger.error("Groq %s request exception: %s", model, e)
            continue

        if resp.status_code == 200:
            try:
                body = resp.json()
                msg = body["choices"][0].get("message") or {}
                # gpt-oss often leaves content empty and puts the JSON in reasoning.
                # A 200 with nothing in either field is not an answer.
                text = message_text(msg) if isinstance(msg, dict) else str(msg or "")
            except (KeyError, IndexError, TypeError, ValueError) as e:
                logger.warning("Groq %s returned malformed success payload: %s", model, e)
                last_failure = {"status_code": 200, "model": model,
                                "error": f"malformed success payload: {e}"}
                continue
            if not str(text or "").strip():
                logger.warning("Groq %s HTTP 200 with 0 chars — provider failure, trying next model", model)
                last_failure = {"status_code": 200, "model": model, "error": "empty content"}
                continue
            u = body.get("usage", {})
            return text, {
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "model": model,
                "ratelimit": rate_headers(resp),
            }

        last_failure = {"status_code": resp.status_code, "model": model,
                        "error": resp.text, "ratelimit": rate_headers(resp)}
        logger.warning("Groq %s %s: %s", model, resp.status_code, resp.text[:200])
        if resp.status_code in (401, 403):
            return None, last_failure
        # 429/4xx/5xx can be model-specific; give the next configured model a chance.
        continue

    return None, last_failure
