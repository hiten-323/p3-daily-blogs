"""Fail-closed pre-publish quality authorization for every external platform.

This is an enforcement layer, not a viral-performance prediction. Platform-native
assets must be present and pass the applicable editorial/readiness checks before
a publisher can make an API call.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PLATFORM_KEYS = {
    "instagram": ("carousel", "instagram_post"),
    "facebook": ("facebook_post",),
    "threads": ("threads_post",),
    "linkedin": ("linkedin_post",),
    "youtube": ("yt_short",),
    "shopify": ("blog_post",),
}


def _native_asset(content: dict, platform: str) -> tuple[str, dict | None]:
    for key in _PLATFORM_KEYS[platform]:
        value = content.get(key)
        if platform == "instagram" and key in ("reel_1", "reel_2"):
            reels = content.get("reels") or []
            index = 0 if key == "reel_1" else 1
            value = reels[index] if len(reels) > index else value
        if isinstance(value, dict) and value:
            return key, value
        if isinstance(value, str) and value.strip():
            return key, {"text": value.strip(), "body": value.strip()}
    return "", None


def authorize_publish(content: Any, platform: str) -> dict:
    """Return {allowed, asset_key, reason, checks}; exceptions fail closed."""
    platform = str(platform or "").strip().lower()
    if platform not in _PLATFORM_KEYS:
        return {"allowed": False, "asset_key": "", "reason": "unknown_platform", "checks": {}}
    if not isinstance(content, dict):
        return {"allowed": False, "asset_key": "", "reason": "invalid_content_payload", "checks": {}}

    try:
        from content_generator.core.editorial_engine import approved_assets, get_current_pass_score
        approved = approved_assets(content)
        if not isinstance(approved, dict):
            raise TypeError("approved_assets returned a non-dict result")
    except Exception as exc:
        logger.exception("[prepublish] Editorial gate failed for %s", platform)
        return {"allowed": False, "asset_key": "", "reason": f"editorial_gate_error:{type(exc).__name__}", "checks": {}}

    key, asset = _native_asset(content, platform)
    if not key or not asset:
        return {"allowed": False, "asset_key": "", "reason": "missing_native_asset", "checks": {"editorial": False}}

    # Existing editorial-approved assets must be the exact objects authorized by
    # the canonical gate. No substitute asset is accepted for these platforms.
    if platform in ("instagram", "linkedin", "youtube", "shopify"):
        canonical_key = {"instagram": key, "linkedin": "linkedin_post",
                         "youtube": "yt_short", "shopify": "blog_post"}[platform]
        # Instagram can publish the carousel or Instagram post, but reel-only
        # approval does not authorize a carousel image payload.
        if canonical_key not in approved:
            return {"allowed": False, "asset_key": key, "reason": "canonical_editorial_rejection", "checks": {"editorial": False}}
        asset = approved[canonical_key]
        key = canonical_key

    # Facebook and Threads have separate native copy. They must carry a measured
    # editorial score themselves; approval of another platform's copy is not a
    # substitute for reviewing this platform's actual text.
    if platform in ("facebook", "threads"):
        score = asset.get("editorial_score")
        try:
            score_value = float(score.get("overall")) if isinstance(score, dict) else None
        except (TypeError, ValueError):
            score_value = None
        threshold = get_current_pass_score()
        if score_value is None or score_value < threshold:
            return {"allowed": False, "asset_key": key, "reason": "native_asset_missing_passing_editorial_score", "checks": {"editorial": False}}

    # Platform-native content also receives the anti-fabrication and platform
    # format diagnostics. These are blocking errors, not advisory logging.
    try:
        from content_generator.core.growth_contract import audit_asset
        objective = str(asset.get("funnel_objective") or asset.get("objective") or "")
        native_audit = audit_asset(platform, asset, objective)
        if native_audit.get("errors"):
            return {"allowed": False, "asset_key": key, "reason": "platform_contract_failed",
                    "checks": {"editorial": True, "platform_contract": native_audit}}
    except Exception as exc:
        logger.exception("[prepublish] Platform contract failed for %s", platform)
        return {"allowed": False, "asset_key": key, "reason": f"platform_contract_error:{type(exc).__name__}", "checks": {"editorial": True}}

    try:
        from content_generator.core.brand_validator import validate_no_prohibited_claims
        native_text = " ".join(str(asset.get(field) or "") for field in
                               ("hook", "title", "body", "text", "caption", "cta", "content"))
        if not validate_no_prohibited_claims(native_text):
            return {"allowed": False, "asset_key": key, "reason": "prohibited_claim_detected",
                    "checks": {"editorial": True, "platform_contract": native_audit}}
    except Exception as exc:
        logger.exception("[prepublish] Claim safety gate failed for %s", platform)
        return {"allowed": False, "asset_key": key, "reason": f"claim_safety_error:{type(exc).__name__}", "checks": {"editorial": True}}

    try:
        from content_generator.core.viral_readiness import evaluate_viral_readiness
        readiness = evaluate_viral_readiness(asset, platform=platform)
        if not readiness.get("passes"):
            return {"allowed": False, "asset_key": key, "reason": "viral_readiness_failed", "checks": {"editorial": True, "viral_readiness": readiness}}
    except Exception as exc:
        logger.exception("[prepublish] Viral-readiness gate failed for %s", platform)
        return {"allowed": False, "asset_key": key, "reason": f"viral_readiness_error:{type(exc).__name__}", "checks": {"editorial": True}}

    try:
        from content_generator.core.content_contract import shareability
        share = shareability(asset)
        if not share.get("passes"):
            return {"allowed": False, "asset_key": key, "reason": "shareability_failed", "checks": {"editorial": True, "viral_readiness": readiness, "shareability": share}}
    except Exception as exc:
        logger.exception("[prepublish] Shareability gate failed for %s", platform)
        return {"allowed": False, "asset_key": key, "reason": f"shareability_error:{type(exc).__name__}", "checks": {"editorial": True, "viral_readiness": readiness}}

    # Platform-specific hard limits / native structure.
    if platform == "threads":
        text = str(asset.get("text") or asset.get("body") or asset.get("content") or "").strip()
        if not text:
            return {"allowed": False, "asset_key": key, "reason": "empty_native_threads_text", "checks": {"editorial": True}}
        if len(text) > 500:
            return {"allowed": False, "asset_key": key, "reason": "threads_text_over_500_characters", "checks": {"editorial": True}}
    if platform == "youtube":
        scenes, script = asset.get("scenes"), asset.get("script")
        if not (isinstance(scenes, list) and len(scenes) >= 3) and not (isinstance(script, list) and len(script) >= 3):
            return {"allowed": False, "asset_key": key, "reason": "youtube_short_missing_3_beat_plan", "checks": {"editorial": True, "viral_readiness": readiness, "shareability": share}}

    return {"allowed": True, "asset_key": key, "reason": "all_pre_publish_checks_passed",
            "checks": {"editorial": True, "viral_readiness": readiness, "shareability": share}}
