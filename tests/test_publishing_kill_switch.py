"""Global publishing kill-switch contracts for the daily generation slot."""

from pathlib import Path

from content_generator.scheduler import daily


def test_generate_slot_is_generation_only_when_publish_flag_is_missing(monkeypatch):
    monkeypatch.delenv("PUBLISHING_ENABLED", raising=False)

    def unexpected_publish(*_args, **_kwargs):
        raise AssertionError("publisher must not be called while the global hold is active")

    monkeypatch.setattr(daily, "_do_publish", unexpected_publish)
    result = daily._do_publish_if_enabled({"day_number": 7}, 7)

    assert result["skipped"] is True
    assert result["reason"] == "publishing_disabled"
    assert result["published_platforms"] == []


def test_generate_slot_calls_publisher_only_after_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("PUBLISHING_ENABLED", "true")
    expected = {"published_platforms": ["linkedin"], "summary": "published"}
    calls = []
    monkeypatch.setattr(daily, "_do_publish", lambda content, day: calls.append((content, day)) or expected)

    result = daily._do_publish_if_enabled({"day_number": 8}, 8)

    assert result is expected
    assert calls == [({"day_number": 8}, 8)]


def test_daily_workflow_passes_repository_publish_flag_to_python():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"
    )
    assert "PUBLISHING_ENABLED: ${{ vars.PUBLISHING_ENABLED }}" in workflow
