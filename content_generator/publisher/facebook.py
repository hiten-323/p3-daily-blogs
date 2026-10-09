
"""
Facebook auto-publisher — posts to Facebook Page via Graph API.

Uses the same Meta App as Instagram (shared access token).

Required secrets:
    FACEBOOK_PAGE_ID           — Your Facebook Page ID
                                 Find: facebook.com/your-page → About → Page ID
                                 Or: Graph API Explorer → /me/accounts → find your page id
    FACEBOOK_PAGE_ACCESS_TOKEN — Long-lived Page Access Token
                                 Same token as INSTAGRAM_ACCESS_TOKEN if your IG is
                                 connected to this Facebook Page.
                                 Or set a separate FACEBOOK_PAGE_ACCESS_TOKEN secret.

What gets posted:
    - LinkedIn post text (repurposed) + carousel image
    - Hashtags adapted for Facebook (fewer, broader)
    - Link to p3online.in/shop (Shopify store)

Token tip:
    If you already set INSTAGRAM_ACCESS_TOKEN and both IG + FB are on the same
    Meta App, you can reuse it: FACEBOOK_PAGE_ACCESS_TOKEN = same value.
"""
from __future__ import annotations
from config.api_versions import META_GRAPH_BASE
import logging
import os

logger = logging.getLogger(__name__)

_GRAPH_API = META_GRAPH_BASE


def is_configured() -> bool:
    return bool(os.getenv("FACEBOOK_PAGE_ID")) and bool(
        os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN")
    )


def resolve_page_access_token(page_id: str, candidate_token: str) -> str:
    """
    Ensure the token used for Facebook Page publishing is a Page-scoped Access Token.
    If the supplied candidate_token is a User Access Token with pages_manage_posts,
    exchange it via GET /{page_id}?fields=access_token.
    Falls back to INSTAGRAM_ACCESS_TOKEN if it is already a Page token.
    """
    if not page_id or not candidate_token:
        return candidate_token

    try:
        import requests
        resp = requests.get(
            f"{_GRAPH_API}/{page_id}",
            params={"fields": "access_token"},
            headers={"Authorization": f"Bearer {candidate_token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            resolved = resp.json().get("access_token")
            if resolved:
                logger.info("[facebook] Resolved Page Access Token from Page query")
                return resolved
    except Exception as exc:
        logger.debug("[facebook] Page token resolution failed: %s", exc)

    try:
        import requests
        resp = requests.get(
            f"{_GRAPH_API}/me/accounts",
            headers={"Authorization": f"Bearer {candidate_token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            for item in resp.json().get("data", []):
                if str(item.get("id")) == str(page_id) and item.get("access_token"):
                    logger.info("[facebook] Resolved Page Access Token from /me/accounts")
                    return item["access_token"]
    except Exception as exc:
        logger.debug("[facebook] /me/accounts lookup failed: %s", exc)

    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if ig_token and ig_token != candidate_token:
        try:
            import requests
            resp = requests.get(
                f"{_GRAPH_API}/{page_id}",
                params={"fields": "access_token"},
                headers={"Authorization": f"Bearer {ig_token}"},
                timeout=15,
            )
            if resp.status_code == 200:
                resolved = resp.json().get("access_token")
                if resolved:
                    logger.info("[facebook] Resolved Page Access Token via INSTAGRAM_ACCESS_TOKEN")
                    return resolved
        except Exception:
            pass

    return candidate_token


def post_content(content: dict, day: int = 0,
                 preferred_image: str | None = None,
                 message_override: str | None = None) -> dict:
    """
    Post today's content to Facebook Page.

    preferred_image/message_override let the slot scheduler mirror the
    Instagram post exactly (same image, same caption, same time).

    Returns:
        {"success": bool, "post_id": str, "url": str, "error": str|None}
    """
    if not is_configured():
        logger.info("[facebook] Not configured — FACEBOOK_PAGE_ID or token missing")
        return {"success": False, "post_id": "", "url": "", "error": "not_configured"}

    from content_generator.publisher.prepublish_gate import authorize_publish
    gate = authorize_publish(content, "facebook")
    if not gate["allowed"]:
        logger.warning("[facebook] Pre-publish gate blocked content: %s", gate["reason"])
        return {"success": False, "post_id": "", "url": "", "error": "prepublish_gate:" + gate["reason"], "gate": gate}


    page_id = os.getenv("FACEBOOK_PAGE_ID", "")
    raw_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    token = resolve_page_access_token(page_id, raw_token)
    message = message_override or _build_message(content)
    link    = os.getenv("WEBSITE_URL", "https://p3online.in")

    # Find an image to attach
    image_path = preferred_image or _find_image(content)

    result = _post_to_page(page_id, token, message, link, image_path)

    if result["success"]:
        logger.info("[facebook] Day %d posted | id=%s", day, result["post_id"])
    else:
        # A dead page token must not look like a fatal publish. Instagram is
        # the slot that fails the run; Facebook is a mirror.
        logger.warning("[facebook] Day %d failed: %s", day, result["error"])

    return result


def _build_message(content: dict) -> str:
    """Build Facebook post text from content."""
    fb = content.get("facebook_post")
    if isinstance(fb, dict):
        parts = [
            str(fb.get("hook") or "").strip(),
            str(fb.get("body") or "").strip(),
            str(fb.get("community_question") or "").strip(),
            str(fb.get("cta") or "").strip(),
            str(fb.get("hashtags") or "").strip(),
        ]
        text = "\n\n".join(p for p in parts if p)
        if text:
            return text[:63206]
    elif isinstance(fb, str) and fb.strip():
        return fb.strip()[:63206]

    # Fail closed: never publish another platform's copy or generic filler.
    return ""


def _find_image(content: dict) -> str | None:
    """Find the best image for Facebook post."""
    import glob as _glob

    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    today        = _today()

    patterns = [
        os.path.join(creative_dir, f"facebook_post_*{today}.jpg"),
        os.path.join(creative_dir, f"instagram_post_*{today}.jpg"),
        os.path.join(creative_dir, f"carousel_slide_1_{today}.jpg"),
        os.path.join(creative_dir, f"carousel_cover_{today}.jpg"),
        os.path.join(creative_dir, f"*_{today}.jpg"),
    ]
    for pat in patterns:
        files = sorted(_glob.glob(pat), reverse=True)
        if files:
            return files[0]
    return None


def _post_to_page(
    page_id: str, token: str, message: str,
    link: str, image_path: str | None,
) -> dict:
    """Post text + optional image to Facebook Page."""
    try:
        import requests
    except ImportError:
        return {"success": False, "post_id": "", "url": "", "error": "requests_not_installed"}

    try:
        if image_path and os.path.exists(image_path):
            from content_generator.creative.jar_provenance import verify_jar_provenance
            prov = verify_jar_provenance(image_path)
            if not prov.get("verified"):
                logger.error("[facebook] Refusing to post unverified jar image: %s (%s)", image_path, prov.get("reason"))
                return {"success": False, "post_id": "", "url": "", "error": f"real_jar_unverified: {prov.get('reason')}"}

            # Photo post
            with open(image_path, "rb") as f:
                resp = requests.post(
                    f"{_GRAPH_API}/{page_id}/photos",
                    data={"message": message},
                    files={"source": f},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60,
                )
        else:
            # Link post (text + link preview)
            resp = requests.post(
                f"{_GRAPH_API}/{page_id}/feed",
                params={"message": message, "link": link},
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )

        data    = resp.json()
        post_id = data.get("post_id") or data.get("id", "")
        if post_id:
            url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
            return {"success": True, "post_id": post_id, "url": url, "error": None}
        else:
            err = data.get("error", {}).get("message", str(data)[:200])
            logger.warning("[facebook] Post failed: %s", err)
            return {"success": False, "post_id": "", "url": "", "error": err}

    except Exception as e:
        logger.warning("[facebook] Request error: %s", e)
        return {"success": False, "post_id": "", "url": "", "error": str(e)}


def _today() -> str:
    from content_generator.core.ist_dates import today_ist
    return today_ist().isoformat()
