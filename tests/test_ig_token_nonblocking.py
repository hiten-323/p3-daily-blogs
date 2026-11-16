"""An Instagram token problem must never block Facebook/Threads/LinkedIn/YouTube,
and a missing instagram_manage_insights must never block anything (16 Nov regression)."""
import pytest

from content_generator.ops import meta_token_health as health
from content_generator.core import instagram_pause

FB_OK = {"type": "PAGE", "expires": "never", "scopes": list(health.FB_SCOPES), "expired": False, "valid": True}


def _env(monkeypatch, tmp_path, *, preflight=True):
    monkeypatch.setenv("META_TOKEN_MODE", "strict")
    if preflight:
        monkeypatch.setenv("META_PUBLISH_PREFLIGHT", "true")
    else:
        monkeypatch.delenv("META_PUBLISH_PREFLIGHT", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_REQUIRED", raising=False)
    monkeypatch.delenv("INSTAGRAM_CREDENTIAL_BLOCK", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    for k, v in {"INSTAGRAM_ACCOUNT_ID": "ig-123", "INSTAGRAM_ACCESS_TOKEN": "ig-token",
                 "FACEBOOK_PAGE_ID": "fb-123", "FACEBOOK_PAGE_ACCESS_TOKEN": "fb-token",
                 "THREADS_ACCESS_TOKEN": "th-token", "THREADS_USER_ID": "threads-123"}.items():
        monkeypatch.setenv(k, v)
    for k in ("LI_REFRESH_TOKEN", "LI_CLIENT_ID", "LI_CLIENT_SECRET", "LI_API_ACCESS"):
        monkeypatch.delenv(k, raising=False)
    env_file = tmp_path / "github_env"
    env_file.write_text("")
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output"))
    monkeypatch.setattr(health, "inspect_token", lambda token, **k: dict(FB_OK))
    monkeypatch.setattr(health, "_fetch", lambda *a, **k: {"id": "threads-123", "username": "pb"})
    blocks = []
    monkeypatch.setattr("content_generator.publisher.publishing_ledger.record_credential_block",
                        lambda platform, reason, slot="generate": blocks.append((platform, reason)) or {})
    return env_file, blocks


def _ig(monkeypatch, *, problems=(), degraded=()):
    monkeypatch.setattr(health, "inspect_instagram", lambda *a, **k: {
        "ok": not problems, "problems": list(problems), "degraded": list(degraded),
        "scopes": list(health.IG_PUBLISH_SCOPES), "type": "PAGE", "expires": "never",
        "username": "purepantryprovisions", "resolved_account_id": "",
    })


@pytest.mark.parametrize("preflight", [True, False])
def test_missing_insights_only_degrades(monkeypatch, tmp_path, capsys, preflight):
    env_file, blocks = _env(monkeypatch, tmp_path, preflight=preflight)
    _ig(monkeypatch, degraded=["instagram_manage_insights"])
    assert health.run_checks(now=100) == 0
    out = capsys.readouterr().out
    assert "::warning::Instagram metrics DEGRADED: token lacks instagram_manage_insights" in out
    assert "publishing is unaffected" in out
    assert "::error::" not in out
    assert "INSTAGRAM_CREDENTIAL_BLOCK" not in env_file.read_text()
    assert blocks == []


def test_ig_publish_problem_in_preflight_skips_ig_only(monkeypatch, tmp_path, capsys):
    env_file, blocks = _env(monkeypatch, tmp_path)
    _ig(monkeypatch, problems=["token expired (expires=2026-11-01T00:00:00Z)"])
    assert health.run_checks(now=100) == 0          # Facebook/Threads/LinkedIn/YouTube continue
    out = capsys.readouterr().out
    assert "Instagram is skipped in this job; other platforms continue" in out
    assert "INSTAGRAM_CREDENTIAL_BLOCK=Instagram token cannot publish" in env_file.read_text()
    assert blocks and blocks[0][0] == "instagram"
    assert "ig-token" not in out and "ig-token" not in env_file.read_text()


def test_missing_ig_credentials_in_preflight_do_not_block_others(monkeypatch, tmp_path):
    env_file, blocks = _env(monkeypatch, tmp_path)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN")
    assert health.run_checks(now=100) == 0
    assert "INSTAGRAM_CREDENTIAL_BLOCK=" in env_file.read_text()


def test_ig_http_error_in_preflight_does_not_block_others(monkeypatch, tmp_path):
    env_file, _ = _env(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise health.TokenHttpError(400, "bad token ig-token")
    monkeypatch.setattr(health, "inspect_instagram", boom)
    assert health.run_checks(now=100) == 0
    assert "ig-token" not in env_file.read_text()


def test_token_health_still_fails_on_a_real_ig_publish_problem(monkeypatch, tmp_path, capsys):
    _env(monkeypatch, tmp_path, preflight=False)
    _ig(monkeypatch, problems=["missing instagram_content_publish"])
    assert health.run_checks(now=100) == 1
    assert "::error::Instagram token cannot publish: missing instagram_content_publish" in capsys.readouterr().out


def test_instagram_only_job_can_keep_ig_fatal(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("META_INSTAGRAM_REQUIRED", "true")
    _ig(monkeypatch, problems=["token expired"])
    assert health.run_checks(now=100) == 1


def test_facebook_failure_rules_unchanged(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    _ig(monkeypatch)
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    assert health.run_checks(now=100) == 1


def test_credential_block_skips_instagram_like_the_pause(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "false")
    monkeypatch.delenv("INSTAGRAM_CREDENTIAL_BLOCK", raising=False)
    assert instagram_pause.instagram_paused() is False
    monkeypatch.setenv("INSTAGRAM_CREDENTIAL_BLOCK", "Instagram token cannot publish: token expired")
    assert instagram_pause.instagram_paused() is True
    res = instagram_pause.paused_result()
    assert res["error"] == "instagram_credential_block" and res["attempted"] is False
    from content_generator.publisher import instagram
    assert instagram.post_content({}, day=1)["error"] == "instagram_credential_block"
    from content_generator.scheduler import retry_unposted
    targets = retry_unposted.active_targets()
    assert not set(targets) & set(retry_unposted.INSTAGRAM_TARGETS)
    assert targets  # Facebook/Threads/LinkedIn/YouTube still due
