"""
Operational telemetry — publisher diagnostics + quality metrics.

Two record types, both appended to output/learning/ (persisted across CI runs):

  publish_diagnostics.json  one record per publish ATTEMPT (per platform)
  quality_telemetry.json    one record per pipeline RUN (latencies, rates)

Design notes:
- Never raises. Telemetry must not be able to break a publish or a run.
- Responses are sanitized (tokens/keys stripped, body truncated) before storage.
- report() gives 7-day rolling views by platform / model / failure reason.
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

try:                                  # single source of truth for versions
    from content_generator.core.versions import PUBLISHER_VERSION
except Exception:                     # pragma: no cover - fallback if import order shifts
    PUBLISHER_VERSION = "2.3.0"

_LEARNING_DIR = lambda: os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_PUB_LOG      = lambda: os.path.join(_LEARNING_DIR(), "publish_diagnostics.json")
_QUAL_LOG     = lambda: os.path.join(_LEARNING_DIR(), "quality_telemetry.json")

_MAX_RECORDS  = 2000
_SECRET_RE    = re.compile(
    r'(access_token|api_key|token|secret|password|authorization)["\'=:\s]+[^\s"\'&,}]+',
    re.I,
)


# ── storage helpers (never raise) ────────────────────────────────────────────

def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug("[telemetry] could not read %s: %s", path, e)
        return []


def _append(path: str, record: dict) -> None:
    try:
        entries = _load(path)
        entries.append(record)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries[-_MAX_RECORDS:], f, indent=2, default=str)
    except Exception as e:
        logger.debug("[telemetry] could not write %s: %s", path, e)


def _sanitize(value, limit: int = 600) -> str:
    """Strip credentials and truncate — safe to commit to the repo."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        text = str(value)
    text = _SECRET_RE.sub(r"\1=<redacted>", text)
    return text[:limit]


def classify_failure(error: str, http_status: int | None = None) -> str:
    """Bucket a failure so trends are groupable."""
    e = (error or "").lower()
    # HTTP status is authoritative when present (a 429 whose body mentions
    # "access_token" is a rate limit, not an auth failure).
    if http_status == 429:
        return "rate_limit"
    if http_status in (401, 403):
        return "auth"
    if http_status and 500 <= http_status < 600:
        return "upstream_5xx"
    if "rate limit" in e or "quota" in e or "429" in e:
        return "rate_limit"
    if "token" in e or "oauth" in e or "permission" in e or "unauthor" in e:
        return "auth"
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if "not_configured" in e:
        return "not_configured"
    if "held_for_timed_slot" in e:
        return "held"
    if "no_" in e or "missing" in e or "empty" in e:
        return "missing_input"
    if http_status and 400 <= http_status < 500:
        return "bad_request"
    return "other" if e else "none"


# ── 1. Publisher diagnostics ─────────────────────────────────────────────────

def record_publish(
    platform: str,
    result: dict,
    duration_ms: int,
    content_id: str = "",
    generation_id: str = "",
    day_number: int | None = None,
    retry_count: int = 0,
    http_status: int | None = None,
    rate_limit: dict | None = None,
    exception: BaseException | None = None,
) -> dict:
    """Record one publish attempt. Returns the stored record."""
    result = result or {}
    success = bool(result.get("success"))
    error = "" if success else str(result.get("error", ""))
    status = "success" if success else ("held" if result.get("held") else "failure")

    record = {
        "ts":              datetime.datetime.now().isoformat(timespec="seconds"),
        "day_number":      day_number,
        "platform":        platform,
        "content_id":      content_id,
        "generation_id":   generation_id,
        "publisher_version": PUBLISHER_VERSION,
        "status":          status,
        "duration_ms":     int(duration_ms),
        "http_status":     http_status,
        "retry_count":     int(retry_count),
        "failure_class":   classify_failure(error, http_status) if not success else "none",
        "error":           _sanitize(error, 300),
        "response":        _sanitize({k: v for k, v in result.items() if k != "error"}, 400),
        "rate_limit":      rate_limit or {},
        "exception_type":  type(exception).__name__ if exception else "",
        "exception_msg":   _sanitize(str(exception), 300) if exception else "",
    }
    _append(_PUB_LOG(), record)
    logger.info("[telemetry] %s %s in %dms (%s)",
                platform, status, record["duration_ms"], record["failure_class"])
    return record


# ── 2. Quality telemetry (per pipeline run) ──────────────────────────────────

def record_quality(
    day_number: int | None = None,
    generation_ms: int = 0,
    validation_ms: int = 0,
    publish_ms: int = 0,
    editorial_scores: list | None = None,
    confidences: list | None = None,
    assets_generated: int = 0,
    assets_valid: int = 0,
    schema_failures: int = 0,
    brand_failures: int = 0,
    editorial_rejections: int = 0,
    retries: int = 0,
    providers_used: dict | None = None,
    emergency: bool = False,
) -> dict:
    scores = [float(s) for s in (editorial_scores or []) if s is not None]
    confs  = [float(c) for c in (confidences or []) if c is not None]
    total  = max(assets_generated, 1)

    record = {
        "ts":                 datetime.datetime.now().isoformat(timespec="seconds"),
        "date":               today_ist().isoformat(),
        "day_number":         day_number,
        "generation_ms":      int(generation_ms),
        "validation_ms":      int(validation_ms),
        "publish_ms":         int(publish_ms),
        "assets_generated":   assets_generated,
        "assets_valid":       assets_valid,
        "throughput":         assets_generated,
        "avg_editorial_score": round(sum(scores) / len(scores), 2) if scores else None,
        "min_editorial_score": round(min(scores), 2) if scores else None,
        "max_editorial_score": round(max(scores), 2) if scores else None,
        "avg_confidence":     round(sum(confs) / len(confs), 2) if confs else None,
        "schema_failure_rate":    round(schema_failures / total, 3),
        "brand_failure_rate":     round(brand_failures / total, 3),
        "editorial_reject_rate":  round(editorial_rejections / total, 3),
        "retry_count":        retries,
        "providers_used":     providers_used or {},
        "emergency":          emergency,
    }
    _append(_QUAL_LOG(), record)
    return record


# ── 3. Reporting (7-day rolling) ─────────────────────────────────────────────

def report(days: int = 7) -> dict:
    """Rolling operational report: per-platform, per-model, failure reasons."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

    pub = [r for r in _load(_PUB_LOG()) if str(r.get("ts", "")) >= cutoff]
    qual = [r for r in _load(_QUAL_LOG()) if str(r.get("ts", "")) >= cutoff]

    # per-platform publish stats
    platforms: dict = {}
    for r in pub:
        p = platforms.setdefault(r.get("platform", "?"),
                                 {"attempts": 0, "success": 0, "held": 0,
                                  "failure": 0, "durations": [], "retries": 0})
        p["attempts"] += 1
        p[r.get("status", "failure")] = p.get(r.get("status", "failure"), 0) + 1
        p["durations"].append(r.get("duration_ms", 0))
        p["retries"] += r.get("retry_count", 0)
    for p in platforms.values():
        d = p.pop("durations") or [0]
        p["avg_duration_ms"] = int(sum(d) / len(d))
        attempted = p["attempts"] - p.get("held", 0)
        p["success_rate"] = round(p.get("success", 0) / attempted, 3) if attempted else None

    # failure reasons
    reasons: dict = {}
    for r in pub:
        if r.get("status") == "failure":
            reasons[r.get("failure_class", "other")] = reasons.get(r.get("failure_class", "other"), 0) + 1

    # per-model usage
    models: dict = {}
    for r in qual:
        for m, n in (r.get("providers_used") or {}).items():
            models[m] = models.get(m, 0) + (n if isinstance(n, int) else 1)

    def _avg(key):
        vals = [r[key] for r in qual if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "window_days":        days,
        "publish_attempts":   len(pub),
        "runs":               len(qual),
        "by_platform":        platforms,
        "failure_reasons":    reasons,
        "models_used":        models,
        "avg_editorial_score":   _avg("avg_editorial_score"),
        "avg_confidence":        _avg("avg_confidence"),
        "avg_generation_ms":     _avg("generation_ms"),
        "avg_publish_ms":        _avg("publish_ms"),
        "avg_editorial_reject_rate": _avg("editorial_reject_rate"),
        "avg_schema_failure_rate":   _avg("schema_failure_rate"),
        "avg_brand_failure_rate":    _avg("brand_failure_rate"),
        "emergency_runs":     sum(1 for r in qual if r.get("emergency")),
    }


def format_report(days: int = 7) -> str:
    """Human-readable block for the daily summary / founder brief."""
    r = report(days)
    lines = [f"OPERATIONS ({days}d): {r['runs']} runs, {r['publish_attempts']} publish attempts"]
    for name, p in sorted(r["by_platform"].items()):
        sr = "n/a" if p["success_rate"] is None else f"{p['success_rate']*100:.0f}%"
        lines.append(f"  {name:<10} success {sr:<5} avg {p['avg_duration_ms']}ms"
                     + (f" | held {p['held']}" if p.get("held") else ""))
    if r["failure_reasons"]:
        lines.append("  failures: " + ", ".join(f"{k}={v}" for k, v in r["failure_reasons"].items()))
    if r["avg_editorial_score"] is not None:
        lines.append(f"  editorial avg {r['avg_editorial_score']} | "
                     f"reject rate {r['avg_editorial_reject_rate']} | "
                     f"confidence {r['avg_confidence']}")
    if r["emergency_runs"]:
        lines.append(f"  ** {r['emergency_runs']} emergency run(s) in window **")
    return "\n".join(lines)
