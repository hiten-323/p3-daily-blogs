#!/usr/bin/env python3
"""Probe background sources and save one plate each from Pexels, Pixabay, and Hugging Face.

Does not publish. Does not print secret values. Logs are redacted before they
are written.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys

SECRET_NAMES = (
    "PEXELS_API_KEY", "PIXABAY_API_KEY", "HF_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY",
    "PIXAZO_API_KEY", "RUNWAY_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
)
PLATE_DIR = os.path.join("output", "probe_plates")


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [os.getenv(name, "") for name in SECRET_NAMES]
        message = record.getMessage()
        for secret in secrets:
            if secret and secret in message:
                message = message.replace(secret, "***")
        record.msg = message
        record.args = ()
        return True


def _install_redaction() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    redact = _Redact()
    logging.getLogger().addFilter(redact)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redact)


def _http_code(detail: str) -> int | None:
    for token in (detail or "").replace(":", " ").split():
        if token.isdigit():
            return int(token)
    return None


def classify(row: dict) -> str:
    """Map a probe row to live / auth failed / quota / error / empty."""
    status = row.get("status") or ""
    code = _http_code(row.get("detail") or "")
    if row.get("name") == "coded":
        return "live"
    if row.get("name") == "kaggle_bank" and status == "empty":
        return "empty"
    if status == "skipped":
        return "error"
    if code in (401, 403):
        return "auth failed"
    if code in (402, 429):
        return "quota"
    if status == "live":
        return "live"
    if status == "down":
        return "error"
    return "error"


def _choice() -> dict:
    return {
        "date": "2026-10-21",
        "format": "short",
        "concept": "steam_backlight",
        "scene": "steam",
        "ai_prompt": "thick white steam curling upward against a warm backlight, photoreal, no people",
    }


def _save(name: str, path: str | None) -> None:
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 1000:
        print(f"plate {name}: none")
        return
    os.makedirs(PLATE_DIR, exist_ok=True)
    dest = os.path.join(PLATE_DIR, f"{name}.mp4")
    shutil.copyfile(path, dest)
    print(f"plate {name}: saved bytes={os.path.getsize(dest)}")


def _try_plate(name: str, fn) -> None:
    try:
        result = fn(_choice(), name, 5)
    except Exception as exc:
        print(f"plate {name}: failed {type(exc).__name__}")
        return
    path = result if isinstance(result, str) else (result or {}).get("path")
    _save(name, path)


def main() -> int:
    _install_redaction()
    from content_generator.creative import background_probe, hf_video, stock_video

    rows = background_probe.probe_results()
    by_name = {row["name"]: row for row in rows}
    for row in rows:
        kind = classify(row)
        code = _http_code(row.get("detail") or "")
        code_bit = f" http={code}" if code is not None else ""
        print(f"source {row['name']}: {kind}{code_bit} raw={row.get('status')}")

    if classify(by_name.get("pexels", {})) == "live":
        _try_plate("pexels", stock_video.pexels)
    else:
        print("plate pexels: skipped")
    if classify(by_name.get("pixabay", {})) == "live":
        _try_plate("pixabay", stock_video.pixabay)
    else:
        print("plate pixabay: skipped")
    if classify(by_name.get("hf_ltx", {})) == "live" or classify(by_name.get("hf_wan", {})) == "live":
        os.environ.setdefault("HF_BG_TIMEOUT_S", "75")
        hf_video.reset_session()
        before = hf_video.ltx(_choice(), "probe", 5)
        if before:
            _save("hf_ltx", before)
        else:
            print("plate hf_ltx: none")
            _save("hf_wan", hf_video.wan(_choice(), "probe", 5))
    else:
        print("plate hf: skipped")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"probe_plates_crashed {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
