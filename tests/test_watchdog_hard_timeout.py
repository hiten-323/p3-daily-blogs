import time

import pytest


def test_run_with_hard_timeout_returns_callable_result(monkeypatch):
    from content_generator.scheduler import watchdog
    monkeypatch.setattr(watchdog, "_log_run", lambda *args: None)
    monkeypatch.setattr(watchdog, "_alert", lambda *args: None)
    assert watchdog.run_with_hard_timeout("fast-test", lambda: 42, timeout_s=1) == 42


def test_run_with_hard_timeout_returns_at_deadline(monkeypatch):
    from content_generator.scheduler import watchdog
    monkeypatch.setattr(watchdog, "_log_run", lambda *args: None)
    monkeypatch.setattr(watchdog, "_alert", lambda *args: None)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="hard timeout"):
        watchdog.run_with_hard_timeout("slow-test", lambda: time.sleep(0.25), timeout_s=0.02)
    assert time.monotonic() - started < 0.15


def test_run_with_hard_timeout_propagates_callable_exception(monkeypatch):
    from content_generator.scheduler import watchdog
    monkeypatch.setattr(watchdog, "_log_run", lambda *args: None)
    monkeypatch.setattr(watchdog, "_alert", lambda *args: None)
    def fail():
        raise ValueError("editorial worker failed")
    with pytest.raises(ValueError, match="editorial worker failed"):
        watchdog.run_with_hard_timeout("error-test", fail, timeout_s=1)
