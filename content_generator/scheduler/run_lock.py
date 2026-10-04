"""
Run lock — prevents double execution on the same calendar day.

GitHub Actions can occasionally trigger twice (e.g. a manual re-run
overlapping with the scheduled cron). This lock ensures the full pipeline
runs exactly once per day, no matter how many processes try to start it.

Mechanism:
  - On acquire: write "date|pid|status|timestamp" to the lock file
  - On completion: mark_completed() rewrites the status
  - On check: only a COMPLETED lock from today means "already ran"

THE LOCK RECORDS COMPLETION, NOT MERELY THE START.

The earlier form wrote "date|pid" up front and treated any same-day lock as
proof the day's work was done. But the lock is written BEFORE the work, so a
run that acquired it and then crashed left a lock that read as success — and
because the workflow reports a skipped slot as green, every later slot that day
skipped silently behind a green tick. The lock file is committed to the repo,
so the state survived into the next run rather than dying with the container.

A lock that says "started" and has gone stale is now taken over. Only
"completed" blocks a rerun.

The lock is also date-based, so a crashed run from yesterday never blocks today.

Usage:
    from content_generator.scheduler.run_lock import RunLock

    with RunLock() as lock:
        if lock.already_ran:
            sys.exit(0)
        run_full_pipeline()
    # lock auto-released on exit
"""
from __future__ import annotations
import datetime
import logging
import os

from content_generator.core.ist_dates import today_ist

logger = logging.getLogger(__name__)

_LOCK_FILE = os.path.join("output", ".running")

# A lock still marked "started" after this long is assumed abandoned. The job
# itself is capped at 30 minutes by the workflow, so anything past that cannot
# still be running — and on CI each run is a fresh container, which makes a PID
# liveness check meaningless across runs. Time is the only signal available.
STALE_AFTER_MINUTES = 45

_STATUS_STARTED   = "started"
_STATUS_COMPLETED = "completed"


class RunLock:
    """
    Context manager that acquires/releases the daily run lock.

    Attributes:
        already_ran (bool): True if today's run already completed.
        was_acquired (bool): True if this instance holds the lock.
    """

    def __init__(self, lock_path: str = _LOCK_FILE):
        self._path        = lock_path
        self.already_ran  = False
        self.was_acquired = False

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "RunLock":
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        today = today_ist().isoformat()

        if os.path.exists(self._path):
            try:
                content = open(self._path).read().strip()
                # Format: "YYYY-MM-DD|PID|status|ISO-timestamp".
                # Two-field locks predate the status field; they were written to
                # mean "done", so honour that reading.
                parts     = content.split("|")
                lock_date = parts[0] if parts else ""
                status    = parts[2] if len(parts) > 2 else _STATUS_COMPLETED
                stamp     = parts[3] if len(parts) > 3 else ""

                if lock_date != today:
                    logger.info("[run_lock] Stale lock from %s — clearing", lock_date)
                    os.remove(self._path)
                elif status == _STATUS_COMPLETED:
                    logger.info(
                        "[run_lock] Today's run already completed (lock: %s) — skipping",
                        content,
                    )
                    self.already_ran = True
                    return self
                elif self._is_stale(stamp):
                    # Started but never finished, and too old to still be alive.
                    # Blocking here is what turned one crashed run into a whole
                    # day of silent skips.
                    logger.warning(
                        "[run_lock] Lock says '%s' since %s and has gone stale — "
                        "a previous run acquired it and never completed. Taking over.",
                        status, stamp or "unknown")
                    os.remove(self._path)
                else:
                    logger.info(
                        "[run_lock] A run started at %s is still in flight — skipping",
                        stamp or "unknown")
                    self.already_ran = True
                    return self
            except Exception:
                # Unreadable lock file — treat as stale
                try:
                    os.remove(self._path)
                except Exception as _e:
                    logger.debug("[run_lock] optional step failed: %s", _e)

        # Write the lock as STARTED. It only becomes "completed" when the caller
        # says the work is done.
        try:
            self._write(_STATUS_STARTED)
            self.was_acquired = True
            logger.info("[run_lock] Lock acquired for %s (pid=%d, status=started)",
                        today, os.getpid())
        except Exception as e:
            logger.warning("[run_lock] Could not write lock file: %s — proceeding anyway", e)

        return self

    @staticmethod
    def _is_stale(stamp: str) -> bool:
        """True when a 'started' lock is older than STALE_AFTER_MINUTES."""
        if not stamp:
            return True          # no timestamp to trust — assume abandoned
        try:
            started = datetime.datetime.fromisoformat(stamp)
        except Exception:
            return True
        age_min = (datetime.datetime.now() - started).total_seconds() / 60.0
        return age_min > STALE_AFTER_MINUTES

    def _write(self, status: str) -> None:
        with open(self._path, "w") as f:
            f.write(f"{today_ist().isoformat()}|{os.getpid()}|{status}"
                    f"|{datetime.datetime.now().isoformat(timespec='seconds')}")

    def mark_completed(self) -> None:
        """
        Record that the work actually finished.

        Until this is called the lock reads as "started", so a crashed run is
        retried rather than mistaken for a completed one.
        """
        try:
            self._write(_STATUS_COMPLETED)
            logger.info("[run_lock] Lock marked completed")
        except Exception as e:
            logger.warning("[run_lock] Could not mark lock completed: %s", e)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Keep the lock file on success — it blocks duplicate runs for the rest of today.
        # The next day's run sees a stale date and clears it automatically.
        #
        # Only release if the run crashed mid-flight (exception raised):
        # that lets a retry attempt run again rather than being permanently locked.
        if exc_type is not None and self.was_acquired and not self.already_ran:
            logger.info("[run_lock] Run failed — releasing lock so a retry can proceed")
            self._release()
        # Don't suppress exceptions
        return False

    # ── Manual API ────────────────────────────────────────────────────────────

    def release(self) -> None:
        """Manually release the lock (called after successful completion)."""
        self._release()

    def _release(self) -> None:
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
                logger.info("[run_lock] Lock released")
        except Exception as e:
            logger.warning("[run_lock] Could not release lock: %s", e)

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def is_running() -> bool:
        """Check if a run is currently in progress today (from any process)."""
        if not os.path.exists(_LOCK_FILE):
            return False
        try:
            content   = open(_LOCK_FILE).read().strip()
            lock_date = content.split("|")[0]
            return lock_date == today_ist().isoformat()
        except Exception:
            return False

    @staticmethod
    def force_clear() -> None:
        """Emergency: forcibly remove all locks (use if a run crashed mid-flight)."""
        for filename in (".running", ".running_morning", ".running_evening"):
            path = os.path.join("output", filename)
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info("[run_lock] Lock %s force-cleared", filename)
            except Exception as e:
                logger.warning("[run_lock] Force clear failed for %s: %s", filename, e)
