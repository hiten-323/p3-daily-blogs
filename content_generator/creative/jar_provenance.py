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
import hashlib
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def _sha256(path: str) -> str | None:
    """Compute hex SHA-256 digest of a file; returns None if file does not exist or cannot be read."""
    if not path:
        return None
    try:
        if not os.path.isfile(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_PROVENANCE_FILE = os.path.join(_OUT_DIR, "jar_provenance.json")
_TRUSTED_JAR_ASSET_ROOT = os.path.abspath(os.getenv("PURITY_BRAND_ASSET_ROOT", "brand_assets"))

VALID_RENDER_SOURCES = {
    "real_jar",
    "gemini_real_jar",
    "cinematic_real_jar",
    "approved_photo",   # official photo used as-is (crop/resize/overlay only)
}

_MEMORY_REGISTRY: dict[str, dict] = {}


def _canonical_key(path: str) -> str:
    """Canonical path key for collision-free lookup across relative/absolute variants."""
    if not path:
        return ""
    try:
        abs_p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
        return abs_p.replace("\\", "/")
    except Exception:
        return os.path.abspath(path).replace("\\", "/").lower()


def _portable_key(path: str) -> str:
    """Portable repo-relative key across runners and platforms."""
    if not path:
        return ""
    try:
        rel = os.path.relpath(os.path.realpath(path), os.path.abspath(".")).replace("\\", "/")
        return os.path.normcase(rel)
    except Exception:
        return os.path.normcase(path.replace("\\", "/"))


def _norm_key(path: str) -> str:
    """Normalize path to a canonical, collision-free key."""
    return _canonical_key(path)


def _paths_match(recorded_path: str, candidate_path: str) -> bool:
    """Check whether candidate_path corresponds to recorded_path without filename collisions."""
    if not recorded_path or not candidate_path:
        return False
    try:
        if os.path.exists(recorded_path) and os.path.exists(candidate_path):
            if os.path.samefile(recorded_path, candidate_path):
                return True
    except (OSError, ValueError):
        pass

    can_rec = _canonical_key(recorded_path)
    can_cand = _canonical_key(candidate_path)
    if can_rec and can_cand and can_rec == can_cand:
        return True

    port_rec = _portable_key(recorded_path)
    port_cand = _portable_key(candidate_path)
    if port_rec and port_cand and port_rec == port_cand:
        return True

    norm_rec = os.path.normpath(recorded_path).replace("\\", "/").strip("/").lower()
    norm_cand = os.path.normpath(candidate_path).replace("\\", "/").strip("/").lower()
    if norm_rec == norm_cand:
        return True

    # Suffix check with directory separator prevents matching different directories
    if "/" in norm_rec and norm_cand.endswith("/" + norm_rec):
        return True
    if "/" in norm_cand and norm_rec.endswith("/" + norm_cand):
        return True

    return False


def _find_entry(reg: dict[str, dict], image_path: str) -> dict | None:
    """Find registry entry by canonical key, portable key, or verified path match."""
    can_key = _canonical_key(image_path)
    if can_key in reg:
        return reg[can_key]

    port_key = _portable_key(image_path)
    if port_key in reg:
        return reg[port_key]

    norm_p = os.path.normpath(image_path).replace("\\", "/").lower()
    if norm_p in reg:
        return reg[norm_p]

    for k, entry in reg.items():
        if isinstance(entry, dict):
            rec = entry.get("image_path") or k
            if _paths_match(rec, image_path):
                return entry

    # Fallback to legacy basename key only if the entry's recorded path actually matches
    base = os.path.basename(image_path).lower()
    if base in reg:
        candidate_entry = reg[base]
        if isinstance(candidate_entry, dict):
            rec = candidate_entry.get("image_path")
            if not rec or _paths_match(rec, image_path):
                return candidate_entry

    return None


def _trusted_jar_asset(path: str) -> bool:
    """Only first-party files inside the trusted brand-assets directory count as jar sources."""
    if not path:
        return False
    try:
        candidate = os.path.realpath(path)
        root = os.path.realpath(_TRUSTED_JAR_ASSET_ROOT)
        return os.path.isfile(candidate) and os.path.commonpath((candidate, root)) == root
    except (OSError, ValueError):
        return False


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


def _save_registry() -> bool:
    """Persist registry atomically so an interrupted runner cannot truncate it. Returns True on success, False on failure."""
    tmp_path = ""
    try:
        os.makedirs(_OUT_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=_OUT_DIR,
            prefix=".jar_provenance.", suffix=".tmp", delete=False,
        ) as handle:
            tmp_path = handle.name
            json.dump(_MEMORY_REGISTRY, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, _PROVENANCE_FILE)
        tmp_path = ""
        return True
    except Exception as e:
        logger.warning("[provenance] Could not save registry atomically: %s", type(e).__name__)
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def record_jar_provenance(
    image_path: str,
    jar_asset_id: str,
    render_source: str,
) -> dict:
    """
    Record verified provenance for a generated image.
    Validates that jar_asset_id exists on disk, render_source is an approved tier,
    and binds provenance to SHA-256 hashes of both image and source jar.
    """
    _load_registry()

    jar_asset_id = os.path.normpath(jar_asset_id) if jar_asset_id else ""
    trusted_jar = _trusted_jar_asset(jar_asset_id)
    valid_source = render_source in VALID_RENDER_SOURCES

    image_hash = _sha256(image_path)
    jar_hash = _sha256(jar_asset_id) if trusted_jar else None

    # An image cannot be verified without authentic file content on disk
    is_verified = bool(trusted_jar and valid_source and image_hash and jar_hash)

    if trusted_jar:
        # Persist a repository-relative path so a fresh runner can re-verify it.
        jar_asset_id = os.path.relpath(os.path.realpath(jar_asset_id), os.path.abspath("."))

    entry = {
        "image_path": image_path.replace("\\", "/"),
        "image_filename": os.path.basename(image_path),
        "image_sha256": image_hash,
        "jar_sha256": jar_hash,
        "asset_real_jar_verified": is_verified,
        "jar_asset_id": jar_asset_id.replace("\\", "/"),
        "render_source": render_source,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    can_key = _canonical_key(image_path)
    _MEMORY_REGISTRY[can_key] = entry
    port_key = _portable_key(image_path)
    if port_key and port_key != can_key:
        _MEMORY_REGISTRY[port_key] = entry

    saved = _save_registry()
    if not saved:
        logger.warning("[provenance] Persistence failed for %s — failing closed", image_path)
        _MEMORY_REGISTRY.pop(can_key, None)
        if port_key:
            _MEMORY_REGISTRY.pop(port_key, None)
        entry["asset_real_jar_verified"] = False
        entry["reason"] = "persistence_failed"
        return entry

    if is_verified:
        logger.info(
            "[provenance] Verified real-jar image: %s (source=%s, jar=%s)",
            os.path.basename(image_path), render_source, os.path.basename(jar_asset_id)
        )
    else:
        logger.warning(
            "[provenance] FAILED verification for %s (jar_exists=%s, valid_source=%s)",
            image_path, trusted_jar, valid_source
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
    entry = _find_entry(reg, image_path)

    if not entry:
        return {"verified": False, "jar_asset_id": None, "render_source": None, "reason": "unregistered_image"}

    recorded_path = entry.get("image_path")
    if recorded_path and not _paths_match(recorded_path, image_path):
        return {"verified": False, "jar_asset_id": None, "render_source": None, "reason": "image_path_mismatch"}

    if not entry.get("asset_real_jar_verified"):
        return {"verified": False, "jar_asset_id": entry.get("jar_asset_id"),
                "render_source": entry.get("render_source"), "reason": "unverified_flag"}

    source = entry.get("render_source")
    if source not in VALID_RENDER_SOURCES:
        return {"verified": False, "jar_asset_id": entry.get("jar_asset_id"),
                "render_source": source, "reason": "invalid_render_source"}

    jar_asset = entry.get("jar_asset_id")
    if not jar_asset or not _trusted_jar_asset(jar_asset):
        return {"verified": False, "jar_asset_id": jar_asset,
                "render_source": source, "reason": "source_jar_missing_or_untrusted"}

    # Content-bound integrity: reject tampered image file
    recorded_img_hash = entry.get("image_sha256")
    if recorded_img_hash:
        current_img_hash = _sha256(image_path)
        if not current_img_hash or current_img_hash != recorded_img_hash:
            return {"verified": False, "jar_asset_id": jar_asset,
                    "render_source": source, "reason": "image_content_tampered"}

    # Content-bound integrity: reject modified source jar file
    recorded_jar_hash = entry.get("jar_sha256")
    if recorded_jar_hash:
        current_jar_hash = _sha256(jar_asset)
        if not current_jar_hash or current_jar_hash != recorded_jar_hash:
            return {"verified": False, "jar_asset_id": jar_asset,
                    "render_source": source, "reason": "source_jar_content_tampered"}

    return {
        "verified": True,
        # Keep the registry portable across runners, but expose an absolute
        # verified path to callers so downstream asset checks use a stable path.
        "jar_asset_id": os.path.abspath(jar_asset),
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
