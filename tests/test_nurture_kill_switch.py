"""Customer nurture must be independently opted in from content generation."""

from content_generator.scheduler import daily


def test_nurture_dispatch_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NURTURE_ENABLED", raising=False)
    result = daily._do_nurture()
    assert result["skipped"] is True
    assert result["reason"] == "nurture_disabled"
    assert result["dispatched"] == 0


def test_nurture_dispatch_requires_explicit_true(monkeypatch):
    monkeypatch.setenv("NURTURE_ENABLED", "0")
    result = daily._do_nurture()
    assert result["skipped"] is True
    assert result["reason"] == "nurture_disabled"
