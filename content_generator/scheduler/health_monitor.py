"""
Health monitor — checks system readiness before each pipeline run.

Checks:
  • API keys present (Gemini, Groq, OpenRouter)
  • DB connectivity (metrics.db writable)
  • Output directory writable
  • Memory store accessible
  • Disk space (warn if < 500 MB free)

Returns a health report dict and raises HealthError for critical failures.
"""
import logging
import os
import shutil
import sqlite3

logger = logging.getLogger(__name__)


class HealthError(RuntimeError):
    """Raised when a critical system check fails and pipeline cannot proceed."""
    pass


def get_health_report() -> dict:
    """
    Run all health checks and return a status report.

    Status values:
      "healthy"  — all checks pass
      "degraded" — some non-critical checks failed (pipeline can continue)
      "critical" — pipeline should not run
    """
    checks: dict[str, dict] = {}

    checks["api_keys"]     = _check_api_keys()
    checks["db"]           = _check_db()
    checks["output_dir"]   = _check_output_dir()
    checks["disk_space"]   = _check_disk_space()
    checks["memory_store"] = _check_memory_store()

    # Determine overall status
    critical_failed = any(
        c["status"] == "fail" and c.get("critical", False)
        for c in checks.values()
    )
    any_failed = any(c["status"] == "fail" for c in checks.values())

    overall = "critical" if critical_failed else ("degraded" if any_failed else "healthy")

    report = {
        "status":  overall,
        "checks":  checks,
        "summary": _summarise(checks),
    }
    logger.info("[health] Status: %s", overall)
    return report


def assert_healthy() -> None:
    """
    Run health checks and raise HealthError if critical checks fail.

    In CI (GitHub Actions) this becomes a hard sys.exit(1) so the workflow
    fails fast with a red X rather than wasting LLM quota on a broken run.
    The failure alert fires via ALERT_WEBHOOK_URL before exit.
    """
    import sys

    report = get_health_report()

    if report["status"] == "critical":
        failed  = [k for k, v in report["checks"].items() if v["status"] == "fail" and v.get("critical")]
        details = "; ".join(
            report["checks"][k].get("message", k) for k in failed
        )
        msg = f"Health check CRITICAL — pipeline aborted.\nFailed: {details}"

        logger.error("[health] %s", msg)
        _send_health_alert(msg, report)

        # Hard exit in CI; raise for daemon/test mode so callers can handle it
        if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
            sys.exit(1)
        raise HealthError(msg)

    if report["status"] == "degraded":
        logger.warning("[health] Degraded mode — continuing with reduced functionality")


def _send_health_alert(message: str, report: dict) -> None:
    """Send a health failure alert through all available channels."""
    try:
        from content_generator.scheduler.watchdog import _alert
        _alert(f"HEALTH CHECK FAILED\n{message}")
    except Exception:
        pass  # Don't let alert failure prevent the exit


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_api_keys() -> dict:
    present = []
    missing = []
    for key, label in [
        ("NVIDIA_API_KEY",     "NVIDIA"),
        ("GROQ_API_KEY",       "Groq"),
        ("GEMINI_API_KEY",     "Gemini"),
        ("CEREBRAS_API_KEY",   "Cerebras"),
        ("DEEPSEEK_API_KEY",   "DeepSeek"),
        ("OPENROUTER_API_KEY", "OpenRouter"),
    ]:
        if os.getenv(key):
            present.append(label)
        else:
            missing.append(label)

    # At least ONE key must be present
    ok = len(present) >= 1
    return {
        "status":   "ok" if ok else "fail",
        "critical": True,
        "present":  present,
        "missing":  missing,
        "message":  f"API keys: {present} available" if ok else f"No API keys found — need at least one of {missing}",
    }


def _check_db() -> dict:
    db_path = os.getenv("METRICS_DB_PATH", os.path.join("output", "metrics.db"))
    try:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        con = sqlite3.connect(db_path)
        con.execute("SELECT 1")
        con.close()
        return {"status": "ok", "critical": False, "message": f"DB accessible at {db_path}"}
    except Exception as e:
        return {"status": "fail", "critical": False, "message": f"DB check failed: {e}"}


def _check_output_dir() -> dict:
    out_dir = os.getenv("OUTPUT_DIR", "output")
    try:
        os.makedirs(out_dir, exist_ok=True)
        test_file = os.path.join(out_dir, ".health_check")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return {"status": "ok", "critical": True, "message": f"Output dir writable: {out_dir}"}
    except Exception as e:
        return {"status": "fail", "critical": True, "message": f"Output dir not writable: {e}"}


def _check_disk_space() -> dict:
    try:
        total, used, free = shutil.disk_usage(".")
        free_mb = free // (1024 * 1024)
        ok      = free_mb >= 500
        return {
            "status":   "ok" if ok else "fail",
            "critical": False,
            "free_mb":  free_mb,
            "message":  f"{free_mb} MB free" + ("" if ok else " — LOW DISK SPACE"),
        }
    except Exception as e:
        return {"status": "fail", "critical": False, "message": f"Disk check failed: {e}"}


def _check_memory_store() -> dict:
    mem_path = os.getenv("SEMANTIC_MEMORY_PATH", os.path.join("output", "content_memory.json"))
    try:
        os.makedirs(os.path.dirname(os.path.abspath(mem_path)), exist_ok=True)
        return {"status": "ok", "critical": False, "message": "Memory store accessible"}
    except Exception as e:
        return {"status": "fail", "critical": False, "message": f"Memory store: {e}"}


def _summarise(checks: dict) -> str:
    ok   = sum(1 for c in checks.values() if c["status"] == "ok")
    fail = sum(1 for c in checks.values() if c["status"] == "fail")
    return f"{ok} passed, {fail} failed"
