"""
Video hosting — Instagram Reels need a PUBLIC video URL (imgbb is images only).

Cloudinary free tier includes video. Set CLOUDINARY_URL:
    cloudinary://<api_key>:<api_secret>@<cloud_name>

Signed REST upload (no SDK dependency). Returns a public https URL, or None.
"""
from __future__ import annotations
import hashlib
import logging
import os
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)
_TIMEOUT = 120


def _creds() -> tuple[str, str, str] | None:
    url = os.getenv("CLOUDINARY_URL", "").strip().strip('"').strip("'").strip()
    # Cloudinary's dashboard shows "CLOUDINARY_URL=cloudinary://..."; accept a pasted prefix.
    if url.upper().startswith("CLOUDINARY_URL="):
        url = url.split("=", 1)[1].strip().strip('"').strip("'")
    if not url.startswith("cloudinary://"):
        if url:
            logger.warning("[video_host] CLOUDINARY_URL is set but not in cloudinary://key:secret@cloud form")
        return None
    try:
        rest = url[len("cloudinary://"):]
        creds, cloud = rest.split("@", 1)
        api_key, api_secret = creds.split(":", 1)
        return api_key, api_secret, cloud
    except Exception:
        return None


def is_configured() -> bool:
    return _creds() is not None


def upload_video(path: str) -> str | None:
    """Upload a local video to Cloudinary; return its public URL."""
    c = _creds()
    if not c or not os.path.exists(path):
        return None
    api_key, api_secret, cloud = c

    timestamp = str(int(time.time()))
    # Cloudinary signature: sha1 of sorted params + api_secret
    to_sign = f"timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(to_sign.encode()).hexdigest()

    try:
        import requests
    except ImportError:
        logger.warning("[video_host] requests not installed")
        return None

    try:
        with open(path, "rb") as f:
            resp = requests.post(
                f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
                data={"api_key": api_key, "timestamp": timestamp, "signature": signature},
                files={"file": f},
                timeout=_TIMEOUT,
            )
        data = resp.json()
        url = data.get("secure_url") or data.get("url")
        if url:
            logger.info("[video_host] Uploaded video -> %s", url)
            return url
        logger.warning("[video_host] Cloudinary upload failed: %s", data.get("error", data))
        return None
    except Exception as e:
        logger.warning("[video_host] upload error: %s", e)
        return None
