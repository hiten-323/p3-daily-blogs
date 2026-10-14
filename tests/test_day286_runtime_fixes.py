"""Day 286 fixes: keep passing drafts on time limit, NVIDIA timeout, held slot stays green."""
from content_generator.core.publish_contract import build, evaluate


def test_gate_hold_is_green_and_queued_for_retry():
    v = evaluate(build("evening", 286, {}, {}, status="held", reason="canonical_validation_failed"))
    assert v["ok"] and v["retry"] and v["status"] == "held"


def test_stale_hold_still_fails():
    v = evaluate(build("morning", 1, {}, {}, status="held", reason="stale_content — old file"))
    assert not v["ok"]


def test_nvidia_timeout_raised():
    from content_generator.providers import nvidia
    assert nvidia._CALL_TIMEOUT_S >= 45


def test_editorial_deadline_stops_new_attempts(monkeypatch):
    from content_generator.scheduler import daily
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", 0.0)
    assert daily._editorial_deadline_passed()
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", None)
    assert not daily._editorial_deadline_passed()


def test_editorial_skips_pieces_after_deadline_and_keeps_passed(monkeypatch):
    from content_generator.scheduler import daily
    from content_generator.providers import llm_router
    monkeypatch.setattr(llm_router, "any_provider_available", lambda: True)
    monkeypatch.setitem(daily._EDITORIAL_DEADLINE, "at", 0.0)
    passed = {"caption": "ok", "editorial_score": 8.4, "passed": True}
    content = {"day_number": 286, "threads_post": dict(passed), "facebook_post": {"caption": "x"}}
    daily._do_editorial(content)
    assert content["threads_post"]["editorial_score"] == 8.4          # untouched
    assert "time budget" in content["facebook_post"].get("editorial_error", "")
