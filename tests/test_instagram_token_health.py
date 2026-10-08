"""Instagram token health must prove the token can publish, and never print it."""
from __future__ import annotations

import json
from pathlib import Path

from content_generator.ops import meta_token_health as health

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "instagram-token-health.yml"
TOKEN = "IGAAsecrettokenvalue"
ACCOUNT = "17890000000000001"
NOW = 1_800_000_000  # 2027-01-15-ish; fixtures use expires around this


def _debug(scopes, *, expires_at=0, is_valid=True, token_type="PAGE"):
    return {
        "data": {
            "type": token_type,
            "is_valid": is_valid,
            "expires_at": expires_at,
            "scopes": list(scopes),
        }
    }


def _install(monkeypatch, routes, mode="strict", facebook=""):
    monkeypatch.setenv("META_TOKEN_MODE", mode)
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    if facebook:
        monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", facebook)
    else:
        monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    seen = []

    def fetch(url, headers, timeout=15):
        seen.append({"url": url, "headers": dict(headers), "timeout": timeout})
        for needle, payload in routes:
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(health, "_fetch", fetch)
    return seen


def _run(capsys, now=NOW):
    code = health.run_checks(now=now)
    return code, capsys.readouterr().out


def test_workflow_runs_the_shared_check_and_does_not_print_the_token():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python -m content_generator.ops.meta_token_health" in text
    assert "META_TOKEN_MODE: strict" in text
    assert "FACEBOOK_PAGE_ACCESS_TOKEN:" in text
    assert "INSTAGRAM_ACCESS_TOKEN:" in text
    assert "print(" not in text
    assert "echo " not in text
    assert "permissions:" in text
    assert "contents: read" in text


def test_missing_instagram_credentials_fail_closed(monkeypatch, capsys):
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("META_TOKEN_MODE", "strict")

    def fetch(*_args, **_kwargs):
        raise AssertionError("Graph was called without credentials")

    monkeypatch.setattr(health, "_fetch", fetch)
    code, out = _run(capsys)
    assert code == 1
    assert "INSTAGRAM_ACCESS_TOKEN" in out
    assert "::error::" in out


def test_soft_mode_missing_credentials_do_not_fail(monkeypatch, capsys):
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("META_TOKEN_MODE", "soft")

    def fetch(*_args, **_kwargs):
        raise AssertionError("Graph was called without credentials")

    monkeypatch.setattr(health, "_fetch", fetch)
    code, out = _run(capsys)
    assert code == 0
    assert "::warning::" in out


def test_healthy_token_logs_type_expiry_scopes_and_username(monkeypatch, capsys):
    seen = _install(monkeypatch, [
        ("debug_token", _debug(health.IG_SCOPES, expires_at=0, token_type="PAGE")),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, out = _run(capsys)
    assert code == 0
    assert "type=PAGE" in out
    assert "expires=never" in out
    assert "scopes=instagram_basic,instagram_content_publish" in out
    assert "username=puritybeans" in out
    assert TOKEN not in out
    debug = seen[0]
    assert "input_token=" in debug["url"] and "access_token=" in debug["url"]
    assert TOKEN in debug["url"]
    assert "Authorization" not in debug["headers"]
    account = seen[1]
    assert account["url"].endswith(f"/{ACCOUNT}?fields=id,username")
    assert TOKEN not in account["url"]
    assert account["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert "https://graph.facebook.com/v24.0/" in debug["url"]


def test_missing_publish_scope_fails(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", _debug(["instagram_basic"])),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, out = _run(capsys)
    assert code == 1
    assert "instagram_content_publish" in out
    assert TOKEN not in out


def test_missing_basic_scope_fails(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", _debug(["instagram_content_publish"])),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, out = _run(capsys)
    assert code == 1
    assert "instagram_basic" in out


def test_expired_token_fails(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", _debug(health.IG_SCOPES, expires_at=NOW - 10)),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, out = _run(capsys)
    assert code == 1
    assert "token expired" in out
    assert TOKEN not in out


def test_invalid_token_fails_even_with_scopes(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", _debug(health.IG_SCOPES, expires_at=0, is_valid=False)),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, out = _run(capsys)
    assert code == 1
    assert "token expired" in out


def test_graph_error_redacts_the_token(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", health.TokenHttpError(401, f"bad {TOKEN}")),
    ])
    code, out = _run(capsys)
    assert code == 1
    assert TOKEN not in out
    assert "***" in out


def test_facebook_scope_gap_warns_and_instagram_still_passes(monkeypatch, capsys):
    page = "EAAB-facebook-page-token"
    seen = _install(
        monkeypatch,
        [
            ("debug_token", None),  # replaced below per token
        ],
        facebook=page,
    )

    def fetch(url, headers, timeout=15):
        seen.append({"url": url, "headers": dict(headers)})
        if "debug_token" in url:
            if page in url:
                return _debug(["pages_show_list"], token_type="PAGE")
            return _debug(health.IG_SCOPES, token_type="USER")
        return {"id": ACCOUNT, "username": "puritybeans"}

    monkeypatch.setattr(health, "_fetch", fetch)
    code, out = _run(capsys)
    assert code == 0
    assert "type=USER" in out
    assert "username=puritybeans" in out
    assert "::warning::" in out
    assert "pages_manage_posts" in out
    assert "Facebook token type=PAGE" in out
    assert TOKEN not in out
    assert page not in out


def test_expired_facebook_token_is_only_a_warning(monkeypatch, capsys):
    page = "EAAB-facebook-page-token"

    def fetch(url, headers, timeout=15):
        if "debug_token" in url and page in url:
            return _debug(["pages_manage_posts"], expires_at=NOW - 50, token_type="PAGE")
        if "debug_token" in url:
            return _debug(health.IG_SCOPES)
        return {"id": ACCOUNT, "username": "puritybeans"}

    _install(monkeypatch, [], facebook=page)
    monkeypatch.setattr(health, "_fetch", fetch)
    code, out = _run(capsys)
    assert code == 0
    assert "Facebook token" in out
    assert "token expired" in out
    assert page not in out


def test_unset_facebook_token_is_not_checked(monkeypatch, capsys):
    seen = _install(monkeypatch, [
        ("debug_token", _debug(health.IG_SCOPES)),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ])
    code, _out = _run(capsys)
    assert code == 0
    assert len(seen) == 2


def test_soft_mode_reports_missing_scopes_without_failing(monkeypatch, capsys):
    _install(monkeypatch, [
        ("debug_token", _debug(["instagram_basic"])),
        (f"/{ACCOUNT}?", {"id": ACCOUNT, "username": "puritybeans"}),
    ], mode="soft")
    code, out = _run(capsys)
    assert code == 0
    assert "::warning::" in out
    assert "instagram_content_publish" in out
    assert TOKEN not in out


def test_alert_body_does_not_contain_the_token(monkeypatch, capsys):
    posted = {}

    def urlopen(req, timeout=10):
        posted["body"] = req.data.decode()
        class _Resp:
            def read(self):
                return b"ok"
        return _Resp()

    _install(monkeypatch, [
        ("debug_token", health.TokenHttpError(400, json.dumps({"error": TOKEN}))),
    ])
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    monkeypatch.setattr(health.urllib.request, "urlopen", urlopen)
    code, out = _run(capsys)
    assert code == 1
    assert TOKEN not in out
    assert TOKEN not in posted["body"]
    assert "***" in posted["body"]
