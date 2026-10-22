"""Resolve the Kaggle account that owns the background kernel.

A bare API token is asked who it belongs to, first through ``kaggle config view``
and then through IntrospectToken. ``KAGGLE_USERNAME`` is the fallback. Blank
``KAGGLE_*`` values are removed so an empty key is not treated as legacy auth.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import urllib.request

logger = logging.getLogger(__name__)

_INTROSPECT_URL = "https://api.kaggle.com/v1/security.OAuthService/IntrospectToken"


def configure_logging() -> None:
    """Show INFO logs in the weekly job. Leave a handler pytest already installed."""
    logging.getLogger("content_generator").setLevel(logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    elif root.level > logging.INFO:
        root.setLevel(logging.INFO)


def valid_owner(value: str) -> str:
    slug = (value or "").strip()
    if not slug or slug.lower() in {"none", "null", "missing"}:
        return ""
    if slug.upper().startswith("KGAT"):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", slug):
        return ""
    return slug


def kaggle_env(owner: str = "") -> dict:
    """Env for the Kaggle CLI. Drop blank KAGGLE_* values so an empty key is not legacy auth."""
    from content_generator.creative.kaggle_bank import api_token
    token = api_token()
    env = os.environ.copy()
    if token:
        env["KAGGLE_API_TOKEN"] = token
    for name, value in list(env.items()):
        if name.startswith("KAGGLE_") and not str(value or "").strip():
            env.pop(name, None)
    if env.get("KAGGLE_USERNAME") and not valid_owner(env["KAGGLE_USERNAME"]):
        logger.info("[kaggle_bank] ignoring KAGGLE_USERNAME that is not a slug")
        env.pop("KAGGLE_USERNAME", None)
    slug = valid_owner(owner)
    if slug:
        env["KAGGLE_USERNAME"] = slug
    return env


def username_in_text(text: str) -> str:
    for line in (text or "").splitlines():
        match = re.search(r"username\s*:\s*(\S+)", line, re.IGNORECASE)
        if not match:
            continue
        owner = valid_owner(match.group(1))
        if owner:
            return owner
    return ""


def _owner_from_mapping(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("username", "userName", "user_name"):
        owner = valid_owner(str(payload.get(key) or ""))
        if owner:
            return owner
    for value in payload.values():
        if isinstance(value, dict):
            found = _owner_from_mapping(value)
            if found:
                return found
    return ""


def _owner_from_introspect(token: str) -> str:
    from content_generator.creative.kaggle_bank import _mask_token
    _mask_token(token)
    request = urllib.request.Request(
        _INTROSPECT_URL, data=json.dumps({"token": token}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "PurityBeansBackground/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            payload = json.loads(response.read(4096).decode() or "{}")
    except Exception as exc:
        logger.info("[kaggle_bank] username lookup failed: %s", type(exc).__name__)
        return ""
    if not isinstance(payload, dict):
        logger.info("[kaggle_bank] token introspection returned no username")
        return ""
    if payload.get("active") is False:
        logger.info("[kaggle_bank] token introspection inactive")
        return ""
    owner = _owner_from_mapping(payload)
    if owner:
        return owner
    logger.info("[kaggle_bank] token introspection returned no username (keys=%s)", ",".join(sorted(payload)))
    return ""


def _owner_from_config_view(secrets: list[str]) -> str:
    from content_generator.creative.kaggle_bank import _run
    if not shutil.which("kaggle"):
        logger.info("[kaggle_bank] kaggle CLI missing; skipping config view")
        return ""
    proc = _run(["kaggle", "config", "view"], secrets)
    return username_in_text((proc.stdout or "") + "\n" + (proc.stderr or ""))


def owner_from_token(token: str) -> str:
    from content_generator.creative.kaggle_bank import _auth_secrets
    explicit = valid_owner(os.getenv("KAGGLE_USERNAME", ""))
    if os.getenv("KAGGLE_USERNAME", "").strip() and not explicit:
        logger.info("[kaggle_bank] KAGGLE_USERNAME is set but is not a slug")
    if not token:
        if explicit:
            return explicit
        logger.info("[kaggle_bank] kaggle username unresolved")
        return ""
    resolved = _owner_from_config_view(_auth_secrets()) or _owner_from_introspect(token)
    if resolved and explicit and resolved != explicit:
        logger.info("[kaggle_bank] token owner differs from KAGGLE_USERNAME; using the token account")
        return resolved
    if resolved:
        return resolved
    if explicit:
        logger.info("[kaggle_bank] using KAGGLE_USERNAME because the token did not name an account")
        return explicit
    logger.info("[kaggle_bank] kaggle username unresolved (token did not name an account and KAGGLE_USERNAME is unset)")
    return ""
