"""Global publishing pause contracts: on by default, paused only by config or dry run."""

from pathlib import Path

from content_generator.scheduler import daily


def test_generate_slot_is_generation_only_when_publishing_is_paused(monkeypatch, tmp_path):
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("PUBLISHING_PAUSED", "true")

    def unexpected_publish(*_args, **_kwargs):
        raise AssertionError("publisher must not be called while publishing is paused")

    monkeypatch.setattr(daily, "_do_publish", unexpected_publish)
    result = daily._do_publish_if_enabled({"day_number": 7}, 7)

    assert result["skipped"] is True
    assert result["reason"] == "publishing_disabled"
    assert result["published_platforms"] == []


def test_generate_slot_publishes_by_default_even_when_variable_is_false(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("PUBLISHING_PAUSED", raising=False)
    monkeypatch.setenv("PUBLISHING_ENABLED", "false")
    expected = {"published_platforms": ["linkedin"], "summary": "published"}
    calls = []
    monkeypatch.setattr(daily, "_do_publish", lambda content, day: calls.append((content, day)) or expected)

    result = daily._do_publish_if_enabled({"day_number": 8}, 8)

    assert result is expected
    assert calls == [({"day_number": 8}, 8)]


def test_posting_workflows_are_not_gated_by_the_repo_variable():
    wf = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("daily.yml", "retry-unposted.yml", "publish-recovery.yml"):
        assert "PUBLISHING_ENABLED" not in (wf / name).read_text(encoding="utf-8"), name


def test_paused_retry_reports_nothing_pending(monkeypatch, capsys):
    import sys
    from content_generator.scheduler import retry_unposted, publish_recovery
    monkeypatch.setenv("PUBLISHING_PAUSED", "true")
    monkeypatch.setattr(sys, "argv", ["retry_unposted", "--pending"])
    assert retry_unposted._cli() == 0
    assert capsys.readouterr().out.strip() == "PENDING:"
    monkeypatch.setattr(publish_recovery, "due_retry_groups",
                        lambda: (_ for _ in ()).throw(AssertionError("must not run while paused")))
    assert publish_recovery.main() == 0
