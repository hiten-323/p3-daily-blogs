"""
Jar Provenance & Verification Module.

Enforces the hard invariant:
"A product-bearing creative cannot exist or be published unless a verified real-jar image is present."

Guarantees:
- Every image generated from real_jar_composer, gemini_scene, or cinematic_frame is registered with:
    asset_real_jar_verified = True
    jar_asset_id = <actual existing path in brand_assets/>
    render_source = "real_jar" | "gemini_real_jar" | "cinematic_real_jar"
- Derived images (e.g. 4:5 crops for feed) inherit the parent's verified provenance.
- The publish gates (slots.py, editorial_engine.py, publishers) verify provenance.
- Any image without verified provenance is HELD from publication.
"""
from __future__ import annotations
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_PROVENANCE_FILE = os.path.join(_OUT_DIR, "jar_provenance.json")

VALID_RENDER_SOURCES = {
    "real_jar",
    "gemini_real_jar",
    "cinematic_real_jar",
}

_MEMORY_REGISTRY: dict[str, dict] = {}


def _norm_key(path: str) -> str:
    """Normalize path to filename key for robust lookup across relative/absolute variants."""
    return os.path.basename(path).lower()


def _load_registry() -> dict[str, dict]:
    global _MEMORY_REGISTRY
    if os.path.exists(_PROVENANCE_FILE):
        try:
            with open(_PROVENANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict) and k not in _MEMORY_REGISTRY:
                            _MEMORY_REGISTRY[k] = v
        except Exception as e:
            logger.debug("[provenance] Could not load registry: %s", e)
    return _MEMORY_REGISTRY


def _save_registry() -> None:
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        with open(_PROVENANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(_MEMORY_REGISTRY, f, indent=2)
    except Exception as e:
        logger.warning("[provenance] Could not save registry: %s", e)


def record_jar_provenance(
    image_path: str,
    jar_asset_id: str,
    render_source: str,
) -> dict:
    """
    Record verified provenance for a generated image.
    Validates that jar_asset_id exists on disk and render_source is an approved tier.
    """
    _load_registry()

    jar_asset_id = os.path.normpath(jar_asset_id) if jar_asset_id else ""
    jar_exists = bool(jar_asset_id and os.path.exists(jar_asset_id))
    valid_source = render_source in VALID_RENDER_SOURCES
    is_verified = bool(jar_exists and valid_source)

    entry = {
        "image_path": image_path,
        "image_filename": os.path.basename(image_path),
        "asset_real_jar_verified": is_verified,
        "jar_asset_id": jar_asset_id,
        "render_source": render_source,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    key = _norm_key(image_path)
    _MEMORY_REGISTRY[key] = entry
    _save_registry()

    if is_verified:
        logger.info(
            "[provenance] Verified real-jar image: %s (source=%s, jar=%s)",
            os.path.basename(image_path), render_source, os.path.basename(jar_asset_id)
        )
    else:
        logger.warning(
            "[provenance] FAILED verification for %s (jar_exists=%s, valid_source=%s)",
            image_path, jar_exists, valid_source
        )

    return entry


def inherit_provenance(derived_path: str, source_path: str) -> dict | None:
    """Inherit provenance for derived assets (e.g. 4:5 feed crops from 9:16 reels)."""
    parent = verify_jar_provenance(source_path)
    if not parent.get("verified"):
        logger.warning("[provenance] Cannot inherit unverified provenance from %s", source_path)
        return None

    return record_jar_provenance(
        image_path=derived_path,
        jar_asset_id=parent["jar_asset_id"],
        render_source=parent["render_source"],
    )


def verify_jar_provenance(image_path: str) -> dict:
    """
    Verify whether an image was created directly from an authentic real jar photo.

    Returns:
        {
            "verified": bool,
            "jar_asset_id": str | None,
            "render_source": str | None,
            "reason": str | None
        }
    """
    if not image_path:
        return {"verified": False, "jar_asset_id": None, "render_source": None, "reason": "empty_path"}

    if not os.path.exists(image_path):
        return {"verified": False, "jar_asset_id": None, "render_source": None, "reason": "file_not_found"}

    reg = _load_registry()
    key = _norm_key(image_path)
    entry = reg.get(key)

    if not entry:
        return {"verified": False, "jar_asset_id": None, "render_source": None, "reason": "unregistered_image"}

    if not entry.get("asset_real_jar_verified"):
        return {"verified": False, "jar_asset_id": entry.get("jar_asset_id"),
                "render_source": entry.get("render_source"), "reason": "unverified_flag"}

    source = entry.get("render_source")
    if source not in VALID_RENDER_SOURCES:
        return {"verified": False, "jar_asset_id": entry.get("jar_asset_id"),
                "render_source": source, "reason": "invalid_render_source"}

    jar_asset = entry.get("jar_asset_id")
    if not jar_asset or not os.path.exists(jar_asset):
        return {"verified": False, "jar_asset_id": jar_asset,
                "render_source": source, "reason": "source_jar_missing_on_disk"}

    return {
        "verified": True,
        "jar_asset_id": jar_asset,
        "render_source": source,
        "reason": None,
    }


def verify_creative_suite(image_paths: list[str]) -> tuple[bool, list[str]]:
    """Verify an entire collection of images (e.g. carousel slides)."""
    if not image_paths:
        return False, ["no_images_provided"]

    issues = []
    for p in image_paths:
        check = verify_jar_provenance(p)
        if not check["verified"]:
            issues.append(f"{os.path.basename(p)}: {check.get('reason')}")

    return len(issues) == 0, issues
