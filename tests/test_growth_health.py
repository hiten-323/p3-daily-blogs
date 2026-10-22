from pathlib import Path

from content_generator.ops import growth_health


def test_missing_metric_is_unknown_not_zero(monkeypatch, tmp_path):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(growth_health, "LEARNING", tmp_path)
    # A LIST, matching the real shape of performance_log.json. The scanner
    # accepts a list, or a dict keyed posts/entries/records/data — a bare dict
    # is not a shape it has ever seen in production, so the fixture was wrong,
    # not the implementation.
    (tmp_path / "post.json").write_text(
        '[{"metrics": {"reach": 100}}]', encoding="utf-8"
    )
    result = growth_health.measurement_health()
    assert result["records"] == 1
    assert result["measured_views"] == 0
    assert result["unknown_views"] == 1
    assert result["status"] == "cold"


def test_duplicate_attribution_ids_are_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(growth_health, "LEARNING", tmp_path)
    (tmp_path / "attributed_orders.json").write_text(
        '["1001", "1001"]', encoding="utf-8"
    )
    result = growth_health.attribution_health()
    assert result["status"] == "failed"


def test_unique_attribution_ids_are_healthy(monkeypatch, tmp_path):
    monkeypatch.setattr(growth_health, "LEARNING", tmp_path)
    (tmp_path / "attributed_orders.json").write_text(
        '{"1001": {"attribution_version": 3}, "1002": {"attribution_version": 3}}',
        encoding="utf-8",
    )
    result = growth_health.attribution_health()
    assert result["status"] == "ok"
    assert result["orders"] == 2


def test_config_health_flags_extended_content(monkeypatch, tmp_path):
    monkeypatch.setattr(growth_health, "WORKFLOW", tmp_path / "daily.yml")
    monkeypatch.setattr(growth_health, "POLICY", tmp_path / "founder_policies.yaml")
    monkeypatch.setattr(
        growth_health,
        "ROOT",
        tmp_path,
    )
    (tmp_path / "daily.yml").write_text(
        'ENABLE_EXTENDED_CONTENT: "true"', encoding="utf-8"
    )
    (tmp_path / "founder_policies.yaml").write_text("minimum_score: 6.5", encoding="utf-8")
    (tmp_path / "content_generator/core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "content_generator/core/brand_guard.py").write_text("EDITORIAL_THRESHOLD = 8.0", encoding="utf-8")
    result = growth_health.config_health()
    # The implementation emits "workflow_hardcodes_extended_content" for a
    # workflow literal and "extended_content_enabled_via_policy" for the policy
    # route. This asserted a third name that nothing ever emits, so it failed
    # on every run — and nothing noticed, because the suite was not wired into
    # the gate and executes no test function when run as a script.
    assert "workflow_hardcodes_extended_content" in result["warnings"]
    assert "legacy_editorial_threshold_symbol_present" in result["warnings"]
