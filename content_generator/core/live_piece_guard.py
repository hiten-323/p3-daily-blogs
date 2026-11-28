"""Protect already-published pieces from later regeneration overwrites.

Retry-unposted and publish-recovery used to rewrite content_<date>.json after
a platform was already VERIFIED_LIVE, so the saved pack no longer matched
what went out and the learning loop could not attribute performance.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

POSTED_STATES = ("VERIFIED_LIVE", "PUBLISHED_UNVERIFIED", "UNCERTAIN")

LABEL_BY_PLATFORM_SLOT = {
    ("linkedin", "generate"): "linkedin_post",
    ("threads", "generate"): "threads_post",
    ("youtube", "generate"): "yt_short",
    ("youtube", "evening"): "evening_yt_short",
    ("facebook", "morning"): "facebook_post",
    ("facebook", "evening"): "growth_reel_fb",
    ("blog", "generate"): "blog_post",
    ("shopify", "generate"): "blog_post",
    ("instagram", "morning"): "instagram_post",
    ("instagram_story", "morning"): "stories",
}

KNOWN_LABELS = {
    "linkedin_post", "facebook_post", "threads_post", "yt_short",
    "instagram_post", "carousel", "growth_reel", "reel_1",
    "growth_reel_fb", "evening_yt_short", "blog_post", "stories",
}

PLATFORM_FOR_LABEL = {
    "linkedin_post": "linkedin",
    "facebook_post": "facebook",
    "threads_post": "threads",
    "yt_short": "youtube",
    "evening_yt_short": "youtube",
    "instagram_post": "instagram",
    "carousel": "instagram",
    "growth_reel": "instagram",
    "reel_1": "instagram",
    "stories": "instagram_story",
    "growth_reel_fb": "facebook",
    "blog_post": "blog",
}


def label_for_record(record: dict) -> str | None:
    asset = str((record or {}).get("asset") or "").strip()
    if asset in KNOWN_LABELS:
        return asset
    platform = str((record or {}).get("platform") or "").strip().lower()
    slot = str((record or {}).get("slot") or "").strip()
    return LABEL_BY_PLATFORM_SLOT.get((platform, slot))


def label_for_platform(platform: str, asset: str = "", slot: str = "") -> str | None:
    asset = str(asset or "").strip()
    if asset in KNOWN_LABELS:
        return asset
    return LABEL_BY_PLATFORM_SLOT.get((str(platform or "").strip().lower(),
                                       str(slot or "generate").strip()))


def extract_piece(content: dict, label: str) -> dict | None:
    if not isinstance(content, dict) or not label:
        return None
    if label == "reel_1":
        reels = content.get("reels") or []
        piece = reels[0] if isinstance(reels, list) and reels else None
    elif label == "stories":
        holder = content.get("stories")
        piece = holder.get("story_1") if isinstance(holder, dict) else holder
    else:
        piece = content.get(label)
    return copy.deepcopy(piece) if isinstance(piece, dict) and piece else None


def place_piece(content: dict, label: str, piece: dict) -> None:
    if not isinstance(content, dict) or not label or not isinstance(piece, dict):
        return
    stored = copy.deepcopy(piece)
    if label == "reel_1":
        reels = content.setdefault("reels", [{}])
        if not isinstance(reels, list) or not reels:
            content["reels"] = [stored]
        else:
            reels[0] = stored
        return
    if label == "stories":
        holder = content.get("stories")
        if isinstance(holder, dict):
            holder["story_1"] = stored
        else:
            content["stories"] = {"story_1": stored}
        return
    content[label] = stored


def snapshot_from_content(content: dict, platform: str, asset: str = "", slot: str = "") -> dict | None:
    label = label_for_platform(platform, asset, slot)
    if not label:
        return None
    piece = extract_piece(content, label)
    if not piece:
        return None
    return {
        "label": label,
        "piece": piece,
        "featured_product": content.get("featured_product"),
        "source": str(piece.get("source") or content.get("source") or ""),
    }


def live_labels(content: dict | None, records: list[dict] | None = None) -> set[str]:
    """Labels whose ledger row (or in-pack snapshot) says the piece already went live."""
    labels: set[str] = set()
    snaps = (content or {}).get("_posted_snapshots") if isinstance(content, dict) else None
    if isinstance(snaps, dict):
        labels.update(k for k in snaps if k in KNOWN_LABELS)
    if records is None and isinstance(content, dict):
        records = _records_for_content(content)
    for record in records or []:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "") not in POSTED_STATES:
            continue
        label = label_for_record(record)
        if label:
            labels.add(label)
    return labels


def _records_for_content(content: dict) -> list[dict]:
    try:
        from content_generator.core.ist_dates import content_date_iso
        from content_generator.publisher.publishing_ledger import records_for_content_date
        date = content_date_iso(content.get("date")) or str(content.get("date") or "")[:10]
        if not date:
            return []
        return records_for_content_date(date)
    except Exception as exc:
        logger.debug("[live-piece] ledger read skipped: %s", exc)
        return []


def restore_live_pieces(content: dict, records: list[dict] | None = None) -> list[str]:
    """Overwrite in-memory pieces that already went live with the posted snapshot.

    Returns the labels that were restored.
    """
    if not isinstance(content, dict):
        return []
    restored: list[str] = []
    local = content.get("_posted_snapshots") if isinstance(content.get("_posted_snapshots"), dict) else {}
    if records is None:
        records = _records_for_content(content)
    by_label: dict[str, dict] = {}
    for record in records or []:
        if not isinstance(record, dict) or str(record.get("status") or "") not in POSTED_STATES:
            continue
        label = label_for_record(record)
        snap = record.get("posted_snapshot")
        if label and isinstance(snap, dict) and snap.get("piece"):
            by_label[label] = snap
    for label, snap in local.items():
        if label in KNOWN_LABELS and isinstance(snap, dict) and snap.get("piece") and label not in by_label:
            by_label[label] = snap
    for label, snap in by_label.items():
        piece = snap.get("piece")
        if not isinstance(piece, dict):
            continue
        current = extract_piece(content, label)
        if current == piece:
            content.setdefault("_posted_snapshots", {})[label] = copy.deepcopy(snap)
            continue
        place_piece(content, label, piece)
        content.setdefault("_posted_snapshots", {})[label] = copy.deepcopy(snap)
        restored.append(label)
        logger.warning("[live-piece] Restored already-published %s; regeneration must not overwrite it", label)
    return restored


def capture_posted_snapshot(content: dict, platform: str, asset: str = "", slot: str = "",
                            record_key: str = "") -> dict | None:
    """Remember the exact piece that was just posted (content pack + ledger)."""
    snap = snapshot_from_content(content, platform, asset, slot)
    if not snap:
        return None
    content.setdefault("_posted_snapshots", {})[snap["label"]] = copy.deepcopy(snap)
    return snap
