
"""
Instagram auto-publisher — posts carousels and single images via Meta Graph API.

Prerequisites (one-time setup):
  1. Instagram Business or Creator account
  2. Facebook Page connected to that Instagram account
  3. Meta App with instagram_basic + instagram_content_publish permissions
  4. A long-lived Page Access Token (valid 60 days, renewable)

Required secrets:
    INSTAGRAM_ACCOUNT_ID     — Your Instagram Business Account ID
                               Find: Graph API Explorer → /me/accounts → instagram_business_account
    INSTAGRAM_ACCESS_TOKEN   — Long-lived Page Access Token with publishing permissions
                               Generate: developers.facebook.com → Tools → Access Token Debugger

What gets posted:
    - Carousel (multi-image): all generated carousel slide images
    - Single image: if only one image available (carousel cover)
    - Caption: from carousel.caption or reel hook

Note on Reels:
    Instagram Reels require an actual video file. Since the engine generates
    scripts (not rendered video), Reels auto-posting is skipped here.
    Add RUNWAY_API_KEY to enable video generation → Reels posting.

API flow for carousel:
    1. POST /{ig-user-id}/media for each image → get container_id
    2. POST /{ig-user-id}/media with carousel children → get carousel_container_id
    3. POST /{ig-user-id}/media_publish with carousel_container_id → published!
"""
from __future__ import annotations
from config.api_versions import META_GRAPH_BASE
import logging
import os
import re

logger = logging.getLogger(__name__)

_HASHTAG = re.compile(r"#[\w]+", re.UNICODE)
_CAPTION_LIMIT = 2200
_HASHTAG_TARGET = 15
_HASHTAG_MIN = 5
_HASHTAG_HARD_MAX = 30
# Instagram feed accepts 4:5 (0.8) through 1.91:1. 9:16 reels are ~0.5625.
_FEED_MIN_RATIO = 4 / 5
_FEED_MAX_RATIO = 1.91

_GRAPH_API = META_GRAPH_BASE


def is_configured() -> bool:
    return bool(os.getenv("INSTAGRAM_ACCOUNT_ID")) and bool(os.getenv("INSTAGRAM_ACCESS_TOKEN"))


def _find_reel_video(day: int) -> str | None:
    """Return only today's rendered MP4 for this content day; never reuse a stale reel."""
    import glob

    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    from content_generator.core.ist_dates import today_ist

    today = today_ist().isoformat()
    expected = os.path.join(creative_dir, f"reel_1_video_day{day}_{today}.mp4")
    if os.path.isfile(expected) and os.path.getsize(expected) > 10_000:
        return expected

    # Accept the canonical label only, and still require both the current date
    # and day number in the filename so an older video can never be reposted.
    matches = glob.glob(os.path.join(creative_dir, f"reel_1_video_day{day}_{today}.mp4"))
    return next((p for p in matches if os.path.isfile(p) and os.path.getsize(p) > 10_000), None)


def post_content(content: dict, day: int = 0) -> dict:
    """
    Post today's content to Instagram.

    Tries carousel first (if multiple images). Falls back to single image post.

    Returns:
        {"success": bool, "media_id": str, "permalink": str, "error": str|None}
    """
    if not is_configured():
        logger.info("[instagram] Not configured — INSTAGRAM_ACCOUNT_ID or INSTAGRAM_ACCESS_TOKEN missing")
        return {"success": False, "media_id": "", "permalink": "", "error": "not_configured"}

    from content_generator.publisher.prepublish_gate import authorize_publish
    gate = authorize_publish(content, "instagram")
    if not gate["allowed"]:
        logger.warning("[instagram] Pre-publish gate blocked content: %s", gate["reason"])
        return {"success": False, "media_id": "", "permalink": "", "error": "prepublish_gate:" + gate["reason"], "gate": gate}


    caption = _extract_caption(content, day=day)

    # A rendered Reel is the preferred Instagram format when it exists. Upload
    # to public video hosting first because Meta requires a public video_url.
    # If upload or publishing fails, return that failure rather than silently
    # substituting a carousel or risking a duplicate after an ambiguous result.
    reel_video_path = _find_reel_video(day)
    if reel_video_path:
        from content_generator.publisher.video_host import upload_video

        video_url = upload_video(reel_video_path)
        if video_url:
            result = post_reel_video(video_url, caption)
            if result.get("success"):
                result["hashtags_used"] = " ".join(w for w in caption.split() if w.startswith("#"))
                result["format_used"] = "reel"
                result["reel_video_path"] = reel_video_path
                logger.info("[instagram] Day %d Reel published | id=%s", day, result.get("media_id"))
                return result
            logger.error("[instagram] Day %d rendered Reel failed to publish: %s", day, result.get("error"))
        else:
            direct_res = _post_reel_direct_binary(reel_video_path, caption)
            if direct_res.get("success"):
                direct_res["hashtags_used"] = " ".join(w for w in caption.split() if w.startswith("#"))
                direct_res["format_used"] = "reel"
                direct_res["reel_video_path"] = reel_video_path
                logger.info("[instagram] Day %d Reel published via direct binary upload | id=%s", day, direct_res.get("media_id"))
                return direct_res

        logger.warning(
            "[instagram] Reel video upload unavailable or failed for day %d. Falling back to editorial carousel.",
            day,
        )

    logger.warning("[instagram] No rendered Reel MP4 for day %d; Reel is not publishable. Checking feed-image fallback.", day)
    images  = _find_carousel_images(content)

    if not images:
        logger.warning("[instagram] No images found — skipping Instagram post")
        return {"success": False, "media_id": "", "permalink": "", "error": "no_images"}

    # Fail closed on broken, low-resolution, blank, or duplicate rendered assets.
    # This is technical QA; it does not replace human review for realism or brand taste.
    from content_generator.creative.rendered_asset_qa import audit_rendered_images
    visual_qa = audit_rendered_images(images[:10])
    if not visual_qa.get("ok"):
        logger.error("[instagram] Refusing to publish assets that failed visual QA: %s", visual_qa.get("issues"))
        return {
            "success": False,
            "media_id": "",
            "permalink": "",
            "error": "visual_qa_failed: " + "; ".join(visual_qa.get("issues", [])),
            "visual_qa": visual_qa,
        }

    from content_generator.creative.jar_provenance import verify_creative_suite
    prov_ok, prov_issues = verify_creative_suite(images[:10] if len(images) >= 2 else [images[0]])
    if not prov_ok:
        logger.error("[instagram] Refusing to publish unverified jar images: %s", prov_issues)
        return {"success": False, "media_id": "", "permalink": "", "error": f"real_jar_unverified: {'; '.join(prov_issues)}"}

    if len(images) >= 2:
        result = _post_carousel(images[:10], caption)   # Instagram max 10
    else:
        result = _post_single_image(images[0], caption)

    # Expose the exact tags posted so insights can attribute performance to them
    result["hashtags_used"] = " ".join(w for w in caption.split() if w.startswith("#"))

    if result["success"]:
        logger.info("[instagram] Day %d posted | id=%s", day, result["media_id"])
    else:
        logger.error("[instagram] Day %d failed: %s", day, result["error"])

    return result


# 25-tag fallback: 5 broad + 5 niche + 5 Indian + 5 discovery + 5 brand
_FALLBACK_HASHTAGS = (
    "#Coffee #CoffeeLover #InstantCoffee #MorningCoffee #CoffeeTime "
    "#PremiumCoffee #GlassJar #GourmetCoffee #PureCoffee #CoffeeCommunity "
    "#IndianCoffee #CoffeeIndia #MadeInIndia #IndianBrands #SupportIndianBrands "
    "#CoffeeAddict #CoffeeDaily #CoffeeGram #CoffeeCulture #CoffeeLife "
    "#PurityBeans #PurityBeansCoffee #NoChicory #BrewPure #PureCoffeeExperience"
)


def _unique_hashtags(*blobs: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        for tag in _HASHTAG.findall(blob or ""):
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(tag)
    return found


def _strip_hashtags(text: str) -> str:
    """Remove inline hashtags from caption body so they are not counted twice."""
    cleaned = _HASHTAG.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _choose_hashtags(piece: dict, day: int) -> list[str]:
    """Target 5-15 tags. Hard ceiling is Instagram's 30."""
    primary = ""
    try:
        from content_generator.analytics.hashtag_bank import select_hashtags
        primary = select_hashtags(day=day) or ""
    except Exception as e:
        logger.debug("[instagram] adaptive hashtags unavailable: %s", e)
    llm = piece.get("hashtags")
    if isinstance(llm, list):
        llm = " ".join(str(t) for t in llm)
    ordered = _unique_hashtags(primary, str(llm or ""))
    if len(ordered) < _HASHTAG_MIN:
        ordered = _unique_hashtags(" ".join(ordered), _FALLBACK_HASHTAGS)
    if len(ordered) > _HASHTAG_TARGET:
        ordered = ordered[:_HASHTAG_TARGET]
    return ordered[:_HASHTAG_HARD_MAX]


def _meaningful_piece(piece: dict) -> bool:
    if not isinstance(piece, dict) or not piece:
        return False
    for key in ("caption", "body", "hook", "hook_text", "title", "cta", "slides"):
        value = piece.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def _caption_piece(content: dict) -> dict | None:
    """
    The asset actually being posted.

    An empty carousel caption used to fall through to reel 1, whose caption
    already contained a full hashtag block. The publisher then appended another
    ~25 tags and blew past Instagram's limit of 30.
    """
    carousel = content.get("carousel") if isinstance(content.get("carousel"), dict) else {}
    if _meaningful_piece(carousel):
        return carousel
    ig = content.get("instagram_post") if isinstance(content.get("instagram_post"), dict) else {}
    if _meaningful_piece(ig):
        return ig
    reels = content.get("reels") or []
    if reels and isinstance(reels[0], dict) and reels[0]:
        return reels[0]
    return None


def _extract_caption(content: dict, day: int = 0) -> str:
    """
    Build the Instagram caption from the piece being posted:
    body + triggers + 5-15 hashtags, never more than 30, max 2200 characters.
    """
    piece = _caption_piece(content)
    if not piece:
        return _assemble_caption("Pure instant coffee. Zero chicory. 100% coffee.", {}, day)

    body = str(
        piece.get("caption") or piece.get("body") or piece.get("hook")
        or piece.get("hook_text") or piece.get("title") or ""
    ).strip()
    if not body:
        bits = [str(piece.get("title") or "").strip()]
        for slide in (piece.get("slides") or [])[:3]:
            if isinstance(slide, dict):
                bits.append(str(slide.get("heading") or "").strip())
        body = ". ".join(b for b in bits if b)
    cta = _strip_hashtags(str(piece.get("cta") or ""))
    if cta and cta.lower() not in body.lower():
        body = f"{body}\n\n{cta}"
    return _assemble_caption(body, piece, day)


def _assemble_caption(body: str, piece: dict, day: int = 0) -> str:
    """Triggers + capped hashtags. Inline tags in the body are stripped first."""
    body = _strip_hashtags(body)
    parts = [body]
    for key in ("comment_trigger", "save_trigger"):
        extra = _strip_hashtags(str(piece.get(key) or ""))
        if extra and extra.lower() not in body.lower():
            parts.append(extra)

    audio_rec = (piece.get("audio") or {}).get("recommendation")
    if audio_rec and "🎵" not in body and "audio" not in body.lower():
        parts.append(f"🎵 Audio: {audio_rec}")

    tags = _choose_hashtags(piece or {}, day)
    tag_line = " ".join(tags)
    caption_body = "\n\n".join(p for p in parts if p).strip()
    suffix = f"\n\n{tag_line}" if tag_line else ""
    if len(caption_body) + len(suffix) > _CAPTION_LIMIT:
        budget = _CAPTION_LIMIT - len(suffix)
        if budget < 40 and tags:
            while tags and len(" ".join(tags)) + 2 > _CAPTION_LIMIT - 40:
                tags.pop()
            tag_line = " ".join(tags)
            suffix = f"\n\n{tag_line}" if tag_line else ""
            budget = _CAPTION_LIMIT - len(suffix)
        caption_body = caption_body[:max(0, budget)].rsplit(" ", 1)[0].strip()
    full = f"{caption_body}{suffix}".strip()
    # Hard ceiling even if a trigger smuggled a tag back in.
    final_tags = _unique_hashtags(full)
    if len(final_tags) > _HASHTAG_HARD_MAX:
        keep = final_tags[:_HASHTAG_HARD_MAX]
        full = _strip_hashtags(full)
        full = f"{full}\n\n{' '.join(keep)}".strip()
    if len(full) > _CAPTION_LIMIT:
        full = full[:_CAPTION_LIMIT].rsplit(" ", 1)[0].strip()
    return full


def _find_carousel_images(content: dict) -> list[str]:
    """Find all carousel slide images generated today."""
    import glob as _glob

    creative_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))

    patterns = [
        "carousel_slide_*.jpg",
        "carousel_slide_*.png",
        "slide_*.jpg",
        "slide_*.png",
        "carousel_*.jpg",
        "carousel_*.png",
    ]

    from content_generator.core.ist_dates import today_ist
    today = today_ist().isoformat()

    images = []
    for pattern in patterns:
        images.extend(sorted(_glob.glob(os.path.join(creative_dir, pattern))))

    # Remove duplicates but preserve order; ONLY today's files —
    # creative images persist 7 days in the repo for the publish slots,
    # so without this filter we would post a mix of old days' slides.
    images = [p for p in dict.fromkeys(images) if today in os.path.basename(p)]

    # If no carousel slides found, look for feed post / instagram post images generated today
    if not images:
        single_patterns = [
            f"instagram_post_*{today}.jpg",
            f"instagram_post_*{today}.png",
            f"feed_post_*{today}.jpg",
            f"feed_post_*{today}.png",
        ]
        for sp in single_patterns:
            images.extend(sorted(_glob.glob(os.path.join(creative_dir, sp))))
        images = list(dict.fromkeys(images))

    logger.info("[instagram] CREATIVE_OUTPUT_DIR=%s", creative_dir)
    if not images:
        logger.info("[instagram] Images discovered: %s", images)
    else:
        logger.info("[instagram] Found %d images in %s", len(images), creative_dir)

    return images


def _post_single_image(image_path: str, caption: str) -> dict:
    """Upload and publish a single image to Instagram."""
    try:
        import requests
    except ImportError:
        return {"success": False, "media_id": "", "permalink": "", "error": "requests_not_installed"}

    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token   = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    # 1. Upload image to get a hosting URL — Instagram requires a publicly accessible URL.
    # We upload to a temporary image host (imgur or use Facebook's own CDN via page photo).
    image_url = _upload_to_public_url(image_path)
    if not image_url:
        return {"success": False, "media_id": "", "permalink": "", "error": "image_upload_failed"}

    try:
        from content_generator.publisher.meta_graph import (
            ContainerNotReady, MetaRequestError, graph_request, wait_for_container,
        )
        # 2. Create media container (+ product tags if IG Shopping is set up)
        params = {
            "image_url":    image_url,
            "caption":      caption,
            "access_token": token,
        }
        try:
            from content_generator.publisher.product_tags import build_image_product_tags
            tags = build_image_product_tags(caption)
            if tags:
                params["product_tags"] = tags
        except Exception as e:
            logger.debug("[instagram] product tagging skipped: %s", e)
        container_data = graph_request(
            "POST", f"{_GRAPH_API}/{acct_id}/media", params, timeout=30,
        )
        container_id = container_data.get("id", "")
        if not container_id:
            err = container_data.get("error", {}).get("message", str(container_data))
            return {"success": False, "media_id": "", "permalink": "", "error": err}

        # 3. Wait until FINISHED. ERROR and timeout must not publish.
        wait_for_container(container_id, token)

        # 4. Publish
        return _publish_container(container_id, acct_id, token)

    except (ContainerNotReady, MetaRequestError) as e:
        logger.error("[instagram] Single post not published: %s", e)
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}
    except Exception as e:
        logger.error("[instagram] Single post error: %s", e)
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}


def _post_carousel(image_paths: list[str], caption: str) -> dict:
    """Upload and publish a carousel (multi-image) post to Instagram."""
    try:
        import requests
    except ImportError:
        return {"success": False, "media_id": "", "permalink": "", "error": "requests_not_installed"}

    from content_generator.publisher.meta_graph import (
        ContainerNotReady, MetaRequestError, graph_request, wait_for_container,
    )

    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token   = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    # 1. Every slide must become a child. A partial carousel used to publish
    #    the one child that succeeded — that container is an item, not a post,
    #    and it has no caption. Abort and fall back to a real single-image post.
    children = []
    ok_paths = []
    failed = []
    for path in image_paths:
        url = _upload_to_public_url(path)
        if not url:
            failed.append(os.path.basename(path))
            logger.warning("[instagram] carousel child upload failed: %s", path)
            continue
        try:
            resp_json = graph_request(
                "POST",
                f"{_GRAPH_API}/{acct_id}/media",
                {"image_url": url, "is_carousel_item": True, "access_token": token},
                timeout=30,
            )
            logger.info("[instagram] carousel item upload response: %s", resp_json)
            cid = resp_json.get("id", "")
            if cid:
                children.append(cid)
                ok_paths.append(path)
            else:
                failed.append(os.path.basename(path))
                logger.warning("[instagram] carousel child rejected: %s", resp_json)
        except MetaRequestError as e:
            failed.append(os.path.basename(path))
            logger.warning("[instagram] carousel child failed: %s", e)

    logger.info("[instagram] child_ids=%s failed=%s", children, failed)
    if failed or len(children) < 2:
        if ok_paths:
            logger.warning(
                "[instagram] carousel aborted (%d failed) — single image fallback",
                len(failed) or (2 - len(children)),
            )
            return _post_single_image(ok_paths[0], caption)
        return {"success": False, "media_id": "", "permalink": "", "error": "carousel_children_failed"}

    # 2. Create carousel container
    try:
        carousel_data = graph_request(
            "POST",
            f"{_GRAPH_API}/{acct_id}/media",
            {
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "caption": caption,
                "access_token": token,
            },
            timeout=30,
        )
        carousel_id = carousel_data.get("id", "")
        if not carousel_id:
            err = (carousel_data.get("error") or {}).get("message", "carousel_container_failed")
            return {"success": False, "media_id": "", "permalink": "", "error": err}

        wait_for_container(carousel_id, token)
        return _publish_container(carousel_id, acct_id, token)

    except (ContainerNotReady, MetaRequestError) as e:
        logger.error("[instagram] Carousel not published: %s", e)
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}
    except Exception as e:
        logger.error("[instagram] Carousel post error: %s", e)
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}


def post_reel_video(video_url: str, caption: str) -> dict:
    """
    Publish an actual Instagram REEL from a public video URL.
    Video processing is async, so we poll the container until FINISHED.
    """
    if not is_configured():
        return {"success": False, "media_id": "", "error": "not_configured"}
    try:
        import requests
    except ImportError:
        return {"success": False, "media_id": "", "error": "requests_not_installed"}

    from content_generator.publisher import meta_graph
    from content_generator.publisher.meta_graph import ContainerNotReady, MetaRequestError

    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token   = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    try:
        params = {"media_type": "REELS", "video_url": video_url,
                  "caption": caption, "share_to_feed": "true",
                  "audio_name": "Purity Beans • 100% Pure Coffee",
                  "access_token": token}
        # product tags on reels (if IG Shopping configured)
        try:
            from content_generator.publisher.product_tags import build_reel_product_tags
            tags = build_reel_product_tags(caption)
            if tags:
                params["product_tags"] = tags
        except Exception as _e:
            logger.debug("[instagram] optional step failed: %s", _e)
        data = meta_graph.graph_request(
            "POST", f"{_GRAPH_API}/{acct_id}/media", params, timeout=60,
        )
        container_id = data.get("id", "")
        if not container_id:
            err = (data.get("error") or {}).get("message", str(data))
            return {"success": False, "media_id": "", "error": err}

        # Video encoding often needs several minutes. Stop at ~5 minutes and
        # do not publish a container that is still processing.
        meta_graph.wait_for_container(
            container_id, token,
            max_wait=meta_graph._VIDEO_POLL_S,
            interval=meta_graph._POLL_INTERVAL,
        )
        result = _publish_container(container_id, acct_id, token)
        logger.info("[instagram] Reel video published: %s", result.get("success"))
        return result
    except (ContainerNotReady, MetaRequestError) as e:
        logger.error("[instagram] Reel video not published: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}
    except Exception as e:
        logger.error("[instagram] Reel video error: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}


def _post_reel_direct_binary(video_path: str, caption: str) -> dict:
    """Publish Instagram Reel directly via Meta's resumable video upload protocol."""
    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not acct_id or not token or not os.path.isfile(video_path):
        return {"success": False, "media_id": "", "error": "missing_prerequisites"}
    try:
        import requests
        from content_generator.publisher import meta_graph
        from content_generator.publisher.meta_graph import ContainerNotReady, MetaRequestError

        file_size = os.path.getsize(video_path)
        init_params = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true",
            "audio_name": "Purity Beans • 100% Pure Coffee",
            "access_token": token,
        }
        init_data = meta_graph.graph_request(
            "POST",
            f"{_GRAPH_API}/{acct_id}/media",
            init_params,
            timeout=30,
        )
        container_id = init_data.get("id")
        upload_uri = init_data.get("uri")
        if not container_id or not upload_uri:
            return {"success": False, "media_id": "", "error": "resumable_init_failed"}

        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
        }
        with open(video_path, "rb") as fh:
            up_resp = requests.post(upload_uri, headers=headers, data=fh, timeout=120)
        if up_resp.status_code not in (200, 201):
            return {"success": False, "media_id": "", "error": f"resumable_transfer_failed: {up_resp.status_code}"}

        meta_graph.wait_for_container(
            container_id, token,
            max_wait=meta_graph._VIDEO_POLL_S,
            interval=meta_graph._POLL_INTERVAL,
        )
        return _publish_container(container_id, acct_id, token)
    except (ContainerNotReady, MetaRequestError) as e:
        logger.error("[instagram] Direct binary reel container failed: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}
    except Exception as exc:
        logger.debug("[instagram] Direct binary reel upload failed: %s", exc)
        return {"success": False, "media_id": "", "error": str(exc)}


def post_story(content: dict, day: int = 0) -> dict:
    """
    Publish an Instagram Story (image, 9:16, 24h ephemeral).

    Composes a story image from today's story content + a real jar photo, then
    publishes via media_type=STORIES. Interactive stickers (polls/questions)
    cannot be set via the API — those stay manual; this keeps a daily story
    presence and can carry a swipe-up/link on eligible accounts.
    """
    if not is_configured():
        return {"success": False, "media_id": "", "error": "not_configured"}

    # Prefer generated story_1, else today's reel/carousel hook, else a
    # day-rotated bank. Never the historical slogan pair that printed
    # identically every day except for the jar.
    from content_generator.publisher.story_copy import resolve_story_copy
    copy = resolve_story_copy(content, day=day)
    headline = copy["headline"]
    sub = copy["sub"]
    logger.info("[instagram] story copy source=%s headline=%r", copy.get("source"), headline)

    product = None
    try:
        from content_generator.rotation import PRODUCTS, pick as _pick_product
        product = _pick_product(PRODUCTS, day)
    except Exception as e:
        logger.debug("[instagram] product pick skipped: %s", e)

    image_path = None
    try:
        # Cinematic frame: white background knocked out + full-bleed 9:16 gradient.
        # (The 1:1 post composer left a white box and dead space in stories.)
        from content_generator.creative.cinematic_frame import compose_cinematic_frame
        image_path = compose_cinematic_frame(
            headline=headline, sub=sub, day=day, idx=9, product=product,
            width=1080, height=1920, label=f"story_day{day}",
        )
    except Exception as e:
        logger.warning("[instagram] cinematic story compose failed: %s", e)
    if not image_path:
        try:
            from content_generator.creative.real_jar_composer import compose_post_image
            image_path = compose_post_image(
                headline=headline, body=sub, day=day, idx=9,
                width=1080, height=1920, label=f"story_day{day}",
            )
        except Exception as e:
            logger.warning("[instagram] story image compose failed: %s", e)
    if not image_path:
        return {"success": False, "media_id": "", "error": "no_story_image"}

    try:
        import requests
    except ImportError:
        return {"success": False, "media_id": "", "error": "requests_not_installed"}

    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token   = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    # Attempt to render dynamic 9:16 vertical video story with royalty-free audio
    video_path = None
    try:
        from content_generator.creative.story_video import build_story_video
        video_path = build_story_video(
            image_path=image_path,
            headline=headline,
            day=day,
            duration=7.5,
            label=f"story_video_day{day}",
        )
    except Exception as ve:
        logger.debug("[instagram] story video build skipped/failed: %s", ve)

    media_payload = {"media_type": "STORIES", "access_token": token}
    if video_path and os.path.exists(video_path):
        from content_generator.publisher.video_host import upload_video
        video_url = upload_video(video_path)
        if video_url:
            media_payload["video_url"] = video_url
            logger.info("[instagram] Story using dynamic video with audio: %s", video_url)

    if "video_url" not in media_payload:
        image_url = _upload_to_public_url(image_path)
        if not image_url:
            return {"success": False, "media_id": "", "error": "media_upload_failed"}
        media_payload["image_url"] = image_url

    try:
        from content_generator.publisher.meta_graph import (
            ContainerNotReady, MetaRequestError, graph_request, wait_for_container,
        )
        data = graph_request(
            "POST",
            f"{_GRAPH_API}/{acct_id}/media",
            media_payload,
            timeout=30,
        )
        container_id = data.get("id", "")
        if not container_id:
            err = (data.get("error") or {}).get("message", str(data))
            return {"success": False, "media_id": "", "error": err}
        wait_for_container(container_id, token)
        result = _publish_container(container_id, acct_id, token)
        logger.info("[instagram] Story published: %s", result.get("success"))
        return result
    except (ContainerNotReady, MetaRequestError) as e:
        logger.error("[instagram] Story not published: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}
    except Exception as e:
        logger.error("[instagram] Story post error: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}


def _publish_container(container_id: str, acct_id: str, token: str) -> dict:
    """Publish a ready media container."""
    try:
        from content_generator.publisher.meta_graph import MetaRequestError, graph_request
        data = graph_request(
            "POST",
            f"{_GRAPH_API}/{acct_id}/media_publish",
            {"creation_id": container_id, "access_token": token},
            timeout=20,
        )
        media_id = data.get("id", "")
        if media_id:
            permalink = _get_permalink(media_id, token)
            logger.info("[instagram] Published | id=%s | url=%s", media_id, permalink)
            return {"success": True, "media_id": media_id, "permalink": permalink, "error": None}
        err = (data.get("error") or {}).get("message", str(data))
        return {"success": False, "media_id": "", "permalink": "", "error": err}
    except MetaRequestError as e:
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}
    except Exception as e:
        return {"success": False, "media_id": "", "permalink": "", "error": str(e)}


def _wait_for_container(container_id: str, token: str, max_wait: int = 60) -> None:
    """Poll until FINISHED. ERROR and timeout raise ContainerNotReady."""
    from content_generator.publisher.meta_graph import wait_for_container
    wait_for_container(container_id, token, max_wait=max_wait)


def _get_permalink(media_id: str, token: str) -> str:
    """Fetch the permanent URL for a published post."""
    try:
        import requests
        resp = requests.get(
            f"{_GRAPH_API}/{media_id}",
            params={"fields": "permalink"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return resp.json().get("permalink", "")
    except Exception:
        return ""


def _upload_to_public_url(image_path: str) -> str | None:
    """
    Instagram requires a publicly accessible HTTPS URL for image containers.
    We try:
    1. Imgbb (IMGBB_API_KEY)
    2. Cloudinary (CLOUDINARY_URL)
    3. Meta Facebook Page CDN (native fallback using connected Facebook Page)
    """
    try:
        import requests, base64

        imgbb_key = os.getenv("IMGBB_API_KEY")

        if imgbb_key:
            try:
                with open(image_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")

                resp = requests.post(
                    "https://api.imgbb.com/1/upload",
                    data={"key": imgbb_key, "image": encoded},
                    timeout=30,
                )
                url = resp.json().get("data", {}).get("url", "")
                if url:
                    logger.debug("[instagram] Image hosted at: %s", url)
                    return url
                logger.warning("[instagram] ImgBB upload rejected (%d): %s", resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("[instagram] ImgBB request error: %s", e)

        # Fallback 1: try Cloudinary if configured
        cloud_url = _cloudinary_upload(image_path)
        if cloud_url:
            return cloud_url

        # Fallback 2: Meta Facebook CDN upload
        meta_cdn_url = _upload_to_facebook_cdn(image_path)
        if meta_cdn_url:
            return meta_cdn_url

        logger.warning(
            "[instagram] No working image hosting available. "
            "Tried Imgbb, Cloudinary, and Facebook CDN."
        )
        return None

    except Exception as e:
        logger.debug("[instagram] Image upload error: %s", e)
        return None


def _upload_to_facebook_cdn(image_path: str) -> str | None:
    """
    Fallback upload to connected Facebook Page as unpublished photo to obtain
    a Meta CDN (scontent.xx.fbcdn.net) URL.
    """
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip() or os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not page_id or not token:
        return None
    try:
        from content_generator.publisher.facebook import resolve_page_access_token
        page_token = resolve_page_access_token(page_id, token)
    except Exception:
        page_token = token

    try:
        import requests
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{_GRAPH_API}/{page_id}/photos",
                data={"published": "false", "temporary": "true"},
                files={"source": f},
                headers={"Authorization": f"Bearer {page_token}"},
                timeout=30,
            )
        photo_id = resp.json().get("id")
        if not photo_id:
            logger.debug("[instagram] Facebook CDN photo upload failed: %s", resp.text[:200])
            return None
        img_resp = requests.get(
            f"{_GRAPH_API}/{photo_id}",
            params={"fields": "images"},
            headers={"Authorization": f"Bearer {page_token}"},
            timeout=15,
        )
        images = img_resp.json().get("images", [])
        if images and isinstance(images, list) and images[0].get("source"):
            cdn_url = images[0]["source"]
            logger.info("[instagram] Image hosted via Meta Facebook CDN: %s", cdn_url[:60])
            return cdn_url
    except Exception as exc:
        logger.debug("[instagram] Facebook CDN upload exception: %s", exc)
    return None


def _cloudinary_upload(image_path: str) -> str | None:
    """Upload to Cloudinary if CLOUDINARY_URL is set (free 25GB/month)."""
    cloud_url = os.getenv("CLOUDINARY_URL")
    if not cloud_url:
        return None
    try:
        import re, requests, base64, hashlib, time as _time
        m = re.match(r"cloudinary://(\w+):(\S+)@(\S+)", cloud_url.strip())
        if not m:
            logger.warning("[instagram] Cloudinary URL format invalid")
            return None
        api_key, api_secret, cloud_name = m.groups()
        cloud_name = cloud_name.strip("/")

        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()

        ts  = str(int(_time.time()))
        sig = hashlib.sha1(f"timestamp={ts}{api_secret}".encode()).hexdigest()

        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
            data={"file": f"data:image/jpeg;base64,{encoded}",
                  "timestamp": ts, "api_key": api_key, "signature": sig},
            timeout=60,
        )
        url = resp.json().get("secure_url", "")
        if url:
            return url
        logger.warning("[instagram] Cloudinary upload returned no URL: %s", resp.text[:200])
        return None
    except Exception as exc:
        logger.warning("[instagram] Cloudinary upload error: %s", exc)
        return None


def image_aspect_ratio(path: str) -> float | None:
    """Width / height, or None when the file cannot be read."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            width, height = im.size
        if height <= 0:
            return None
        return width / height
    except Exception as e:
        logger.debug("[instagram] could not read aspect of %s: %s", path, e)
        return None


def aspect_is_feed_safe(ratio: float | None) -> bool:
    if ratio is None:
        return False
    return (_FEED_MIN_RATIO - 0.01) <= ratio <= (_FEED_MAX_RATIO + 0.01)


def prepare_feed_image(path: str) -> str | None:
    """
    Return a feed-safe image path.

    4:5 through 1.91:1 is returned unchanged. Anything taller (a 1080x1920
    reel thumbnail) is center-cropped to 1080x1350 (4:5). None means the
    caller should post the original as a Story instead of a feed image.
    """
    ratio = image_aspect_ratio(path)
    if ratio is None:
        return None
    if aspect_is_feed_safe(ratio):
        return path
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        width, height = im.size
        target = 4 / 5
        if height <= 0 or width <= 0:
            return None
        if (width / height) < target:
            new_h = int(round(width / target))
            top = max(0, (height - new_h) // 2)
            im = im.crop((0, top, width, min(height, top + new_h)))
        else:
            new_w = int(round(height * target))
            left = max(0, (width - new_w) // 2)
            im = im.crop((left, 0, min(width, left + new_w), height))
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        im = im.resize((1080, 1350), resample)
        out = os.path.splitext(path)[0] + "_feed45.jpg"
        im.save(out, "JPEG", quality=90)
        logger.info("[instagram] rendered feed-safe 4:5 image %s", out)

        try:
            from content_generator.creative.jar_provenance import inherit_provenance
            inherit_provenance(out, source_path=path)
        except Exception as pe:
            logger.debug("[instagram] Provenance inheritance skipped: %s", pe)

        return out
    except Exception as e:
        logger.warning("[instagram] could not render 4:5 feed image: %s", e)
        return None


def post_local_story(image_path: str) -> dict:
    """Publish an existing image as an Instagram Story (9:16 is valid here)."""
    if not is_configured():
        return {"success": False, "media_id": "", "error": "not_configured"}
    if not image_path or not os.path.exists(image_path):
        return {"success": False, "media_id": "", "error": "no_story_image"}

    from content_generator.creative.jar_provenance import verify_jar_provenance
    prov = verify_jar_provenance(image_path)
    if not prov.get("verified"):
        logger.error("[instagram] Refusing to publish unverified story image: %s (%s)", image_path, prov.get("reason"))
        return {"success": False, "media_id": "", "error": f"real_jar_unverified: {prov.get('reason')}"}
    try:
        import requests  # noqa: F401
    except ImportError:
        return {"success": False, "media_id": "", "error": "requests_not_installed"}

    acct_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    image_url = _upload_to_public_url(image_path)
    if not image_url:
        return {"success": False, "media_id": "", "error": "image_upload_failed"}
    try:
        from content_generator.publisher.meta_graph import (
            ContainerNotReady, MetaRequestError, graph_request, wait_for_container,
        )
        data = graph_request(
            "POST",
            f"{_GRAPH_API}/{acct_id}/media",
            {"image_url": image_url, "media_type": "STORIES", "access_token": token},
            timeout=30,
        )
        container_id = data.get("id", "")
        if not container_id:
            err = (data.get("error") or {}).get("message", str(data))
            return {"success": False, "media_id": "", "error": err}
        wait_for_container(container_id, token)
        return _publish_container(container_id, acct_id, token)
    except (ContainerNotReady, MetaRequestError) as e:
        return {"success": False, "media_id": "", "error": str(e)}
    except Exception as e:
        logger.error("[instagram] local story error: %s", e)
        return {"success": False, "media_id": "", "error": str(e)}


def _today() -> str:
    from content_generator.core.ist_dates import today_ist
    return today_ist().isoformat()
