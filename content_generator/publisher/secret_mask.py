"""Mask and redact publishing tokens before they reach logs or URLs."""
from __future__ import annotations

import urllib.parse


def mask_secret(value: str) -> None:
    """Register a secret with the Actions log masker. The value is not printed alone."""
    raw = str(value or "").strip()
    if not raw or any(ch in raw for ch in "\r\n"):
        return
    print(f"::add-mask::{raw}", flush=True)


def redact(text: str, secrets: list[str] | tuple[str, ...] | None = None) -> str:
    out = str(text or "")
    for secret in secrets or ():
        raw = str(secret or "").strip()
        if not raw:
            continue
        out = out.replace(raw, "***")
        quoted = urllib.parse.quote(raw, safe="")
        if quoted and quoted != raw:
            out = out.replace(quoted, "***")
    return out
