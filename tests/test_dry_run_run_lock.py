import pytest

def test_dry_run_bypasses_run_lock(monkeypatch):
    import os
    from content_generator.scheduler import daily
    from content_generator.scheduler.run_lock import RunLock

    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(RunLock, "__enter__", lambda self: setattr(self, "already_ran", True))
    monkeypatch.setattr(daily, "_run_generate_slot", lambda day=None: {"executed": True})
    res = daily.run_full_pipeline(day_number=1)
    assert res.get("executed") is True
