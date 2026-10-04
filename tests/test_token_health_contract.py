"""Regression coverage for fail-closed Instagram token health and policy ownership."""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TOKEN_WORKFLOW = ROOT / ".github" / "workflows" / "instagram-token-health.yml"
DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
FOUNDER_POLICY = ROOT / "founder_policies.yaml"


def test_missing_instagram_credentials_fail_closed() -> None:
    text = TOKEN_WORKFLOW.read_text(encoding="utf-8")
    marker = "if not account_id or not token:"
    assert marker in text
    block = text.split(marker, 1)[1].split("url =", 1)[0]
    assert "sys.exit(1)" in block
    assert "sys.exit(0)" not in block
    assert "access_token" not in text
    assert "Authorization" in text


def test_token_health_uses_graph_v24() -> None:
    text = TOKEN_WORKFLOW.read_text(encoding="utf-8")
    assert "https://graph.facebook.com/v24.0/" in text


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
