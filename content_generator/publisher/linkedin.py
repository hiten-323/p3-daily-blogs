"""
LinkedIn auto-publisher — posts text + image to LinkedIn daily.

Uses LinkedIn's REST Posts API (2024).

Required secrets (GitHub Actions):
    LI_API_ACCESS    — LinkedIn OAuth 2.0 access token
                       Get from: linkedin.com/developers → your app → OAuth → Access Token
    LI_AUTHOR_URN    — LinkedIn URN for the author
                       Person:  urn:li:person:XXXXXXXX
                       Company: urn:li:organization:XXXXXXXX
                       Get your person URN: https://www.linkedin.com/in/me/
                       (inspect network tab → /me?projection=(id) → copy id → urn:li:person:{id})

Optional:
    LI_API_VERSION   — API version header (default: 202406)

What gets posted:
    - linkedin_post text from the daily content output
    - If a carousel/cover image was generated, it's attached as an image

Token refresh:
    LinkedIn tokens expire in 60 days. Use a Service App (not 3-legged OAuth)
    for long-lived tokens, or set a calendar reminder to refresh monthly.
    See: https://learn.microsoft.com/en-us/linkedin/shared/authentication/
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_API_BASE    = "https://api.linkedin.com/rest"
_API_VERSION = os.getenv("LI_API_VERSION", "202506")   # Use latest monthly version; override via LI_API_VERSION secret
_cached_token: str | None = None


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str | None:
    """Exchange a 365-day LinkedIn refresh token for a fresh access token."""
    import json
    import urllib.parse
    import urllib.request
    url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "PurityBeans/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            tok = payload.get("access_token")
            if tok:
                logger.info("[linkedin] Successfully obtained fresh access token via refresh token")
                return tok
    except Exception as e:
        logger.warning("[linkedin] Could not refresh access token: %s", e)
    return None


def get_access_token(force_refresh: bool = False) -> str:
    """Return active LinkedIn access token, refreshing if refresh credentials exist."""
    global _cached_token
    if not force_refresh and _cached_token:
        return _cached_token

    client_id     = os.getenv("LI_CLIENT_ID", "").strip()
    client_secret = os.getenv("LI_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("LI_REFRESH_TOKEN", "").strip()

    if client_id and client_secret and refresh_token:
        tok = refresh_access_token(client_id, client_secret, refresh_token)
        if tok:
            _cached_token = tok
            return tok

    explicit = os.getenv("LI_API_ACCESS", "").strip()
    if explicit:
        return explicit

    return ""


def is_configured() -> bool:
    has_token = bool(os.getenv("LI_API_ACCESS")) or (
        bool(os.getenv("LI_CLIENT_ID")) and bool(os.getenv("LI_CLIENT_SECRET")) and bool(os.getenv("LI_REFRESH_TOKEN"))
    )
    return has_token and bool(os.getenv("LI_AUTHOR_URN"))



def post_content(content: dict, day: int = 0) -> dict:
    """
    Post today's LinkedIn content.

    Args:
        content: Daily content dict with "linkedin_post" key
        day:     Day number (used in logs)

    Returns:
        {"success": bool, "post_id": str, "url": str, "error": str|None}
    """
    from content_generator.publisher.dispatcher import editorial_disposition, not_attempted_result
    state = editorial_disposition(content, "linkedin_post")
    if state != "approved":
        logger.info("[linkedin] Skipping linkedin_post — %s; not attempted", state)
        return not_attempted_result("linkedin_post", state)

    if not is_configured():
        logger.info("[linkedin] Not configured — LI_API_ACCESS or LI_AUTHOR_URN missing")
        return {"success": False, "post_id": "", "url": "", "error": "not_configured"}

    post_text = _extract_post_text(content)
    if not post_text:
        logger.warning("[linkedin] No linkedin_post in content — skipping")
        return {"success": False, "post_id": "", "url": "", "error": "no_content"}

    # Try to attach an image (carousel cover or first reel thumbnail)
    image_path = _find_image(content)
    image_urn  = None
    if image_path:
        image_urn = _upload_image(image_path)
        if not image_urn:
            logger.info("[linkedin] Image upload failed — posting text only")

    result = _create_post(post_text, image_urn)

    if result["success"]:
        logger.info("[linkedin] Day %d posted | id=%s", day, result["post_id"])
    else:
        logger.error("[linkedin] Day %d post failed: %s", day, result["error"])

    return result


def _extract_post_text(content: dict) -> str:
    """Extract complete, beautifully formatted LinkedIn post text from content dict."""
    li = content.get("linkedin_post") or {}
    if isinstance(li, str):
        return li[:3000]

    if isinstance(li, dict) and (li.get("body") or li.get("hook")):
        parts = []
        hook = str(li.get("hook") or "").strip()
        body = str(li.get("body") or "").strip()
        bridge = str(li.get("brand_bridge") or "").strip()
        question = str(li.get("closing_question") or "").strip()
        cta = str(li.get("cta") or "").strip()
        hashtags = str(li.get("hashtags") or "").strip()

        if hook:
            parts.append(hook)
        if body:
            parts.append(body)
        if bridge and bridge not in body:
            parts.append(bridge)
        if question and question not in body:
            parts.append(question)
        if cta and cta not in body:
            parts.append(cta)
        if hashtags and hashtags not in body:
            parts.append(hashtags)

        full_post = "\n\n".join(parts)
        if len(full_post) <= 3000:
            return full_post

        # If over LinkedIn's 3000-character cap, preserve hook, cta and hashtags while cleanly trimming body
        essential_parts = [p for p in (bridge, question, cta, hashtags) if p and p not in body]
        trailer = "\n\n".join(essential_parts)
        available_body = 3000 - len(hook) - len(trailer) - 10
        if available_body > 100:
            trimmed_body = body[:available_body].rsplit(" ", 1)[0] + "..."
            trimmed_post = "\n\n".join(p for p in [hook, trimmed_body, trailer] if p)
            return trimmed_post[:3000]
        return full_post[:3000]

    text_fields = ["text", "content", "caption", "post"]
    for f in text_fields:
        val = li.get(f, "")
        if val:
            return str(val)[:3000]

    # Fallback: use first reel hook + CTA
    reels = content.get("reels") or []
    if reels:
        reel = reels[0]
        hook = reel.get("hook", "")
        cta  = reel.get("cta", "")
        return f"{hook}\n\n{cta}\n\n#PurityBeans #PureCoffee #InstantCoffee"[:3000]

    return ""


def _find_image(content: dict) -> str | None:
    """Find a generated image file to attach."""
    import os, glob as _glob

    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

    # Look for carousel cover first, then any generated image — today's only
    # (creative files persist 7 days in the repo for the publish slots)
    from content_generator.core.ist_dates import today_ist
    today = today_ist().isoformat()
    patterns = [
        os.path.join(creative_dir, f"carousel_slide_1_*{today}.jpg"),
        os.path.join(creative_dir, f"carousel_cover_*{today}.jpg"),
        os.path.join(creative_dir, f"*{today}.jpg"),
    ]
    for pat in patterns:
        files = sorted(_glob.glob(pat), reverse=True)
        if files:
            return files[0]
    return None


def _upload_image(image_path: str) -> str | None:
    """
    Upload an image to LinkedIn and return its asset URN.
    Two-step: initialize upload → upload bytes → return URN.
    """
    try:
        import requests
    except ImportError:
        return None

    token      = get_access_token()
    author_urn = os.getenv("LI_AUTHOR_URN", "")
    headers    = {
        "Authorization":  f"Bearer {token}",
        "LinkedIn-Version": _API_VERSION,
        "Content-Type":   "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Step 1: Initialize upload
    try:
        init_resp = requests.post(
            f"{_API_BASE}/images?action=initializeUpload",
            headers=headers,
            json={"initializeUploadRequest": {"owner": author_urn}},
            timeout=15,
        )
        if init_resp.status_code == 401 and os.getenv("LI_REFRESH_TOKEN"):
            logger.info("[linkedin] Token expired during image init — refreshing token")
            token = get_access_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            init_resp = requests.post(
                f"{_API_BASE}/images?action=initializeUpload",
                headers=headers,
                json={"initializeUploadRequest": {"owner": author_urn}},
                timeout=15,
            )

        if init_resp.status_code != 200:
            logger.debug("[linkedin] Image init failed: %d %s", init_resp.status_code, init_resp.text[:200])
            return None

        data       = init_resp.json().get("value", {})
        upload_url = data.get("uploadUrl", "")
        image_urn  = data.get("image", "")

        if not upload_url or not image_urn:
            return None

    except Exception as e:
        logger.debug("[linkedin] Image init error: %s", e)
        return None

    # Step 2: Upload the image bytes
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        upload_resp = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
            data=image_bytes,
            timeout=60,
        )
        if upload_resp.status_code in (200, 201):
            logger.info("[linkedin] Image uploaded: %s", image_urn)
            return image_urn
        else:
            logger.debug("[linkedin] Image upload failed: %d", upload_resp.status_code)
            return None

    except Exception as e:
        logger.debug("[linkedin] Image upload error: %s", e)
        return None


def _create_post(text: str, image_urn: str | None) -> dict:
    """Create the LinkedIn post via REST API."""
    try:
        import requests
    except ImportError:
        return {"success": False, "post_id": "", "url": "", "error": "requests_not_installed"}

    token      = get_access_token()
    author_urn = os.getenv("LI_AUTHOR_URN", "")

    headers = {
        "Authorization":  f"Bearer {token}",
        "LinkedIn-Version": _API_VERSION,
        "Content-Type":   "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    payload: dict = {
        "author":       author_urn,
        "commentary":   text,
        "visibility":   "PUBLIC",
        "distribution": {
            "feedDistribution":             "MAIN_FEED",
            "targetEntities":               [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState":              "PUBLISHED",
        "isReshareDisabledByAuthor":   False,
    }

    if image_urn:
        payload["content"] = {
            "media": {
                "altText": "Purity Beans — 100% Pure Instant Coffee",
                "id":      image_urn,
            }
        }

    try:
        resp = requests.post(f"{_API_BASE}/posts", headers=headers, json=payload, timeout=20)
        if resp.status_code == 401 and os.getenv("LI_REFRESH_TOKEN"):
            logger.info("[linkedin] Token expired during post create — refreshing token")
            token = get_access_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = requests.post(f"{_API_BASE}/posts", headers=headers, json=payload, timeout=20)

        if resp.status_code in (200, 201):
            post_id = resp.headers.get("x-restli-id", "") or resp.json().get("id", "")
            url     = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""
            return {"success": True, "post_id": post_id, "url": url, "error": None}
        else:
            err = resp.text[:300]
            logger.warning("[linkedin] Post failed %d: %s", resp.status_code, err)
            return {"success": False, "post_id": "", "url": "", "error": f"HTTP {resp.status_code}: {err}"}

    except Exception as e:
        logger.error("[linkedin] Post exception: %s", e)
        return {"success": False, "post_id": "", "url": "", "error": str(e)}
