"""Prove a Meta token can publish, without ever printing the token.

Instagram token health and the daily Meta preflight both call this.

  GET /debug_token?input_token=<token>&access_token=<token>
  GET /{account_id}?fields=id,username

The token is its own access_token for debug_token. The account lookup sends
it as an Authorization header so that URL stays free of the secret. Logs
carry the token type, expiry, scopes, and username. The token value is
redacted from every line, including error bodies.

Strict mode (token health, publish preflight) fails when instagram_basic or
instagram_content_publish is missing, or when the token is expired. Soft mode
(generate) reports the same facts as warnings and continues.

FACEBOOK_PAGE_ACCESS_TOKEN, when set, gets the same debug call. It needs
pages_manage_posts. A miss or an expired page token is a warning, never a
failed job.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from config.api_versions import META_GRAPH_BASE

IG_SCOPES = ("instagram_basic", "instagram_content_publish")
FB_SCOPES = ("pages_manage_posts",)
_TIMEOUT_S = 15


class TokenHttpError(Exception):
    def __init__(self, code: int, body: str):
        self.code = code
        self.body = body
        super().__init__(f"HTTP {code}")


def _mode() -> str:
    return os.environ.get("META_TOKEN_MODE", "strict").strip().lower() or "strict"


def _redact(text: str, secrets: list[str]) -> str:
    out = str(text or "")
    for secret in secrets:
        raw = str(secret or "")
        if not raw:
            continue
        out = out.replace(raw, "***")
        quoted = urllib.parse.quote(raw, safe="")
        if quoted and quoted != raw:
            out = out.replace(quoted, "***")
    return out


def _emit(level: str, message: str, secrets: list[str]) -> None:
    print(f"::{level}::{_redact(message, secrets)}")


def _alert(message: str, secrets: list[str]) -> None:
    safe = _redact(message, secrets)
    webhook = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not webhook:
        return
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps({"text": safe}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:
        print(f"::warning::alert webhook failed: {type(exc).__name__}")


def _fetch(url: str, headers: dict, timeout: int = _TIMEOUT_S) -> dict:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise TokenHttpError(exc.code, body) from None
    except urllib.error.URLError:
        raise TokenHttpError(0, "network error") from None


def debug_token_url(token: str) -> str:
    query = urllib.parse.urlencode({"input_token": token, "access_token": token})
    return f"{META_GRAPH_BASE}/debug_token?{query}"


def account_url(account_id: str) -> str:
    account = urllib.parse.quote(account_id, safe="")
    return f"{META_GRAPH_BASE}/{account}?fields=id,username"


def _headers(token: str | None = None) -> dict:
    headers = {"User-Agent": "PurityBeans/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def granted_scopes(info: dict) -> set[str]:
    scopes = {str(item) for item in (info.get("scopes") or []) if str(item).strip()}
    for item in info.get("granular_scopes") or []:
        if isinstance(item, dict) and item.get("scope"):
            scopes.add(str(item["scope"]))
        elif isinstance(item, str) and item.strip():
            scopes.add(item.strip())
    return scopes


def expiry_label(info: dict) -> str:
    try:
        expires = int(info.get("expires_at"))
    except (TypeError, ValueError):
        return "unknown"
    if expires == 0:
        return "never"
    return datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def token_expired(info: dict, now: int | None = None) -> bool:
    if info.get("is_valid") is False:
        return True
    try:
        expires = int(info.get("expires_at"))
    except (TypeError, ValueError):
        return False
    if expires == 0:
        return False
    return expires <= int(now if now is not None else time.time())


def _token_info(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def inspect_token(token: str, *, now: int | None = None) -> dict:
    """Debug one token. Raises TokenHttpError when Graph rejects the call."""
    payload = _fetch(debug_token_url(token), _headers())
    info = _token_info(payload)
    scopes = granted_scopes(info)
    return {
        "type": str(info.get("type") or "unknown").upper(),
        "expires": expiry_label(info),
        "scopes": sorted(scopes),
        "expired": token_expired(info, now=now) if info else True,
        "info": info,
    }


def inspect_instagram(account_id: str, token: str, *, now: int | None = None) -> dict:
    """Return ok plus the fields the workflow is allowed to log."""
    problems: list[str] = []
    report = inspect_token(token, now=now)
    missing = [scope for scope in IG_SCOPES if scope not in set(report["scopes"])]
    if missing:
        problems.append("missing " + ", ".join(missing))
    if report["expired"]:
        problems.append(f"token expired (expires={report['expires']})")
    username = ""
    resolved_account_id = ""
    try:
        account = _fetch(account_url(account_id), _headers(token))
    except TokenHttpError as exc:
        problems.append(f"account lookup HTTP {exc.code}")
    else:
        username = str(account.get("username") or "")
        got_id = str(account.get("id") or "")
        if got_id != str(account_id):
            problems.append(f"unexpected account id {got_id or '(none)'}")
        # A Page access token can successfully read a Facebook Page ID with
        # fields=id,username (username is absent), which is NOT an Instagram
        # publishing account. Resolve its linked Instagram professional ID
        # before allowing a publish job to proceed.
        if not username:
            query = urllib.parse.urlencode({"fields": "instagram_business_account{id,username}"})
            page_url = f"{META_GRAPH_BASE}/{urllib.parse.quote(account_id, safe='')}?{query}"
            try:
                page = _fetch(page_url, _headers(token))
                linked = page.get("instagram_business_account") or {}
                resolved_account_id = str(linked.get("id") or "").strip()
                username = str(linked.get("username") or "").strip()
                if not resolved_account_id or not username:
                    resolved_account_id = ""
                    problems.append(
                        "configured ID is not an Instagram user and no linked Instagram professional account was returned; "
                        "set INSTAGRAM_ACCOUNT_ID to the Instagram professional account ID, not the Facebook Page ID"
                    )
            except TokenHttpError as exc:
                problems.append(
                    f"configured ID has no username and linked Instagram account lookup failed (HTTP {exc.code}); "
                    "check INSTAGRAM_ACCOUNT_ID and Page permissions"
                )
    report["username"] = username
    report["resolved_account_id"] = resolved_account_id
    report["problems"] = problems
    report["ok"] = not problems
    return report


def format_instagram(report: dict) -> str:
    scopes = ",".join(report.get("scopes") or []) or "(none)"
    return (
        f"Instagram token type={report.get('type') or 'unknown'} "
        f"expires={report.get('expires') or 'unknown'} "
        f"scopes={scopes} username={report.get('username') or '(none)'}"
    )


def format_facebook(report: dict) -> str:
    scopes = ",".join(report.get("scopes") or []) or "(none)"
    return (
        f"Facebook token type={report.get('type') or 'unknown'} "
        f"expires={report.get('expires') or 'unknown'} "
        f"scopes={scopes}"
    )


def _finish(messages: list[tuple[str, str]], secrets: list[str], failed: bool) -> int:
    for level, message in messages:
        _emit(level, message, secrets)
    if failed and _mode() != "soft":
        summary = " ".join(message for level, message in messages if level == "error")
        _alert(summary or "Meta token check failed", secrets)
        return 1
    return 0


def run_checks(now: int | None = None) -> int:
    """Print diagnostics and return the process exit code."""
    mode = _mode()
    account_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    facebook = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    secrets = [token, facebook, account_id]
    messages: list[tuple[str, str]] = []
    failed = False

    if not account_id or not token:
        level = "error" if mode != "soft" else "warning"
        messages.append((
            level,
            "Instagram token health FAILED — INSTAGRAM_ACCOUNT_ID or "
            "INSTAGRAM_ACCESS_TOKEN is not configured."
            if mode != "soft"
            else "Instagram credentials unavailable; generate continues; publish slots fail closed.",
        ))
        failed = True
    else:
        try:
            report = inspect_instagram(account_id, token, now=now)
        except TokenHttpError as exc:
            failed = True
            detail = _redact(exc.body, secrets)[:300]
            messages.append((
                "error" if mode != "soft" else "warning",
                f"Instagram token check failed (HTTP {exc.code}): {detail}",
            ))
        else:
            resolved_id = str(report.get("resolved_account_id") or "").strip()
            publish_account_id = resolved_id or account_id
            if resolved_id and resolved_id != account_id:
                # GITHUB_ENV helps non-overridden steps; GITHUB_OUTPUT is used
                # explicitly by publish workflows to beat a secret-valued step env.
                os.environ["INSTAGRAM_ACCOUNT_ID"] = resolved_id
                env_file = os.environ.get("GITHUB_ENV", "").strip()
                if env_file:
                    with open(env_file, "a", encoding="utf-8") as handle:
                        handle.write(f"INSTAGRAM_ACCOUNT_ID={resolved_id}\\n")
                secrets.append(resolved_id)
                messages.append(("notice", f"Resolved linked Instagram professional account username={report.get('username')}; using its account ID for this job."))
            output_file = os.environ.get("GITHUB_OUTPUT", "").strip()
            if report.get("ok") and publish_account_id and output_file:
                with open(output_file, "a", encoding="utf-8") as handle:
                    handle.write(f"instagram_account_id={publish_account_id}\\n")
            messages.append(("notice", format_instagram(report)))
            if not report["ok"]:
                failed = True
                messages.append((
                    "error" if mode != "soft" else "warning",
                    "Instagram token cannot publish: " + "; ".join(report["problems"]),
                ))

    if facebook:
        try:
            page = inspect_token(facebook, now=now)
        except TokenHttpError as exc:
            detail = _redact(exc.body, secrets)[:300]
            messages.append((
                "warning",
                f"Facebook page token check failed (HTTP {exc.code}): {detail}",
            ))
        else:
            messages.append(("notice", format_facebook(page)))
            missing = [scope for scope in FB_SCOPES if scope not in set(page["scopes"])]
            notes = []
            if missing:
                notes.append("missing " + ", ".join(missing))
            if page["expired"]:
                notes.append(f"token expired (expires={page['expires']})")
            if notes:
                messages.append((
                    "warning",
                    "Facebook page token: " + "; ".join(notes),
                ))

    threads_tok = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    threads_uid = os.environ.get("THREADS_USER_ID", "me").strip() or "me"
    if threads_tok:
        secrets.append(threads_tok)
        try:
            th_url = f"https://graph.threads.net/v1.0/{urllib.parse.quote(threads_uid, safe='')}?fields=id,username"
            th_res = _fetch(th_url, _headers(threads_tok))
            th_user = str(th_res.get("username") or "")
            th_id = str(th_res.get("id") or "")
            messages.append(("notice", f"Threads token valid: username={th_user} id={th_id}"))
        except TokenHttpError as exc:
            detail = _redact(exc.body, secrets)[:300]
            messages.append(("warning", f"Threads token check (HTTP {exc.code}): {detail}"))
        except Exception as exc:
            messages.append(("warning", f"Threads token check: {type(exc).__name__}"))

    return _finish(messages, secrets, failed)


def main() -> int:
    try:
        return run_checks()
    except Exception as exc:
        secrets = [
            os.environ.get("INSTAGRAM_ACCESS_TOKEN", ""),
            os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
        ]
        message = _redact(f"{type(exc).__name__}: {exc}", secrets)
        if _mode() == "soft":
            print(f"::warning::Meta token check failed ({message}); generate continues.")
            return 0
        print(f"::error::Meta token check failed: {message}")
        _alert(message, secrets)
        return 1


if __name__ == "__main__":
    sys.exit(main())
