"""Regression checks for repository security automation and disclosure policy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codeql_runs_on_main_prs_and_weekly_with_least_privilege():
    workflow = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "schedule:" in workflow
    assert "languages: python" in workflow
    assert "build-mode: none" in workflow
    assert "security-events: write" in workflow
    assert "contents: read" in workflow
    assert "permissions: write-all" not in workflow
    assert "github/codeql-action/init@v4" in workflow
    assert "github/codeql-action/analyze@v4" in workflow


def test_dependabot_updates_python_and_github_actions_weekly():
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in config
    assert "package-ecosystem: github-actions" in config
    assert config.count("interval: weekly") == 2
    assert "timezone: Asia/Kolkata" in config


def test_manual_oneoff_publish_respects_global_kill_switch():
    workflow = (ROOT / ".github" / "workflows" / "oneoff-ig-post.yml").read_text(encoding="utf-8")
    assert "Enforce global publishing kill switch" in workflow
    assert "PUBLISHING_ENABLED: ${{ vars.PUBLISHING_ENABLED }}" in workflow
    assert "Do not enable it until production acceptance is complete" in workflow


def test_security_policy_requires_private_disclosure_and_credential_rotation():
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "private vulnerability reporting" in policy.lower()
    assert "Rotate any credential" in policy
    assert "least-privilege permissions" in policy
    assert "controlled publication/read-back" in policy
