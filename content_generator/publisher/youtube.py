"""
YouTube Shorts auto-publisher — uploads short-form video via YouTube Data API v3.

Prerequisites:
  1. Google Cloud Project with YouTube Data API v3 enabled
  2. OAuth 2.0 credentials (Desktop app or Service Account with domain-wide delegation)
  3. Channel connected to a YouTube account

Required secrets:
    YOUTUBE_CLIENT_ID       — OAuth 2.0 client ID
    YOUTUBE_CLIENT_SECRET   — OAuth 2.0 client secret
    YOUTUBE_REFRESH_TOKEN   — Offline refresh token (never expires unless revoked)
                              Generate once using the setup script below.

How to get YOUTUBE_REFRESH_TOKEN (one-time):
  1. Go to console.cloud.google.com → APIs → YouTube Data API v3 → Enable
  2. Create credentials → OAuth 2.0 Client ID → Desktop app
  3. Run: python -m content_generator.publisher.youtube --setup
     (opens browser, you approve, script prints refresh token — copy to GitHub secrets)

What gets posted:
    - YouTube Shorts (vertical 9:16 video under 60s)
    - Video source: looks for generated .mp4 in output/creative/
    - If no video file found: creates a still-image Short (image + audio narration hook)
    - Title: from reel hook text
    - Description: from reel script
    - Tags: coffee, instant coffee, purity beans, etc.

Note on video generation:
    For actual video, you need RUNWAY_API_KEY set. Without it, the engine
    generates a "slideshow short" from carousel images using Pillow + moviepy.
    Install: pip install moviepy  (adds ~50MB to container)
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_SCOPES       = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_URL    = "https://oauth2.googleapis.com/token"
_UPLOAD_URL   = "https://www.googleapis.com/upload/youtube/v3/videos"
_SHORTS_MAX_S = 59   # YouTube Shorts must be <= 60s
_UPLOAD_ATTEMPTS = 3
_UPLOAD_RESUMES = 6


def is_configured() -> bool:
    return (
        bool(os.getenv("YOUTUBE_CLIENT_ID"))
        and bool(os.getenv("YOUTUBE_CLIENT_SECRET"))
        and bool(os.getenv("YOUTUBE_REFRESH_TOKEN"))
    )


def post_content(content: dict, day: int = 0) -> dict:
    """
    Upload today's YouTube Short.

    Looks for a rendered video first. If none found, creates a slideshow
    Short from carousel images (requires moviepy).

    Returns:
        {"success": bool, "video_id": str, "url": str, "error": str|None}
    """
    from content_generator.publisher.dispatcher import editorial_disposition, not_attempted_result
    state = editorial_disposition(content, "yt_short")
    if state != "approved":
        logger.info("[youtube] Skipping yt_short — %s; not attempted", state)
        return not_attempted_result("yt_short", state)

    if not is_configured():
        logger.info("[youtube] Not configured — YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN missing")
        return {"success": False, "video_id": "", "url": "", "error": "not_configured"}

    # Find the file before any Google call. A missing file or a false claim
    # must not refresh an OAuth token or open an upload.
    video_path = _find_video(content)
    if not video_path:
        if os.getenv("ALLOW_YOUTUBE_SLIDESHOW", "").lower() in ("true", "1", "yes"):
            video_path = _create_slideshow_short(content, day)
        else:
            logger.info(
                "[youtube] No native video file rendered — holding YouTube Short to protect channel retention & viewed-vs-swiped ratio"
            )
            return {"success": False, "video_id": "", "url": "", "error": "held_no_native_video", "held": True}

    if not video_path:
        logger.warning("[youtube] No video available — skipping YouTube Short")
        return {"success": False, "video_id": "", "url": "", "error": "no_video"}

    # Build metadata
    title       = _extract_title(content)
    description = _extract_description(content)
    try:
        from content_generator.publisher.product_links import with_product_link
        description = with_product_link(description, content, "youtube", day=day, limit=5000)
    except Exception as e:
        logger.debug("[youtube] product link skipped: %s", e)
    tags        = _build_tags(content)

    from content_generator.core.product_truth import (
        featured_product_name, piece_copy_text, product_truth_findings, separate_ultra_from_pure,
    )
    title = separate_ultra_from_pure(title)
    description = separate_ultra_from_pure(description)
    short = content.get("yt_short") if isinstance(content.get("yt_short"), dict) else {}
    featured = featured_product_name(content) or str(short.get("featured_product") or "")
    spoken = piece_copy_text(short) if short else ""
    if product_truth_findings(f"{title}\n{description}\n{spoken}", featured=featured):
        logger.error("[youtube] Refusing a Short whose title, description, or script contradicts the jar")
        return {"success": False, "attempted": False, "skipped": True,
                "video_id": "", "url": "", "error": "product_truth_failed", "held": True}

    from content_generator.core.publish_bar import quality_block, reason_code
    block = quality_block(short, "yt_short")
    if block:
        code = reason_code(block)
        logger.warning("[youtube] Quality bar held the Short: %s", block)
        return {"success": False, "attempted": False, "skipped": True,
                "video_id": "", "url": "", "error": "prepublish_gate:" + code, "held": True}

    access_token = _refresh_access_token()
    if not access_token:
        return {"success": False, "video_id": "", "url": "", "error": "token_refresh_failed"}

    result = _upload_video(access_token, video_path, title, description, tags)

    if result["success"]:
        logger.info("[youtube] Day %d uploaded | id=%s | url=%s", day, result["video_id"], result["url"])
    else:
        logger.error("[youtube] Day %d failed: %s", day, result["error"])

    return result


# ── Token management ──────────────────────────────────────────────────────────

def _refresh_access_token() -> str | None:
    """Exchange refresh token for a fresh access token."""
    from content_generator.publisher.secret_mask import mask_secret, redact

    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    refresh = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
    mask_secret(client_secret)
    mask_secret(refresh)
    secrets = [client_secret, refresh]
    try:
        import requests
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     os.getenv("YOUTUBE_CLIENT_ID", ""),
                "client_secret": client_secret,
                "refresh_token": refresh,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            token = str(data["access_token"])
            mask_secret(token)
            return token
        message = data.get("error_description") or data.get("error") or "token_refresh_failed"
        logger.warning("[youtube] Token refresh failed: %s", redact(str(message), secrets))
        return None
    except Exception as e:
        logger.error("[youtube] Token refresh error: %s", redact(f"{type(e).__name__}", secrets))
        return None


# ── Video source ──────────────────────────────────────────────────────────────

def find_native_short(content: dict) -> str | None:
    """A dedicated Short file only. A reel mp4 is not this asset."""
    import glob as _glob
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    today = _today(content)
    patterns = [
        os.path.join(creative_dir, f"short_video_day*_{today}.mp4"),
        os.path.join(creative_dir, f"short_video_day*_{today}_cinematic.mp4"),
        os.path.join(creative_dir, f"yt_short_*_{today}.mp4"),
    ]
    for pat in patterns:
        files = sorted(_glob.glob(pat))
        if files:
            return files[-1]
    return None


def _find_video(content: dict) -> str | None:
    """Look for a rendered .mp4 Short in output/creative/."""
    import glob as _glob
    native = find_native_short(content)
    if native:
        return native
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    today = _today(content)

    patterns = [
        os.path.join(creative_dir, f"short_*_{today}.mp4"),
        os.path.join(creative_dir, f"reel_*_{today}.mp4"),
        os.path.join(creative_dir, f"*_{today}.mp4"),
    ]
    for pat in patterns:
        files = sorted(_glob.glob(pat), reverse=True)
        if files:
            return files[0]
    return None


def _create_slideshow_short(content: dict, day: int) -> str | None:
    """
    Create a ~30s YouTube Short by animating carousel images.
    Requires: pip install moviepy
    """
    try:
        from moviepy import ImageClip, concatenate_videoclips
    except ImportError:
        logger.debug("[youtube] moviepy not installed — cannot create slideshow Short")
        return None

    import glob as _glob
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

    images = (
        sorted(_glob.glob(os.path.join(creative_dir, "carousel_slide_*.jpg")))
        + sorted(_glob.glob(os.path.join(creative_dir, "carousel_slide_*.png")))
    )
    if not images:
        images = (
            sorted(_glob.glob(os.path.join(creative_dir, "*.jpg")))
            + sorted(_glob.glob(os.path.join(creative_dir, "*.png")))
        )
    if not images:
        return None

    try:
        duration_per_image = min(5, _SHORTS_MAX_S // max(len(images), 1))
        clips = []
        for img_path in images[:8]:
            # moviepy 2.0+ uses with_duration; resized() replaces resize()
            clip = ImageClip(img_path).with_duration(duration_per_image)
            if hasattr(clip, "resized"):
                clip = clip.resized(height=1920)
            clips.append(clip)

        final = concatenate_videoclips(clips, method="compose")
        today = today_ist().isoformat()
        out_path = os.path.join(creative_dir, f"short_slideshow_day{day}_{today}.mp4")
        final.write_videofile(out_path, fps=24, codec="libx264", audio=False, logger=None)
        logger.info("[youtube] Slideshow Short created: %s", out_path)
        return out_path

    except Exception as e:
        logger.warning("[youtube] Slideshow creation failed: %s", e)
        return None


# ── Upload ────────────────────────────────────────────────────────────────────

def _upload_video(
    access_token: str, video_path: str,
    title: str, description: str, tags: list[str],
) -> dict:
    """Upload one Short on a single resumable session.

    A dropped connection resumes the same session. It does not open a second
    video. Transient HTTP statuses get a bounded number of tries.
    """
    from content_generator.publisher.secret_mask import mask_secret, redact

    mask_secret(access_token)
    secrets = [
        access_token,
        os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
    ]

    def safe(text: str) -> str:
        return redact(text, secrets)[:300]

    try:
        import requests

        metadata = {
            "snippet": {
                "title":       title[:100],
                "description": description[:5000],
                "tags":        tags[:500],
                "categoryId":  "22",   # People & Blogs (works for coffee content)
            },
            "status": {
                "privacyStatus":           "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        file_size = os.path.getsize(video_path)
        headers   = {
            "Authorization":   f"Bearer {access_token}",
            "Content-Type":    "application/json; charset=UTF-8",
            "X-Upload-Content-Type":   "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        }

        init_resp = requests.post(
            f"{_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
            timeout=20,
        )
        upload_url = init_resp.headers.get("Location", "")
        if init_resp.status_code not in (200, 201) or not upload_url:
            return {
                "success": False, "video_id": "", "url": "",
                "error": safe(f"No upload URL: HTTP {init_resp.status_code}"),
            }

        offset = 0
        attempts = 0
        resumes = 0
        last = "upload_failed"
        while attempts < _UPLOAD_ATTEMPTS and resumes <= _UPLOAD_RESUMES:
            with open(video_path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
            if not chunk and offset < file_size:
                last = "upload_read_empty"
                break
            if offset >= file_size:
                put_headers = {
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{file_size}",
                }
                body = b""
            else:
                end = offset + len(chunk) - 1
                put_headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{end}/{file_size}",
                }
                body = chunk
            try:
                upload_resp = requests.put(upload_url, headers=put_headers, data=body, timeout=300)
            except requests.RequestException as exc:
                attempts += 1
                last = safe(f"transport: {type(exc).__name__}")
                continue
            if upload_resp.status_code in (200, 201):
                try:
                    data = upload_resp.json()
                except Exception:
                    data = {}
                video_id = data.get("id", "") if isinstance(data, dict) else ""
                if video_id:
                    return {
                        "success": True, "video_id": video_id,
                        "url": f"https://www.youtube.com/shorts/{video_id}", "error": None,
                    }
                return {"success": False, "video_id": "", "url": "", "error": "upload finished without a video id"}
            if upload_resp.status_code == 308:
                resumes += 1
                rng = upload_resp.headers.get("Range") or upload_resp.headers.get("range") or ""
                previous = offset
                try:
                    offset = int(str(rng).split("-")[-1]) + 1
                except ValueError:
                    offset = offset + len(chunk)
                if offset <= previous:
                    attempts += 1
                    last = "upload resume made no progress"
                continue
            if upload_resp.status_code in (429, 500, 502, 503, 504):
                attempts += 1
                last = f"HTTP {upload_resp.status_code}"
                continue
            return {
                "success": False, "video_id": "", "url": "",
                "error": safe(f"HTTP {upload_resp.status_code}"),
            }
        return {"success": False, "video_id": "", "url": "", "error": last}

    except Exception as e:
        logger.error("[youtube] Upload error: %s", type(e).__name__)
        return {"success": False, "video_id": "", "url": "", "error": type(e).__name__}


# ── Metadata builders ─────────────────────────────────────────────────────────

def _extract_title(content: dict) -> str:
    yt = content.get("yt_short")
    if isinstance(yt, dict):
        title = str(yt.get("title") or yt.get("hook") or "").strip()
        if title:
            return title[:100]

    reels = content.get("reels") or []
    if reels and isinstance(reels[0], dict):
        hook = str(reels[0].get("hook") or reels[0].get("hook_text") or "").strip()
        if hook:
            return hook[:100]
    return "Purity Beans — Pure Instant Coffee | No Chicory #Shorts"


def _extract_description(content: dict) -> str:
    yt = content.get("yt_short")
    if isinstance(yt, dict):
        desc = str(yt.get("description") or "").strip()
        if desc:
            return desc[:5000]
        # Construct from scenes if present
        scenes = yt.get("scenes") or []
        if isinstance(scenes, list) and scenes:
            spoken_lines = [s.get("spoken") for s in scenes if isinstance(s, dict) and s.get("spoken")]
            cta = str(yt.get("cta") or "Subscribe for pure coffee truths. Explore pure jars at https://p3online.in?utm_source=youtube&utm_medium=post&utm_campaign=202610")
            parts = [
                str(yt.get("hook") or ""),
                "\n".join(spoken_lines),
                cta,
                "\nPurity Beans — instant coffee in lead-free glass jars.",
                "Shop: https://p3online.in?utm_source=youtube&utm_medium=post&utm_campaign=202610",
            ]
            return "\n".join(p for p in parts if p)[:5000]

    reels = content.get("reels") or []
    if reels and isinstance(reels[0], dict):
        reel  = reels[0]
        parts = [
            str(reel.get("hook") or reel.get("hook_text") or ""),
            str(reel.get("script") or reel.get("body") or reel.get("caption") or ""),
            str(reel.get("cta") or ""),
            "",
            "Purity Beans — instant coffee in lead-free glass jars.",
            "Shop: https://p3online.in?utm_source=youtube&utm_medium=post&utm_campaign=202610",
        ]
        return "\n".join(p for p in parts if p)[:5000]
    return "Purity Beans — pure instant coffee. Zero chicory. Shop at https://p3online.in?utm_source=youtube&utm_medium=post&utm_campaign=202610"


def _build_tags(content: dict) -> list[str]:
    yt = content.get("yt_short")
    if isinstance(yt, dict) and isinstance(yt.get("tags"), list) and yt.get("tags"):
        return [str(t).lower()[:30] for t in yt["tags"]][:500]

    base = [
        "purity beans", "pure coffee", "instant coffee", "no chicory",
        "coffee india", "premium coffee", "coffee shorts", "coffee reels",
        "indiancoffee", "coffeelover",
    ]
    trend = content.get("strategy", {}).get("top_trend", "")
    if trend:
        base.append(trend.lower()[:30])
    return base


def _today(content: dict | None = None) -> str:
    if isinstance(content, dict) and content.get("date"):
        from content_generator.core.ist_dates import asset_date
        return asset_date(content)
    return today_ist().isoformat()


# ── CLI setup helper ──────────────────────────────────────────────────────────

def _run_oauth_setup() -> None:
    """
    Interactive OAuth setup — run once to get your YOUTUBE_REFRESH_TOKEN.
    Usage: python -m content_generator.publisher.youtube --setup
    """
    import json
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Run: pip install google-auth-oauthlib")
        return

    client_id     = input("Enter YOUTUBE_CLIENT_ID: ").strip()
    client_secret = input("Enter YOUTUBE_CLIENT_SECRET: ").strip()

    client_config = {
        "installed": {
            "client_id":                  client_id,
            "client_secret":              client_secret,
            "auth_uri":                   "https://accounts.google.com/o/oauth2/auth",
            "token_uri":                  "https://oauth2.googleapis.com/token",
            "redirect_uris":              ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow        = InstalledAppFlow.from_client_config(client_config, _SCOPES)
    credentials = flow.run_local_server(port=0)

    print("\n=== Copy these to GitHub Secrets ===")
    print(f"YOUTUBE_CLIENT_ID:      {client_id}")
    print(f"YOUTUBE_CLIENT_SECRET:  {client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN:  {credentials.refresh_token}")


if __name__ == "__main__":
    import sys
    if "--setup" in sys.argv:
        _run_oauth_setup()
