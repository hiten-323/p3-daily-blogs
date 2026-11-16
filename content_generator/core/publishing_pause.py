"""Global publishing pause (owner-controlled config file).

Publishing is ON by default: every scheduled slot, retry-unposted and publish
recovery publish to every platform each day (owner, 16 Nov 2026: "my content
gets posted every day on all the platforms"). The PUBLISHING_ENABLED repository
variable no longer gates anything.

To pause all platforms, set config/publishing_pause.json -> {"paused": true}
in a PR (or env PUBLISHING_PAUSED=true for one run). To pause only Instagram,
use config/instagram_pause.json. A manual dry run never publishes.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
PAUSE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "config", "publishing_pause.json")


def publishing_paused() -> bool:
    raw = str(os.getenv("PUBLISHING_PAUSED", "") or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    path = os.getenv("PUBLISHING_PAUSE_FILE", PAUSE_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(json.load(fh).get("paused"))
    except FileNotFoundError:
        return False
    except Exception as exc:  # unreadable switch: fail safe (paused)
        logger.error("[publishing-pause] could not read %s (%s); treating publishing as PAUSED", path, exc)
        return True


def dry_run() -> bool:
    return os.getenv("DRY_RUN", "").strip().lower() in _TRUE
