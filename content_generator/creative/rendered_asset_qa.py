"""Technical pixel-level QA for assets immediately before social publishing.

This module checks image integrity and composition-level technical failures. It
does not claim to automatically detect all AI artifacts or judge brand taste.
"""
from __future__ import annotations

import os


def audit_rendered_images(image_paths: list[str]) -> dict:
    """Fail closed on unreadable, undersized, flat, unsupported or duplicate images."""
    issues: list[str] = []
    if not image_paths:
        return {"ok": False, "issues": ["no_rendered_images"], "images_checked": 0}
    try:
        from PIL import Image, ImageStat
    except Exception:
        return {"ok": False, "issues": ["Pillow_unavailable_visual_QA_cannot_run"], "images_checked": 0}

    signatures: set[tuple[bytes, int]] = set()
    for path in image_paths:
        try:
            with Image.open(path) as source:
                source.verify()
            with Image.open(path) as source:
                image = source.convert("RGB")
                width, height = image.size
                ratio = width / max(height, 1)
                if width < 720 or height < 720:
                    issues.append(f"{os.path.basename(path)}: resolution_below_720px")
                if ratio < 0.55 or ratio > 1.95:
                    issues.append(f"{os.path.basename(path)}: unsupported_aspect_ratio")
                stat = ImageStat.Stat(image.resize((64, 64)))
                if max(stat.stddev) < 3.0:
                    issues.append(f"{os.path.basename(path)}: nearly_blank_or_flat_image")
                signature = (image.resize((24, 24)).tobytes(), round(ratio * 1000))
                if signature in signatures:
                    issues.append(f"{os.path.basename(path)}: duplicate_slide_image")
                signatures.add(signature)
        except Exception as exc:
            issues.append(f"{os.path.basename(path)}: unreadable_image:{type(exc).__name__}")
    return {"ok": not issues, "issues": issues, "images_checked": len(image_paths)}
