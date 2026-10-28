"""Instagram publish kill switch (owner-controlled).

When paused, nothing in this pipeline publishes to Instagram: feed post,
carousel, Story, reels, sales story/reel, and the after-midnight evening
backstop. Facebook, Threads, LinkedIn and YouTube are unaffected.

A paused piece is NOT a failure: it is never sent to Meta, never written to
the publishing ledger as an attempt, and never queued for retry-unposted, so
no retry budget is burned while paused.

Control (first match wins):
  1. env INSTAGRAM_PUBLISH_PAUSED (true/false), e.g. from a repo variable;
  2. config/instagram_pause.json -> {"paused": true|false}.
Unset/missing -> not paused.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
PAUSE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "config", "instagram_pause.json")
PAUSED_ERROR = "instagram_paused"


def instagram_paused() -> bool:
    raw = str(os.getenv("INSTAGRAM_PUBLISH_PAUSED", "") or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    path = os.getenv("INSTAGRAM_PAUSE_FILE", PAUSE_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(json.load(fh).get("paused"))
    except FileNotFoundError:
        return False
    except Exception as exc:  # unreadable switch: fail safe (paused)
        logger.error("[instagram-pause] could not read %s (%s); treating Instagram as PAUSED", path, exc)
        return True


def paused_result() -> dict:
    """Publisher-shaped result for a paused call: not attempted, not retried."""
    logger.warning("[instagram] PAUSED by owner kill switch — not publishing to Instagram")
    return {"success": False, "attempted": False, "skipped": True, "paused": True,
            "media_id": "", "permalink": "", "error": PAUSED_ERROR}
