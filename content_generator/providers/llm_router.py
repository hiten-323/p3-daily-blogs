"""
LLM router — circuit breaker, rate limiter, retry, cost tracking.

Call order: Gemini → Groq → Cerebras → OpenRouter(:free) → GitHub Models →
Mistral → Cloudflare Workers AI → Hugging Face → DeepSeek → NVIDIA (last).
LLM_PROVIDER_ORDER overrides. Missing keys are skipped; failover is quick.
Each provider has an independent circuit breaker: after 3 consecutive failures
it is disabled for 15 minutes before being retried.
A threading.Semaphore(2) limits concurrent outbound API calls to prevent
burst rate-limiting when the pipeline runs tasks in parallel.
"""
import re
import time
import logging
from threading import Semaphore, Lock
from dataclasses import dataclass, field

from content_generator.providers import gemini, groq, openrouter, deepseek, cerebras, nvidia, ollama
from content_generator.providers import github_models, mistral, cloudflare, huggingface
from content_generator.parsers.json_parser import extract

logger = logging.getLogger(__name__)

# ── Rate limiter — max 2 concurrent API calls across all providers ────────────
_API_SEMAPHORE = Semaphore(2)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_CIRCUIT_COOLDOWN_S = 900
_CIRCUIT_TRIP_AT = 3
# A 429 is often per-minute (Groq RPM/TPM). An hour-long trip after two 429s
# left every provider "circuit_open" on day 286, so short cooldown unless the
# error says the daily quota is gone. Rotation to other providers comes from
# provider_budget (any 429 moves that provider behind ones with headroom).
_QUOTA_COOLDOWN_S = 120
_DAILY_QUOTA_COOLDOWN_S = 3600
_QUOTA_TRIP_AT = 2
_DAILY_QUOTA = re.compile(r"per day|daily|RPD|TPD|quota exceeded for metric.*per_day", re.I)


# ── Circuit breaker ───────────────────────────────────────────────────────────

@dataclass
class _ProviderState:
    name: str
    _fail_count: int = field(default=0, repr=False)
    _healthy: bool = field(default=True, repr=False)
    _cooldown_until: float = field(default=0.0, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def is_available(self) -> bool:
        with self._lock:
            if self._healthy:
                return True
            if time.time() > self._cooldown_until:
                logger.info("Circuit breaker RESET for %s", self.name)
                self._healthy = True
                self._fail_count = 0
            return self._healthy

    def record_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._healthy = True

    def record_failure(self, quota_error: bool = False, daily: bool = False) -> None:
        with self._lock:
            self._fail_count += 1
            trip_at = _QUOTA_TRIP_AT if quota_error else _CIRCUIT_TRIP_AT
            cooldown = ((_DAILY_QUOTA_COOLDOWN_S if daily else _QUOTA_COOLDOWN_S)
                        if quota_error else _CIRCUIT_COOLDOWN_S)
            if self._fail_count >= trip_at:
                self._healthy = False
                self._cooldown_until = time.time() + cooldown
                reason = "quota exhausted" if quota_error else "repeated failures"
                logger.warning(
                    "Circuit breaker OPEN for %s (%s) — disabled for %d min",
                    self.name, reason, cooldown // 60,
                )


_STATES = {
    "ollama": _ProviderState("ollama"),
    "nvidia": _ProviderState("nvidia"),
    "gemini": _ProviderState("gemini"),
    "deepseek": _ProviderState("deepseek"),
    "github_models": _ProviderState("github_models"),
    "mistral": _ProviderState("mistral"),
    "cloudflare": _ProviderState("cloudflare"),
    "huggingface": _ProviderState("huggingface"),
    "cerebras": _ProviderState("cerebras"),
    "groq": _ProviderState("groq"),
    "openrouter": _ProviderState("openrouter"),
}

# ── Cascade diagnostics ──────────────────────────────────────────────────────
_cascade_log: list[dict] = []
_cascade_lock = Lock()

_SECRET_PREFIXES = ("sk-", "gsk_", "csk-", "AIza", "Bearer ", "key-", "nvapi-")


def _redact(text: str, limit: int = 200) -> str:
    """Truncate a provider error body and strip anything shaped like a credential."""
    if not text:
        return ""
    out = str(text)
    for token in _SECRET_PREFIXES:
        while token in out:
            i = out.index(token)
            j = i + len(token)
            while j < len(out) and (out[j].isalnum() or out[j] in "-_."):
                j += 1
            out = out[:i] + "***" + out[j:]
    out = " ".join(out.split())
    return out[:limit]


def _record_attempt(**row) -> None:
    with _cascade_lock:
        _cascade_log.append(row)


def get_cascade_log() -> list[dict]:
    """Per-attempt diagnostics for the current run."""
    with _cascade_lock:
        return list(_cascade_log)


def reset_cascade_log() -> None:
    with _cascade_lock:
        _cascade_log.clear()


# Accumulated usage across the run — read by pipeline/generator.py
_usage_log: list[dict] = []
_usage_lock = Lock()


def get_usage_log() -> list[dict]:
    with _usage_lock:
        return list(_usage_log)


def _record_usage(label: str, provider: str, usage: dict) -> None:
    with _usage_lock:
        _usage_log.append({
            "label": label,
            "provider": provider,
            "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
            "completion_tokens": usage.get("completion_tokens", 0) or 0,
        })


_ALL_PROVIDERS = {
    "gemini": gemini.call,
    "nvidia": nvidia.call,
    "groq": groq.call,
    "cerebras": cerebras.call,
    "deepseek": deepseek.call,
    "github_models": github_models.call,
    "mistral": mistral.call,
    "cloudflare": cloudflare.call,
    "huggingface": huggingface.call,
    "openrouter": openrouter.call,
}
# Free providers first (Hiten: any free provider is fine), Gemini leading; it
# answered in ~3s on day 286 while NVIDIA timed out or returned empty. NVIDIA is
# last. Providers without a key return (None, {}) and are skipped instantly.
# LLM_PROVIDER_ORDER="a,b,..." overrides; unnamed providers keep this order after it.
_DEFAULT_ORDER = (
    "gemini", "groq", "cerebras", "openrouter", "github_models",
    "mistral", "cloudflare", "huggingface", "deepseek", "nvidia",
)


def _provider_order() -> list:
    import os
    raw = os.getenv("LLM_PROVIDER_ORDER", "")
    names = [n.strip().lower() for n in raw.split(",") if n.strip().lower() in _ALL_PROVIDERS]
    for n in _DEFAULT_ORDER:
        if n not in names:
            names.append(n)
    return [(n, _ALL_PROVIDERS[n]) for n in names]


_PROVIDERS = _provider_order()

_KEY_GETTERS = (
    ("ollama", ollama.get_key),
    ("nvidia", nvidia.get_key),
    ("groq", groq.get_key),
    ("gemini", gemini.get_key),
    ("cerebras", cerebras.get_key),
    ("deepseek", deepseek.get_key),
    ("github_models", github_models.get_key),
    ("mistral", mistral.get_key),
    ("cloudflare", cloudflare.get_key),
    ("huggingface", huggingface.get_key),
    ("openrouter", openrouter.get_key),
)


def any_provider_available() -> bool:
    """Return True if at least one provider has an API key configured."""
    return any(getter() for _, getter in _KEY_GETTERS)


def log_provider_status() -> None:
    """Startup line: which providers have keys, then one NVIDIA health check.

    Names only. Key values are never logged.
    """
    present = [name for name, getter in _KEY_GETTERS if getter()]
    logger.info(
        "[llm] providers with keys present: %s",
        ", ".join(present) if present else "(none)",
    )
    if nvidia.get_key():
        logger.info("[llm] NVIDIA health check: %s", nvidia.health_check())
    else:
        logger.info("[llm] NVIDIA health check: skipped (no key)")


def _try_provider(
    name: str,
    call_fn,
    prompt: str,
    max_tokens: int,
    label: str,
    retries: int,
) -> str | None:
    """
    Attempt a single provider with exponential backoff on retryable status codes.
    Returns raw text on success, None on permanent failure.
    """
    state = _STATES[name]
    started = time.time()
    if not state.is_available():
        logger.warning("[llm] %-11s SKIPPED — circuit breaker open", name)
        _record_attempt(
            label=label, provider=name, model="", status=0, attempts=0,
            latency_s=0.0, category="circuit_open", detail="",
        )
        return None

    from content_generator.providers import provider_budget
    for attempt in range(retries):
        wait = 15 * (2 ** attempt)
        t0 = time.time()
        with _API_SEMAPHORE:
            text, usage = call_fn(prompt, max_tokens)
        elapsed = time.time() - t0
        # HTTP 200 with an empty body used to be logged as OK (0 chars) and
        # recorded as a successful call, so the next model was never tried and
        # the budget kept the provider in front. Blank text is a failure.
        if isinstance(text, str) and not text.strip():
            usage = dict(usage or {})
            usage.setdefault("status_code", 200)
            if "empty" not in str(usage.get("error") or "").lower():
                usage["error"] = "empty content"
            text = None
        if text is None and not usage:
            # No key configured: skip instantly, never count it as a failure.
            _record_attempt(
                label=label, provider=name, model="", status=0, attempts=attempt + 1,
                latency_s=round(elapsed, 1), category="no_api_key_or_transport", detail="",
            )
            return None
        provider_budget.record(name, ok=text is not None, status=int(usage.get("status_code") or 0),
                               usage=usage, label=label)

        if text is not None:
            state.record_success()
            _record_usage(label, name, usage)
            _record_attempt(
                label=label, provider=name, model=usage.get("model", ""),
                status=200, attempts=attempt + 1, latency_s=round(elapsed, 1),
                category="ok", detail=f"{len(text)} chars",
            )
            logger.info("[llm] %-11s OK  %s (%d chars, %.1fs)", name, label, len(text), elapsed)
            return text

        status = usage.get("status_code", 0)
        model = usage.get("model", "")
        detail = _redact(usage.get("error", ""))

        if status == 0 and not usage:
            category = "no_api_key_or_transport"
        elif status == 429:
            category = "quota_429"
        elif status in (401, 403):
            category = "auth_rejected"
        elif status in _RETRY_STATUSES:
            category = "retryable"
        elif status == 200 and "empty content" in str(detail or "").lower():
            category = "empty_content"
        elif 400 <= status < 500:
            category = "client_error"
        else:
            category = "unknown"

        _record_attempt(
            label=label, provider=name, model=model, status=status,
            attempts=attempt + 1, latency_s=round(elapsed, 1),
            category=category, detail=detail,
        )
        logger.warning(
            "[llm] %-11s FAIL %s status=%s model=%s attempt=%d/%d %.1fs [%s] %s",
            name, label, status or "-", model or "-", attempt + 1, retries,
            elapsed, category, detail,
        )

        if status == 429:
            state.record_failure(quota_error=True, daily=bool(_DAILY_QUOTA.search(detail)))
            return None

        if status in _RETRY_STATUSES:
            if attempt < retries - 1:
                time.sleep(wait)
                continue
            break

        state.record_failure()
        return None

    state.record_failure()
    logger.warning(
        "[llm] %-11s exhausted %d attempts for %s (%.1fs total)",
        name, retries, label, time.time() - started,
    )
    return None


def call(prompt: str, label: str, max_tokens: int = 3000) -> dict:
    """
    Route a prompt through providers in order, parse the response, return a dict.
    A provider that answers with malformed/empty JSON is treated as an unusable
    provider response and the cascade continues. Only after every provider is
    unusable does this raise RuntimeError.
    """
    logger.info("[pipeline] Generating %s ...", label)

    from content_generator.core.brand_guard import build_system_prompt
    system_rules = build_system_prompt()
    full_prompt = f"SYSTEM RULES:\n{system_rules}\n\nUSER REQUEST:\n{prompt}"

    from content_generator.providers import provider_budget
    base = [n for n, _ in _PROVIDERS]
    routed = provider_budget.order_for(label, base)
    fns = dict(_PROVIDERS)
    active_providers = [(n, fns[n]) for n in routed]
    logger.info("[llm-route] %s start=%s order=%s", label, routed[0] if routed else "-", ",".join(routed))
    if ollama.is_available() and _STATES["ollama"].is_available():
        active_providers = [("ollama", ollama.call)] + [p for p in active_providers if p[0] != "ollama"]

    data = _run_cascade(active_providers, full_prompt, max_tokens, label)
    if data is None:
        # Last chance: circuits tripped earlier in this run (e.g. Groq RPM 429s)
        # must not make a keyed provider unreachable for the rest of the run.
        keyed = {n for n, g in _KEY_GETTERS if g()}
        reopen = [(n, f) for n, f in active_providers if n in keyed and not _STATES[n].is_available()]
        if reopen:
            logger.warning("[llm] %s: all providers failed; one last pass ignoring open circuits: %s",
                           label, ",".join(n for n, _ in reopen))
            for n, _ in reopen:
                _STATES[n].record_success()  # half-open: allow one try
            data = _run_cascade(reopen, full_prompt, max_tokens, label)
    if data is not None:
        return data

    _log_cascade_verdict(label)
    raise RuntimeError(
        f"All LLM providers failed for '{label}'. "
        "Set NVIDIA_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY in GitHub Secrets."
    )


def _run_cascade(active_providers, full_prompt: str, max_tokens: int, label: str) -> dict | None:
    for name, fn in active_providers:
        # NVIDIA and Ollama back off or fail fast; others retry
        if name in ("nvidia", "ollama"):
            retries = 1
        elif name == "gemini":
            retries = 2
        elif name in ("groq", "deepseek", "cerebras", "openrouter"):
            retries = 2
        else:
            retries = 1  # free-tier OpenAI-compatible providers: fail over fast
        raw = _try_provider(name, fn, full_prompt, max_tokens, label, retries)
        if not raw:
            continue

        try:
            data = extract(raw)
        except Exception as e:
            _record_attempt(
                label=label, provider=name, model="", status=200,
                attempts=1, latency_s=0.0, category="unparseable",
                detail=_redact(str(e)),
            )
            logger.error(
                "[llm] %s answered %s but the response did not parse: %s; "
                "continuing to next provider",
                name, label, _redact(str(e)),
            )
            continue

        if not data:
            _record_attempt(
                label=label, provider=name, model="", status=200,
                attempts=1, latency_s=0.0, category="parsed_empty",
                detail=f"raw {len(raw)} chars -> empty dict",
            )
            logger.error(
                "[llm] %s answered %s with %d chars that parsed to an EMPTY dict "
                "— failure mode B, continuing to next provider",
                name, label, len(raw),
            )
            continue

        logger.info("[pipeline] %s done via %s (%d keys)", label, name, len(data))
        logger.info("[llm-route] %s PRODUCED_BY=%s", label, name)
        return data
    return None


def _log_cascade_verdict(label: str) -> None:
    """Summarise why a label fell through every provider."""
    rows = [r for r in get_cascade_log() if r.get("label") == label]
    logger.error("[llm] ---- CASCADE FAILED for %s ----", label)
    for r in rows:
        logger.error(
            "[llm]   %-11s status=%-4s model=%-28s %-24s %s",
            r.get("provider"), r.get("status") or "-", r.get("model") or "-",
            r.get("category"), r.get("detail") or "",
        )
    cats = {r.get("category") for r in rows}
    # Order matters. A provider that ANSWERED and produced junk is a different
    # problem from one that never connected, and it must be named first even
    # when some other provider in the cascade also returned a 4xx. On
    # 2026-09-07 this reported yt_short as "a decommissioned model id" because
    # cerebras 404'd, when the actual proximate failure was openrouter
    # answering with reasoning prose instead of JSON — sending the reader to
    # the wrong fix.
    if cats & {"unparseable", "parsed_empty", "empty_content"}:
        hint = ("a provider ANSWERED and the response was unusable — this is not a "
                "cascade outage; inspect the model's output, the prompt and the schema")
    elif cats <= {"no_api_key_or_transport", "circuit_open"}:
        hint = "no provider was actually reachable — check keys are set and non-empty"
    elif cats & {"auth_rejected"}:
        hint = "a provider rejected the credential — the key is present but invalid"
    elif cats & {"quota_429"}:
        hint = "quota exhausted — free tiers reset daily; consider staggering the run"
    elif cats & {"client_error"}:
        hint = "4xx from the provider — most often a decommissioned or misspelled model id"
    else:
        hint = "see per-provider rows above"
    logger.error("[llm]   verdict: %s", hint)
    logger.error("[llm] ---- END CASCADE ----")
