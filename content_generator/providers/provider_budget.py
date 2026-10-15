"""Per-platform starting provider + per-day provider usage budget.

Hiten (2026-10-15): spread free LLM quotas across platforms. Each platform
starts on its own provider (config/provider_routing.json). Usage per provider
(calls, tokens, 429s, remaining-quota headers) is persisted for the IST day in
output/state/provider_usage_<date>.json. A provider over `rotate_at_fraction`
of its known free quota, or that returned a 429 today, is moved behind the
providers with headroom: for this piece and every later one. It is never
removed, so the full failover chain is still the fallback.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "provider_routing.json"
_lock = Lock()
_usage: dict | None = None
_usage_date: str | None = None

# label fragment -> platform route key (first match wins; labels may be
# prefixed with fresh_/regen_/editorial_).
_LABEL_ROUTES = (
    (r"growth_reel|reel", "ig_reel"),
    (r"stor(y|ies)", "stories"),
    (r"carousel|instagram_post|ig_post", "ig_post"),
    (r"linkedin", "linkedin"),
    (r"threads", "threads"),
    (r"facebook|\bfb_", "facebook"),
    (r"yt_short|youtube|short", "yt_short"),
    (r"blog", "blog"),
)


def load_config() -> dict:
    try:
        return json.loads(_CONFIG.read_text(encoding="utf-8"))
    except Exception as e:  # config is optional; default = headroom order
        logger.warning("[llm-budget] routing config unreadable (%s); using headroom order", e)
        return {"routes": {"default": "auto"}, "rotate_at_fraction": 0.8, "daily_free_quota": {}}


def platform_for_label(label: str) -> str:
    low = str(label or "").lower()
    for pattern, route in _LABEL_ROUTES:
        if re.search(pattern, low):
            return route
    return "default"


def _today() -> str:
    try:
        from content_generator.core.ist_dates import today_ist
        return today_ist().isoformat()
    except Exception:
        import datetime
        return (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).date().isoformat()


def _state_path(date: str) -> Path:
    base = Path(os.getenv("PROVIDER_USAGE_DIR", os.path.join("output", "state")))
    return base / f"provider_usage_{date}.json"


def _load(date: str) -> dict:
    global _usage, _usage_date
    if _usage is not None and _usage_date == date:
        return _usage
    path = _state_path(date)
    data: dict = {"date": date, "providers": {}, "pieces": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("providers", {})
            data.setdefault("pieces", [])
        except Exception:
            pass
    _usage, _usage_date = data, date
    return data


def _save(data: dict) -> None:
    path = _state_path(data["date"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[llm-budget] could not persist usage: %s", e)


def reset_for_tests() -> None:
    global _usage, _usage_date
    with _lock:
        _usage, _usage_date = None, None


def usage_snapshot() -> dict:
    with _lock:
        return json.loads(json.dumps(_load(_today())))


def rate_headers(resp) -> dict:
    """Pull remaining-quota headers (x-ratelimit-remaining-requests/-tokens) if present."""
    out = {}
    try:
        h = {k.lower(): v for k, v in (resp.headers or {}).items()}
    except Exception:
        return out
    for key, name in (("x-ratelimit-remaining-requests", "remaining_requests"),
                      ("x-ratelimit-remaining-tokens", "remaining_tokens"),
                      ("x-ratelimit-limit-requests", "limit_requests"),
                      ("x-ratelimit-limit-tokens", "limit_tokens")):
        if key in h:
            try:
                out[name] = int(float(str(h[key]).split(",")[0]))
            except ValueError:
                pass
    return out


def record(provider: str, *, ok: bool, status: int = 0, usage: dict | None = None,
           label: str = "") -> None:
    usage = usage or {}
    with _lock:
        data = _load(_today())
        p = data["providers"].setdefault(provider, {"calls": 0, "ok": 0, "tokens": 0, "429s": 0})
        p["calls"] += 1
        if ok:
            p["ok"] += 1
            p["tokens"] += int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
            data["pieces"].append({"label": label, "provider": provider, "model": usage.get("model", "")})
        if status == 429:
            p["429s"] += 1
        rl = usage.get("ratelimit") or {}
        if rl:
            p["ratelimit"] = rl
        _save(data)


def _fraction_used(provider: str, p: dict, quota: dict) -> float:
    rl = p.get("ratelimit") or {}
    fr = 0.0
    for kind in ("requests", "tokens"):
        rem, lim = rl.get(f"remaining_{kind}"), rl.get(f"limit_{kind}")
        if rem is not None and lim:
            fr = max(fr, 1 - rem / lim)
    q = quota.get(provider) or {}
    if q.get("requests"):
        fr = max(fr, p.get("calls", 0) / q["requests"])
    if q.get("tokens"):
        fr = max(fr, p.get("tokens", 0) / q["tokens"])
    return fr


def near_limit(provider: str, cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    with _lock:
        p = _load(_today())["providers"].get(provider) or {}
    if p.get("429s", 0) > 0:
        return True
    return _fraction_used(provider, p, cfg.get("daily_free_quota", {})) >= float(cfg.get("rotate_at_fraction", 0.8))


def headroom(provider: str, cfg: dict) -> float:
    with _lock:
        p = _load(_today())["providers"].get(provider) or {}
    known = provider in cfg.get("daily_free_quota", {}) or bool(p.get("ratelimit"))
    if not known:  # unknown quota (e.g. paid/slow NVIDIA, DeepSeek): middle of the pack
        return 0.5 - 0.5 * p.get("429s", 0)
    return 1.0 - _fraction_used(provider, p, cfg.get("daily_free_quota", {})) - 0.5 * p.get("429s", 0)


def order_for(label: str, base_order: list[str]) -> list[str]:
    """Provider order for this piece: platform start first, then headroom-sorted,
    providers near their limit last. Every provider in base_order is kept."""
    cfg = load_config()
    routes = cfg.get("routes", {})
    start = routes.get(platform_for_label(label), routes.get("default", "auto"))
    starts = [start] if isinstance(start, str) else list(start or [])
    starts = [s for s in starts if s != "auto" and s in base_order]
    healthy = [n for n in base_order if not near_limit(n, cfg)]
    tired = [n for n in base_order if n not in healthy]
    rest = sorted((n for n in healthy if n not in starts),
                  key=lambda n: (-round(headroom(n, cfg), 2), base_order.index(n)))
    ordered = [s for s in starts if s in healthy] + rest + tired
    if starts and starts[0] in tired:
        logger.warning("[llm-budget] %s: start provider %s near limit/429 — rotating to %s",
                       label, starts[0], ordered[0] if ordered else "-")
    return ordered
