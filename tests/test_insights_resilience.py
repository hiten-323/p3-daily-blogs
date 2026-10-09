"""
Insights must never be able to stop content.

Reproduces the 2026-08-21 generate run, which produced nothing at all:

    55 media x 4 metric sets = ~220 requests, every one HTTP 400
    [watchdog] TIMEOUT: insights_fetch exceeded 60s
    TimeoutError: insights_fetch exceeded 60s timeout   <- killed the process

Content generation was three steps later and never ran. GOAL_HIERARCHY.md ranks
learning fidelity (L4) below content quality (L3), so a step that only feeds
learning must not be able to prevent content from being produced.
"""
from __future__ import annotations

import io
import urllib.error

import pytest

from content_generator.analytics import insights_fetcher as insights
from content_generator.scheduler.watchdog import timed_step


def _http_400(body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://graph.facebook.com/v24.0/123/insights",
        400, "Bad Request", {}, io.BytesIO(body),
    )


# ── watchdog ─────────────────────────────────────────────────────────────────

def test_fatal_step_still_raises() -> None:
    """The default must not change — a real pipeline step failing is fatal."""
    with pytest.raises(RuntimeError):
        with timed_step("publish", timeout_s=5):
            raise RuntimeError("publish exploded")


def test_non_fatal_step_is_suppressed() -> None:
    with timed_step("insights_fetch", timeout_s=5, fatal=False):
        raise RuntimeError("Graph API is down")
    # Reaching here is the assertion: the pipeline continued.


# ── the Graph error body ─────────────────────────────────────────────────────

def test_error_detail_includes_the_response_body() -> None:
    """
    str(HTTPError) is only "HTTP Error 400: Bad Request". Every 400 this engine
    ever logged looked like that, so the cause was never visible and the fault
    went undiagnosed for days. The body names it.
    """
    err = _http_400(
        b'{"error":{"message":"(#10) Application does not have permission '
        b'for this action","code":10}}'
    )
    detail = insights._error_detail(err, token=None)
    assert "does not have permission" in detail
    assert "code" in detail


def test_error_detail_redacts_the_access_token() -> None:
    token = "IGAAsecrettokenvalue"
    err = _http_400(b'{"error":{"message":"bad token IGAAsecrettokenvalue"}}')
    detail = insights._error_detail(err, token=token)
    assert token not in detail
    assert "***" in detail


# ── circuit breaker ──────────────────────────────────────────────────────────

def test_circuit_opens_after_consecutive_failures(monkeypatch) -> None:
    insights._reset_circuit()
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    calls = {"n": 0}

    def _always_400(*_a, **_kw):
        calls["n"] += 1
        raise _http_400(b'{"error":{"message":"nope"}}')

    monkeypatch.setattr(insights.urllib.request, "urlopen", _always_400)

    for _ in range(200):
        insights._graph_get("123/insights", {"metric": "reach"})

    assert insights._circuit_open
    assert calls["n"] == insights._MAX_CONSECUTIVE_FAILURES, (
        f"made {calls['n']} requests; the breaker exists so that a systemic "
        f"fault costs {insights._MAX_CONSECUTIVE_FAILURES} requests, not 200"
    )
    insights._reset_circuit()


def test_success_resets_the_failure_run(monkeypatch) -> None:
    """A flaky call must not accumulate toward the breaker across a healthy run."""
    insights._reset_circuit()
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    outcomes = iter([False] * 5 + [True] + [False] * 5)

    class _Resp:
        def read(self):
            return b'{"data":[]}'

    def _flaky(*_a, **_kw):
        if next(outcomes):
            return _Resp()
        raise _http_400(b'{"error":{"message":"transient"}}')

    monkeypatch.setattr(insights.urllib.request, "urlopen", _flaky)
    for _ in range(11):
        insights._graph_get("123/insights", {"metric": "reach"})

    assert not insights._circuit_open, "5 fails, a success, then 5 fails is not systemic"
    insights._reset_circuit()


# ── the pipeline wiring itself ───────────────────────────────────────────────

def test_learning_steps_are_declared_non_fatal() -> None:
    """
    The behaviour above is worthless if daily.py stops passing fatal=False, so
    assert the wiring at the call site. These two steps only feed learning.
    """
    import inspect
    from content_generator.scheduler import daily

    src = inspect.getsource(daily._run_generate_slot)
    for label in ("insights_fetch", "revenue_attribution"):
        line = next(ln for ln in src.splitlines() if f'timed_step("{label}"' in ln)
        assert "fatal=False" in line, (
            f"{label} feeds learning only — it must not be able to abort the "
            f"pipeline before content is generated. Got: {line.strip()}"
        )


# ── access diagnostic ────────────────────────────────────────────────────────

def test_diagnostic_names_the_missing_scopes(monkeypatch, caplog) -> None:
    """
    The engine spent two weeks unable to say why /insights 400s while
    followers_count succeeds. The diagnostic must name the cause, not hint.
    """
    insights._reset_circuit()
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784")

    def _fake(path, params, bypass_circuit=False):
        if path == "debug_token":
            return {"data": {"type": "USER", "is_valid": True,
                             "scopes": ["instagram_basic", "pages_show_list"]}}
        return {"username": "puritybeans", "account_type": "BUSINESS"}

    monkeypatch.setattr(insights, "_graph_get", _fake)
    with caplog.at_level("ERROR"):
        found = insights.diagnose_access()

    assert found["missing_scopes"] == ["instagram_manage_insights", "pages_read_engagement"]
    assert "instagram_manage_insights" in caplog.text
    assert "MISSING for media insights" in caplog.text


def test_diagnostic_reports_a_personal_account(monkeypatch, caplog) -> None:
    insights._reset_circuit()
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1784")

    def _fake(path, params, bypass_circuit=False):
        if path == "debug_token":
            return {"data": {"scopes": list(insights._INSIGHTS_SCOPES)}}
        return {"username": "puritybeans", "account_type": "PERSONAL"}

    monkeypatch.setattr(insights, "_graph_get", _fake)
    with caplog.at_level("ERROR"):
        found = insights.diagnose_access()

    assert found["account_type"] == "PERSONAL"
    assert "media insights are unavailable" in caplog.text
    # Scopes are all present, so it must say so rather than blame them.
    assert "scope theory is" in caplog.text


def test_diagnostic_runs_even_though_the_breaker_is_open(monkeypatch) -> None:
    """It only runs when the circuit is open, so it must be exempt from it."""
    insights._reset_circuit()
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "t")
    insights._circuit_open = True
    seen = {}

    class _Resp:
        def read(self):
            return b'{"data":{"scopes":["instagram_basic"]}}'

    def _urlopen(req, timeout=None):
        seen["called"] = True
        return _Resp()

    monkeypatch.setattr(insights.urllib.request, "urlopen", _urlopen)
    assert insights._graph_get("debug_token", {}, bypass_circuit=True) is not None
    assert seen.get("called"), "the diagnostic must bypass the breaker it reports on"
    assert insights._graph_get("123/insights", {}) is None, "normal calls stay blocked"
    insights._reset_circuit()


def test_abandoned_window_does_not_starve_later_measurements() -> None:
    """A 24h window exhausted after five failures must not block 72h/7d."""
    post = {
        "published_at": "2026-10-01T00:00:00",
        "measurement_snapshots": [],
        "failed_windows": ["24h"],
    }
    # At 30h the failed 24h window is skipped, but 72h is not due yet.
    assert insights._next_due_window(
        post, insights.datetime.datetime(2026, 10, 2, 6, 0, 0)
    ) is None
    # At 80h the 72h window can proceed despite the abandoned 24h window.
    assert insights._next_due_window(
        post, insights.datetime.datetime(2026, 10, 4, 8, 0, 0)
    ) == ("72h", 72)


def test_completed_window_is_not_repeated() -> None:
    post = {
        "published_at": "2026-10-01T00:00:00",
        "measurement_snapshots": [{"window": "24h", "metrics": {"reach": 10}}],
        "failed_windows": [],
    }
    assert insights._next_due_window(
        post, insights.datetime.datetime(2026, 10, 4, 8, 0, 0)
    ) == ("72h", 72)
