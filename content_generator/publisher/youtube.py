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
    from content_generator.publisher.prepublish_gate import authorize_publish
    gate = authorize_publish(content, "youtube")
    if not gate["allowed"]:
        logger.warning("[youtube] Pre-publish gate blocked content: %s", gate["reason"])
        return {"success": False, "video_id": "", "url": "", "error": "prepublish_gate:" + gate["reason"], "gate": gate}

    from content_generator.publisher.dispatcher import editorial_disposition, not_attempted_result
    state = editorial_disposition(content, "yt_short")
    if state != "approved":
        logger.info("[youtube] Skipping yt_short — %s; not attempted", state)
        return not_attempted_result("yt_short", state)

    if not is_configured():
        logger.info("[youtube] Not configured — YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN missing")
        return {"success": False, "video_id": "", "url": "", "error": "not_configured"}

    # Get fresh access token
    access_token = _refresh_access_token()
    if not access_token:
        return {"success": False, "video_id": "", "url": "", "error": "token_refresh_failed"}

    # Find video file
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
    tags        = _build_tags(content)

    result = _upload_video(access_token, video_path, title, description, tags)

    if result["success"]:
        logger.info("[youtube] Day %d uploaded | id=%s | url=%s", day, result["video_id"], result["url"])
    else:
        logger.error("[youtube] Day %d failed: %s", day, result["error"])

    return result


# ── Token management ──────────────────────────────────────────────────────────

def _refresh_access_token() -> str | None:
    """Exchange refresh token for a fresh access token."""
    try:
        import requests
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "client_id":     os.getenv("YOUTUBE_CLIENT_ID", ""),
                "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
                "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        logger.warning("[youtube] Token refresh failed: %s", data.get("error_description", data))
        return None
    except Exception as e:
        logger.error("[youtube] Token refresh error: %s", e)
        return None


# ── Video source ──────────────────────────────────────────────────────────────

def _find_video(content: dict) -> str | None:
    """Look for a rendered .mp4 Short in output/creative/."""
    import glob as _glob
    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    today        = _today()

    patterns = [
        os.path.join(creative_dir, f"reel_*_{today}.mp4"),
        os.path.join(creative_dir, f"short_*_{today}.mp4"),
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
    """Upload video to YouTube with Shorts metadata."""
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

        # Step 1: Initialize resumable upload
        init_resp = requests.post(
            f"{_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
            timeout=20,
        )
        upload_url = init_resp.headers.get("Location", "")
        if not upload_url:
            return {
                "success": False, "video_id": "", "url": "",
                "error": f"No upload URL: {init_resp.status_code} {init_resp.text[:200]}"
            }

        # Step 2: Upload video bytes
        with open(video_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Type":   "video/mp4",
                    "Content-Length": str(file_size),
                },
                data=f,
                timeout=300,   # large file upload timeout
            )

        data     = upload_resp.json()
        video_id = data.get("id", "")
        if video_id:
            url = f"https://www.youtube.com/shorts/{video_id}"
            return {"success": True, "video_id": video_id, "url": url, "error": None}
        else:
            err = str(data.get("error", {}).get("message", data))[:300]
            return {"success": False, "video_id": "", "url": "", "error": err}

    except Exception as e:
        logger.error("[youtube] Upload error: %s", e)
        return {"success": False, "video_id": "", "url": "", "error": str(e)}


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
    return "Purity Beans — 100% Pure Instant Coffee | No Chicory #Shorts"


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
            cta = str(yt.get("cta") or "Subscribe for pure coffee truths. Explore 100% pure jars at https://p3online.in")
            parts = [
                str(yt.get("hook") or ""),
                "\n".join(spoken_lines),
                cta,
                "\nPurity Beans — India's purest instant coffee. Rs 18/cup. Zero chicory.",
                "Shop: https://p3online.in",
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
            "Purity Beans — India's purest instant coffee. Rs 18/cup. Zero chicory.",
            "Shop: https://p3online.in",
        ]
        return "\n".join(p for p in parts if p)[:5000]
    return "Purity Beans — 100% pure instant coffee. Zero chicory. Shop at https://p3online.in"


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


def _today() -> str:
    import datetime
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
