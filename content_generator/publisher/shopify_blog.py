"""
Shopify Blog publisher.

Publishing is off unless SHOPIFY_BLOG_ENABLED=true. The daily workflow turns it
on for the generate slot only. A post is written only when it is editor-approved
and passes every blog gate. Duplicate handles and titles are not attempted,
because Cowork may already have published the same article. Shopify errors and
missing secrets are warnings, not run failures.
"""
from __future__ import annotations
import base64
import glob as _glob
import html
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)
from config.api_versions import SHOPIFY_API_VERSION as _API_VERSION
_TIMEOUT = 40


def blog_enabled() -> bool:
    return os.getenv("SHOPIFY_BLOG_ENABLED", "false").strip().lower() == "true"


def is_configured() -> bool:
    from content_generator.analytics.revenue_attribution import normalize_shopify_domain
    return bool(normalize_shopify_domain(os.getenv("SHOPIFY_STORE_DOMAIN")) and os.getenv("SHOPIFY_ADMIN_TOKEN"))


def _admin(path: str, method: str = "GET", body: dict | None = None) -> dict | None:
    from content_generator.analytics.revenue_attribution import shopify_store_host
    domain = shopify_store_host()
    token = os.getenv("SHOPIFY_ADMIN_TOKEN")
    if not domain or not token:
        return None
    url = f"https://{domain}/admin/api/{_API_VERSION}/{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"X-Shopify-Access-Token": token,
                     "Content-Type": "application/json",
                     "User-Agent": "PurityBeans/1.0"},
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("[shopify_blog] %s %s failed: %s", method, path, e)
        return None


def _resolve_blog_id() -> str | None:
    explicit = os.getenv("SHOPIFY_BLOG_ID")
    if explicit:
        return explicit
    data = _admin("blogs.json")
    blogs = (data or {}).get("blogs") or []
    if blogs:
        return str(blogs[0].get("id"))
    logger.warning("[shopify_blog] No blog found on store")
    return None


def _hero_image_b64() -> str | None:
    creative = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    from content_generator.core.ist_dates import today_ist
    today = today_ist().isoformat()
    for pat in (f"carousel_slide_1_*{today}.jpg", f"*{today}.jpg"):
        hits = sorted(_glob.glob(os.path.join(creative, pat)))
        if hits:
            try:
                with open(hits[0], "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return None
    return None


def _article_body(blog: dict) -> str:
    """HTML for Shopify. `body` is plain text; legacy `body_html` is already markup."""
    from content_generator.core.blog_quality import normalize_text

    raw_html = normalize_text(str(blog.get("body_html") or "").strip())
    raw_body = normalize_text(str(blog.get("body") or "").strip())
    if raw_html:
        body = raw_html
    elif raw_body:
        paragraphs = [html.escape(part.strip()) for part in raw_body.split("\n\n") if part.strip()]
        body = "\n".join(f"<p>{part}</p>" for part in paragraphs)
    else:
        return ""
    intro = normalize_text(str(blog.get("intro") or blog.get("introduction") or ""))
    if intro and intro not in body:
        body = f"<p>{html.escape(intro)}</p>\n{body}"
    return body


def _skip(reason: str, **extra) -> dict:
    logger.warning("[shopify_blog] Skipping publish (%s); not attempted. The run is not failed.", reason)
    payload = {
        "success": False,
        "attempted": False,
        "skipped": True,
        "error": "not_attempted",
        "reason": reason,
    }
    payload.update(extra)
    return payload


def _missing_secrets() -> list[str]:
    return [
        key for key in ("SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_BLOG_ID")
        if not os.getenv(key, "").strip()
    ]


def _mark_path(on_date: str) -> str:
    root = os.getenv("BLOG_STATE_DIR", "output")
    return os.path.join(root, f"blog_published_{on_date}.json")


def _already_published(on_date: str) -> dict | None:
    path = _mark_path(on_date)
    if not os.path.exists(path):
        return None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("url") else None


def _remember_publish(on_date: str, payload: dict) -> None:
    path = _mark_path(on_date)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _titles_match(left: str, right: str) -> bool:
    return " ".join(str(left or "").split()).casefold() == " ".join(str(right or "").split()).casefold()


def _editor_approved(blog: dict) -> bool:
    score = blog.get("editorial_score")
    if not isinstance(score, dict) or score.get("overall") in (None, ""):
        return False
    try:
        overall = float(score["overall"])
    except (TypeError, ValueError):
        return False
    from content_generator.core.editorial_engine import get_current_pass_score
    verdict = str(score.get("verdict") or "").strip().upper()
    return overall >= get_current_pass_score() and verdict in {"PASS", "APPROVE"}


def _find_existing(blog_id: str, handle: str, title: str) -> tuple[str | None, dict | None]:
    """Return a duplicate kind, or lookup_failed when Shopify cannot be read."""
    if handle:
        data = _admin(
            f"blogs/{blog_id}/articles.json?handle={urllib.parse.quote(handle)}&fields=id,title,handle"
        )
        if data is None:
            return "lookup_failed", None
        articles = data.get("articles") or []
        if articles:
            return "duplicate_handle", articles[0]
    since = 0
    for _page in range(8):
        data = _admin(
            f"blogs/{blog_id}/articles.json?limit=250&since_id={since}&fields=id,title,handle"
        )
        if data is None:
            return "lookup_failed", None
        articles = data.get("articles") or []
        for art in articles:
            if _titles_match(art.get("title"), title):
                return "duplicate_title", art
        if len(articles) < 250:
            return None, None
        try:
            since = int(articles[-1]["id"])
        except (KeyError, TypeError, ValueError):
            return None, None
    return None, None


def post_content(content: dict, day: int = 0) -> dict:
    """Publish one approved post per IST day, from the generate slot only."""
    if not blog_enabled():
        logger.info("[shopify_blog] Disabled by SHOPIFY_BLOG_ENABLED (default=false); no Shopify write")
        return {"success": False, "error": "blog_disabled"}

    slot = os.getenv("FORCE_SLOT", "").strip()
    if slot and slot != "generate":
        return _skip("wrong_slot", slot=slot)

    from content_generator.core.blog_quality import assess, normalize_blog_piece
    from content_generator.core.ist_dates import today_ist
    from content_generator.core.schema_validation import BlogSchema, validate_or_fail

    blog = normalize_blog_piece(dict(content.get("blog_post") or {}))
    title = str(blog.get("title") or "").strip()
    body = _article_body(blog)
    if not title or not body:
        logger.warning("[shopify_blog] Blog enabled but generation produced no blog content")
        return {"success": False, "attempted": False, "skipped": True, "error": "no_blog_content"}

    on_date = today_ist().isoformat()
    prior = _already_published(on_date)
    if prior:
        logger.warning("[shopify_blog] Already published today (%s); not attempted", prior.get("url"))
        return _skip("already_published_today", url=prior.get("url") or "")

    if str(blog.get("hold_reason") or "").strip():
        logger.error("[blog] HELD blog_post — not publishing: %s", blog["hold_reason"])
        return _skip("held", hold_reason=str(blog["hold_reason"]))

    if not _editor_approved(blog):
        return _skip("not_editor_approved")

    defects = assess(blog, on_date=on_date)
    try:
        validate_or_fail(BlogSchema, blog)
    except Exception as exc:
        defects = [*defects, str(exc)[:240]]
    if defects:
        logger.warning("[shopify_blog] Refusing to write; blog failed quality checks: %s", defects[0])
        return _skip("blog_quality", issues=defects[:8])

    missing = _missing_secrets()
    if missing:
        logger.warning("[shopify_blog] Missing Shopify secrets (%s); skipping publish", ", ".join(missing))
        return _skip("missing_secrets", missing=missing)

    blog_id = os.getenv("SHOPIFY_BLOG_ID", "").strip() or _resolve_blog_id()
    if not blog_id:
        logger.warning("[shopify_blog] No Shopify blog id; skipping publish")
        return _skip("missing_secrets", missing=["SHOPIFY_BLOG_ID"])

    website = os.getenv("WEBSITE_URL", "https://p3online.in").rstrip("/")
    if "p3online.in" not in body:
        body += f'\n<p>Explore Purity Beans: <a href="{html.escape(website, quote=True)}">{html.escape(website)}</a></p>'

    handle = str(blog.get("slug") or "").strip()
    kind, existing = _find_existing(blog_id, handle, title)
    if kind == "lookup_failed":
        logger.warning("[shopify_blog] Shopify duplicate lookup failed; skipping publish")
        return _skip("shopify_error", detail="duplicate lookup failed")
    if kind in {"duplicate_handle", "duplicate_title"}:
        logger.warning("[shopify_blog] %s already exists (%s); not attempted", kind, handle or title)
        return _skip(kind, handle=handle, title=title)

    tags = blog.get("tags")
    if isinstance(tags, list):
        tags = ", ".join(str(item) for item in tags)
    article = {
        "title": title,
        "author": str(blog.get("author") or "Purity Beans"),
        "body_html": body,
        "tags": str(tags or "coffee, instant coffee, purity beans"),
        "published": True,
        "summary_html": str(blog.get("meta_description") or "")[:320],
    }
    if handle:
        article["handle"] = handle
    hero = _hero_image_b64()
    if hero:
        article["image"] = {"attachment": hero, "alt": str(blog.get("image_alt") or title)}

    resp = _admin(f"blogs/{blog_id}/articles.json", method="POST", body={"article": article})
    art = (resp or {}).get("article") or {}
    if not art.get("id"):
        detail = (resp or {}).get("errors", "publish_failed")
        logger.warning("[shopify_blog] Shopify error, skipping publish without failing the run: %s", detail)
        return _skip("shopify_error", detail=str(detail)[:300])

    public_handle = str(art.get("handle") or handle)
    url = f"{website}/blogs/news/{public_handle}" if public_handle else ""
    logger.info("[shopify_blog] Published article URL: %s (id=%s)", url, art["id"])
    _remember_publish(on_date, {"url": url, "article_id": str(art["id"]), "handle": public_handle, "title": title})
    return {"success": True, "attempted": True, "article_id": str(art["id"]), "url": url, "error": None}
