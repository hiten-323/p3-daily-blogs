"""Regression coverage for fail-closed Instagram token health and policy ownership."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TOKEN_WORKFLOW = ROOT / ".github" / "workflows" / "instagram-token-health.yml"
DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
FOUNDER_POLICY = ROOT / "founder_policies.yaml"


def test_missing_instagram_credentials_fail_closed(monkeypatch, capsys) -> None:
    from content_generator.ops import meta_token_health as health

    text = TOKEN_WORKFLOW.read_text(encoding="utf-8")
    assert "python -m content_generator.ops.meta_token_health" in text
    assert "META_TOKEN_MODE: strict" in text
    assert "access_token" not in text
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("META_TOKEN_MODE", "strict")

    def fetch(*_args, **_kwargs):
        raise AssertionError("Graph was called without credentials")

    monkeypatch.setattr(health, "_fetch", fetch)
    assert health.run_checks() == 1
    assert "INSTAGRAM_ACCESS_TOKEN is not configured" in capsys.readouterr().out


def test_token_health_uses_graph_v24() -> None:
    from config.api_versions import META_GRAPH_BASE
    from content_generator.ops.meta_token_health import account_url, debug_token_url

    assert META_GRAPH_BASE == "https://graph.facebook.com/v24.0"
    assert debug_token_url("tok").startswith(f"{META_GRAPH_BASE}/debug_token?")
    assert account_url("1789").startswith(f"{META_GRAPH_BASE}/1789?fields=id,username")


def test_extended_content_is_owned_by_founder_policy() -> None:
    policy = FOUNDER_POLICY.read_text(encoding="utf-8")
    workflow = DAILY_WORKFLOW.read_text(encoding="utf-8")

    # The policy is the source of truth. The workflow may document the setting,
    # but it must never inject ENABLE_EXTENDED_CONTENT as an environment override.
    assert re.search(r"(?m)^\s*enable_extended_content:\s*(true|false)\s*(?:#.*)?$", policy)
    assert not re.search(r"(?m)^\s*ENABLE_EXTENDED_CONTENT\s*:", workflow)


def test_workflow_documents_policy_owned_extended_content() -> None:
    text = DAILY_WORKFLOW.read_text(encoding="utf-8")
    assert "founder_policies.yaml" in text
    assert "enable_extended_content" in text
