"""Platform-native follower-growth contract.

This is a deterministic pre-publish diagnostic, not a promise of virality.
It prevents known strategy regressions: cross-platform fallback, missing
follow mechanism, product-first discovery content, and fabricated social proof.
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "follower-growth-v1"
PLATFORMS = {
    "instagram": {"assets": ("growth_reel", "reels", "carousel", "instagram_post", "stories")},
    "facebook": {"assets": ("facebook_post", "facebook_reel")},
    "youtube": {"assets": ("yt_short",)},
    "threads": {"assets": ("threads_post",)},
    "linkedin": {"assets": ("linkedin_post",)},
    "shopify": {"assets": ("blog_post",)},
}

_FOLLOW_TERMS = ("follow", "subscribe", "follow along", "for more", "daily")
_PROMO_TERMS = ("shop now", "buy now", "order now", "visit https://p3online.in")
_FABRICATED_PROOF_TERMS = ("customers love", "customer said", "dm from @", "review from @", "10,000 customers", "11247 customers")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, (str, int, float)):
                parts.append(str(item))
            elif isinstance(item, list):
                parts.extend(_text(x) for x in item)
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_text(x) for x in value)
    return ""


def audit_asset(platform: str, asset: Any, objective: str = "") -> dict:
    """Return actionable diagnostics for a single platform asset."""
    platform = platform.lower().strip()
    errors: list[str] = []
    warnings: list[str] = []
    if platform not in PLATFORMS:
        return {"platform": platform, "passes": False, "errors": ["unknown platform"], "warnings": []}
    if not isinstance(asset, (dict, str)) or not _text(asset).strip():
        return {"platform": platform, "passes": False, "errors": ["missing or empty native asset"], "warnings": []}

    text = _text(asset).lower()
    if platform in ("instagram", "facebook", "youtube", "threads", "linkedin") and objective.upper() in ("FOLLOW", "DISCOVERY", "ENGAGEMENT GROWTH"):
        if not any(term in text for term in _FOLLOW_TERMS):
            warnings.append("no explicit follow/subscribe reason found")
        if any(term in text for term in _PROMO_TERMS):
            warnings.append("discovery asset contains a direct sales CTA")
    if any(term in text for term in _FABRICATED_PROOF_TERMS):
        errors.append("possible fabricated social proof; require verified evidence or remove")
    if platform == "youtube" and isinstance(asset, dict):
        scenes = asset.get("scenes")
        script = asset.get("script")
        if not (isinstance(scenes, list) and len(scenes) >= 3) and not (isinstance(script, list) and len(script) >= 3):
            warnings.append("Short lacks a complete 3+ beat native video plan")
        if not (asset.get("title") or asset.get("hook")):
            errors.append("YouTube Short missing its own title/hook")
    if platform == "threads" and isinstance(asset, dict):
        post = str(asset.get("text") or asset.get("body") or "").strip()
        if len(post) > 480:
            errors.append("Threads post exceeds the configured 480-character target")
        if "p3online.in" in post.lower():
            warnings.append("Threads post contains a website link; prefer conversation-first copy")
    if platform == "facebook" and isinstance(asset, dict):
        if not any(asset.get(k) for k in ("hook", "body", "text", "caption")):
            errors.append("Facebook asset missing native copy")
    return {
        "platform": platform,
        "contract_version": CONTRACT_VERSION,
        "passes": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def audit_portfolio(content: dict) -> dict:
    """Audit only assets present; do not fabricate missing platform content."""
    content = content if isinstance(content, dict) else {}
    mapping = {
        "facebook": content.get("facebook_post") or content.get("facebook_reel"),
        "youtube": content.get("yt_short"),
        "threads": content.get("threads_post"),
        "linkedin": content.get("linkedin_post"),
    }
    results = {}
    for platform, asset in mapping.items():
        objective = str(asset.get("objective") or "") if isinstance(asset, dict) else ""
        results[platform] = audit_asset(platform, asset, objective)
    return {
        "contract_version": CONTRACT_VERSION,
        "passes": all(r["passes"] for r in results.values()),
        "results": results,
    }
