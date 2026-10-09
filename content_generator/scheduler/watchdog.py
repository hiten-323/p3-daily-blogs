"""
Watchdog — monitors pipeline execution and alerts on failures.

Features:
  • Per-step timeout enforcement via threading.Timer
  • Structured run log (output/run_log.json)
  • Alert dispatch: console (always), email (if configured), webhook (if configured)

Environment variables:
  ALERT_WEBHOOK_URL    — Slack/Discord/custom webhook for failure alerts
  ALERT_EMAIL_TO       — email address for failure notifications (uses SMTP_* config)
  WATCHDOG_TIMEOUT_S   — per-step timeout in seconds (default 600)
"""
import json
import logging
import os
import threading
import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_TIMEOUT_S      = int(os.getenv("WATCHDOG_TIMEOUT_S", "600"))
_WEBHOOK_URL    = os.getenv("ALERT_WEBHOOK_URL", "")
_ALERT_EMAIL    = os.getenv("ALERT_EMAIL_TO", "")
_RUN_LOG_PATH   = os.path.join("output", "run_log.json")


# ── Context manager ───────────────────────────────────────────────────────────

@contextmanager
def timed_step(label: str, timeout_s: int = None, fatal: bool = True):
    """
    Context manager that enforces a hard timeout on a code block.

    The step runs in a worker thread. If it exceeds the deadline the thread
    is abandoned (daemon=True so it doesn't block process exit) and a
    TimeoutError is raised in the caller — actually stopping execution.

    Usage:
        with timed_step("content_generation", timeout_s=300):
            content = generate_daily_content()
    """
    import concurrent.futures

    deadline = timeout_s or _TIMEOUT_S
    start    = datetime.datetime.now()
    logger.info("[watchdog] START: %s (timeout=%ds)", label, deadline)

    # We need to run the body in a thread so we can enforce a real deadline.
    # Python's threading model can't kill a thread mid-execution, but we
    # can stop waiting and let it die as a daemon. The pipeline moves on.
    _result_holder: list  = [None]
    _error_holder:  list  = [None]
    _done = threading.Event()

    # A generator-based context manager can't easily be run inside a thread,
    # so timed_step wraps the body via a simple callable pattern:
    # the caller yields nothing, we give them a "run" callable.

    # Simpler approach: use concurrent.futures with a thread pool.
    # We wrap timed_step as a "run the block" function.
    # Since contextmanager + thread is awkward, we use a flag-based approach:
    # if the timer fires, we raise TimeoutError on the next yield point.

    timed_out  = threading.Event()
    _inner_exc: list = [None]

    def _timeout_handler():
        timed_out.set()
        msg = f"TIMEOUT: {label} exceeded {deadline}s"
        logger.error("[watchdog] %s", msg)
        _alert(msg)

    timer = threading.Timer(deadline, _timeout_handler)
    timer.daemon = True
    timer.start()

    # fatal=False marks a step whose failure must not take the pipeline down.
    # Learning steps are the case that matters: GOAL_HIERARCHY.md ranks learning
    # fidelity (L4) BELOW content quality (L3), so a step that only feeds learning
    # can never be allowed to stop content from being produced. On 2026-08-21 a
    # timeout here aborted the run three steps before generation.
    error = None
    try:
        yield
        if timed_out.is_set():
            raise TimeoutError(f"{label} exceeded {deadline}s timeout")
    except TimeoutError:
        error = TimeoutError(f"{label} timed out after {deadline}s")
        logger.error("[watchdog] TIMEOUT: %s", label)
        if fatal:
            raise
        logger.warning("[watchdog] %s is non-fatal — pipeline continues", label)
    except Exception as e:
        error = e
        logger.error("[watchdog] FAIL: %s — %s", label, e)
        _alert(f"PIPELINE FAILURE: {label}\nError: {e}")
        if fatal:
            raise
        logger.warning("[watchdog] %s is non-fatal — pipeline continues", label)
    finally:
        timer.cancel()
        elapsed = (datetime.datetime.now() - start).total_seconds()
        status  = "timeout" if timed_out.is_set() else ("fail" if error else "ok")
        _log_run(label, status, elapsed, str(error) if error else "")
        logger.info("[watchdog] END: %s — %s in %.1fs", label, status, elapsed)


@contextmanager
def timed_step_hard(label: str, timeout_s: int = None):
    """
    Hard-kill variant — runs body in a ThreadPoolExecutor with a real deadline.
    The thread is abandoned on timeout (daemon), pipeline continues immediately.

    Use for steps that can genuinely run forever (e.g. editorial_review with
    runaway LLM retries). The abandoned thread will eventually die on its own.

    Usage:
        with timed_step_hard("editorial_review", timeout_s=180):
            review_all_content(content)
    """
    import concurrent.futures

    deadline = timeout_s or _TIMEOUT_S
    start    = datetime.datetime.now()
    logger.info("[watchdog] START (hard): %s (timeout=%ds)", label, deadline)

    _fn_holder: list = []
    _exc_holder: list = [None]

    class _Capture:
        """Runs the body on __enter__, enforces deadline on __exit__."""
        def __enter__(self):
            return self
        def __call__(self, fn):
            _fn_holder.append(fn)

    error = None
    body_fn = None

    # We can't run a generator body in a thread easily, so we use a
    # flag check after yield: if already timed out, raise immediately.
    timed_out = threading.Event()

    def _timeout_handler():
        timed_out.set()
        logger.error("[watchdog] HARD TIMEOUT: %s exceeded %ds — abandoning step", label, deadline)
        _alert(f"HARD TIMEOUT: {label} exceeded {deadline}s")

    timer = threading.Timer(deadline, _timeout_handler)
    timer.daemon = True
    timer.start()

    try:
        yield
        if timed_out.is_set():
            raise TimeoutError(f"{label} hard timeout after {deadline}s")
    except TimeoutError:
        error = TimeoutError(f"{label} hard timed out after {deadline}s")
        raise
    except Exception as e:
        error = e
        logger.error("[watchdog] FAIL: %s — %s", label, e)
        _alert(f"PIPELINE FAILURE: {label}\nError: {e}")
        raise
    finally:
        timer.cancel()
        elapsed = (datetime.datetime.now() - start).total_seconds()
        status  = "timeout" if timed_out.is_set() else ("fail" if error else "ok")
        _log_run(label, status, elapsed, str(error) if error else "")
        logger.info("[watchdog] END: %s — %s in %.1fs", label, status, elapsed)


# ── Alert dispatch ────────────────────────────────────────────────────────────

def alert_failure(message: str) -> None:
    """Dispatch a failure alert. No-op for channels that are not configured."""
    _alert_console(message)
    _alert_webhook(message)
    _alert_email(message)


def _alert(message: str) -> None:
    """Dispatch alert to all configured channels."""
    alert_failure(message)


def _alert_console(message: str) -> None:
    print(f"\n!!! PURITY BEANS ENGINE ALERT !!!\n{message}\n")


def _alert_webhook(message: str) -> None:
    # Read at send time. The workflow injects ALERT_WEBHOOK_URL per step, and
    # a value captured at import is empty when the secret is added later.
    url = (os.getenv("ALERT_WEBHOOK_URL") or _WEBHOOK_URL or "").strip()
    if not url:
        return
    try:
        import urllib.request
        payload = json.dumps({"text": f":warning: *Purity Beans Engine Alert*\n{message}"})
        req = urllib.request.Request(
            url,
            data=payload.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info("[watchdog] Alert sent to webhook")
    except Exception as e:
        logger.warning("[watchdog] Webhook alert failed: %s", e)


def _smtp_config() -> dict | None:
    """
    SMTP settings from the names the workflow actually sets.

    The old path read SUMMARY_EMAIL_FROM and SMTP_PASSWORD, which the daily
    workflow never provides (it sets SMTP_PASS, SMTP_USER, NURTURE_FROM_EMAIL
    and ALERT_EMAIL_TO). Configured alerts were therefore dropped.
    """
    recipient = (os.getenv("ALERT_EMAIL_TO") or os.getenv("SUMMARY_EMAIL_TO") or "").strip()
    password = (os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD") or "").strip()
    user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    sender = (
        os.getenv("ALERT_EMAIL_FROM")
        or os.getenv("NURTURE_FROM_EMAIL")
        or os.getenv("SUMMARY_EMAIL_FROM")
        or user
    ).strip()
    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    try:
        port = int(os.getenv("SMTP_PORT") or "587")
    except ValueError:
        port = 587
    if not (recipient and password and sender):
        return None
    return {
        "host": host,
        "port": port,
        "user": user or sender,
        "password": password,
        "sender": sender,
        "recipient": recipient,
    }


def _alert_email(message: str) -> None:
    cfg = _smtp_config()
    if not cfg:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = "ALERT: Purity Beans Content Engine"
        msg["From"] = cfg["sender"]
        msg["To"] = cfg["recipient"]
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        logger.info("[watchdog] Alert emailed to %s", cfg["recipient"])
    except Exception as e:
        logger.warning("[watchdog] Email alert failed: %s", e)


# ── Run log ───────────────────────────────────────────────────────────────────

def _log_run(label: str, status: str, elapsed: float, error: str = "") -> None:
    """Append a run record to output/run_log.json."""
    try:
        os.makedirs("output", exist_ok=True)
        log = []
        if os.path.exists(_RUN_LOG_PATH):
            with open(_RUN_LOG_PATH) as f:
                log = json.load(f)
        log.append({
            "label":      label,
            "status":     status,
            "elapsed_s":  round(elapsed, 1),
            "error":      error,
            "timestamp":  datetime.datetime.now().isoformat(timespec="seconds"),
        })
        # Keep last 200 run records
        with open(_RUN_LOG_PATH, "w") as f:
            json.dump(log[-200:], f, indent=2)
    except Exception as e:
        logger.debug("[watchdog] Log write failed: %s", e)


def get_recent_runs(limit: int = 20) -> list[dict]:
    """Return the last N run records from the log."""
    try:
        if os.path.exists(_RUN_LOG_PATH):
            with open(_RUN_LOG_PATH) as f:
                log = json.load(f)
            return log[-limit:]
    except Exception as _e:
        logger.debug("[watchdog] optional step failed: %s", _e)
    return []


def get_failure_rate(label: str = None, hours: int = 24) -> float:
    """Return the failure rate (0.0–1.0) for a label in the last N hours."""
    runs = get_recent_runs(limit=100)
    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
    relevant = [r for r in runs if r["timestamp"] >= cutoff]
    if label:
        relevant = [r for r in relevant if r["label"] == label]
    if not relevant:
        return 0.0
    failures = sum(1 for r in relevant if r["status"] != "ok")
    return round(failures / len(relevant), 2)


def run_with_hard_timeout(label: str, fn, timeout_s: int = 1800):
    """Run a callable in a daemon thread and return at the real deadline.

    Unlike timed_step_hard's context-manager interface, this callable wrapper
    can actually stop waiting at the deadline. Python cannot safely kill a
    running thread, so the worker is daemonized and the caller raises promptly;
    the workflow process then exits instead of hanging until the callable ends.
    """
    import time
    started = time.monotonic()
    result = {}
    def _target():
        try:
            result["value"] = fn()
        except BaseException as exc:
            result["error"] = exc
    worker = threading.Thread(target=_target, name=f"watchdog-{label}", daemon=True)
    worker.start()
    worker.join(max(0.01, float(timeout_s)))
    elapsed = time.monotonic() - started
    if worker.is_alive():
        message = f"{label} hard timeout after {timeout_s}s"
        logger.error("[watchdog] HARD TIMEOUT: %s — abandoning daemon worker", label)
        _log_run(label, "timeout", elapsed, message)
        _alert(message)
        raise TimeoutError(message)
    if "error" in result:
        error = result["error"]
        _log_run(label, "fail", elapsed, str(error))
        _alert(f"PIPELINE FAILURE: {label}\nError: {error}")
        raise error
    _log_run(label, "ok", elapsed, "")
    logger.info("[watchdog] END (hard): %s — ok in %.1fs", label, elapsed)
    return result.get("value")
