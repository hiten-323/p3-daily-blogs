"""Regression tests for the Instagram token-health contract."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "instagram-token-health.yml"


def test_missing_instagram_credentials_fail_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = 'if not account_id or not token:'
    assert marker in text
    block = text.split(marker, 1)[1].split('url =', 1)[0]
    assert 'sys.exit(1)' in block
    assert 'sys.exit(0)' not in block
    assert 'access_token' not in text
    assert 'Authorization' in text


def test_health_uses_meta_graph_v24() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'https://graph.facebook.com/v24.0/' in text


def test_health_has_explicit_workflow_permissions() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'permissions:' in text
    assert 'contents: read' in text
