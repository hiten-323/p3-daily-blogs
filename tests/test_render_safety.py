"""
Render safety — the gates between generated copy and published pixels.

Every check here exists because the failure it guards reached a live Instagram
post. Run: python tests/test_render_safety.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

failures = []


def check(name, ok, detail=""):
    msg = f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else "")
    try:
        print(msg)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(msg.encode(encoding, errors="replace").decode(encoding))
    if not ok:
        failures.append(name)


def main():
    from content_generator.creative.real_jar_composer import (
        _sanitize_text, _all_jar_photos, is_overlay_safe, pick_jar_photo, _font,
    )
    from content_generator.scheduler.daily import _clean_scaffolding

    # 1. Scaffolding must never reach pixels. Every string here is a shape the
    #    LLM has actually produced; "SLIDE 1:" shipped to a live carousel.
    print("\nScaffolding labels are stripped:")
    for raw in ("SLIDE 1: It tastes bitter",
                "**Slide 1:** It tastes bitter",
                "[Slide 1] It tastes bitter",
                "SLIDE 1 IT TASTES BITTER",
                "Slide One: It tastes bitter",
                "Slide #1: It tastes bitter",
                "Frame 3 - It tastes bitter",
                "Card 2: It tastes bitter",
                "Text overlay: It tastes bitter",
                "Hook: It tastes bitter",
                "Step 2: It tastes bitter",
                "Slide 1: Hook: It tastes bitter"):
        out = _sanitize_text(raw)
        check(f"strip {raw!r}", "slide" not in out.lower() and "hook:" not in out.lower()
              and out.lower().startswith("it"), out)

    # 2. ...without eating real copy that happens to start with those words.
    print("\nGenuine prose survives:")
    for raw in ("Step into real coffee",
                "Part of every morning",
                "Title deeds to your morning",
                "Hook your senses on real coffee",
                "Image is everything, taste is more"):
        check(f"keep {raw!r}", _sanitize_text(raw) == raw, _sanitize_text(raw))

    # 3. Unrenderable glyphs became tofu boxes on a live post. Rendered copy must
    #    be pure ASCII — whatever font the runner resolves can draw it.
    print("\nRendered text is ASCII-safe:")
    for raw in ("Quick bitterness → check the label",
                "Rated 5★ by drinkers",
                "Pure coffee ✓ no chicory ✗",
                "Only ₹299 a jar",
                "Wake up ☕ every morning \U0001f60a",
                "Café quality at home",
                "Zero chicory • 100% coffee"):
        out = _sanitize_text(raw)
        check(f"ascii {raw!r}", all(ord(c) < 128 for c in out) and out.strip() != "", out)

    # 4. Captions are NOT ascii-folded — emoji belong in Instagram captions.
    print("\nCaption path keeps emoji but drops scaffolding:")
    cap = _clean_scaffolding("Slide 1: Zero chicory ☕ shop at p3online.in")
    check("caption scaffolding stripped", not cap.lower().startswith("slide"), cap)
    check("caption keeps emoji", "☕" in cap, cap)

    # 5. A headline must never land on an asset that already carries its own copy.
    print("\nOverlay substrate selection:")
    photos = _all_jar_photos()
    check("brand assets present", len(photos) > 0, str(len(photos)))
    safe = [p for p in photos if is_overlay_safe(p)]
    check("at least 4 overlay-safe assets", len(safe) >= 4, str(len(safe)))
    for i in range(12):
        p = pick_jar_photo(i, i, overlay_safe=True)
        check(f"slide {i} substrate is overlay-safe", p is not None and is_overlay_safe(p),
              os.path.basename(p or ""))

    # 6. Finished agency creatives must stay out of the overlay pool. These four
    #    ship with their own headline, bullets and footer.
    print("\nFinished creatives excluded from overlay:")
    for name in ("puritybeans_purica_50g_lifestyle.png",
                 "puritybeans_bold_50g_lifestyle.png",
                 "puritybeans_purista_50g_lifestyle.png",
                 "puritybeans_ultra_blend_50g_variant.png"):
        path = os.path.join("brand_assets", name)
        if os.path.exists(path):
            check(f"excluded: {name}", not is_overlay_safe(path))

    # 7. A real TrueType font must resolve. Falling back to Pillow's bitmap
    #    default is what produced the tofu boxes on the runner.
    print("\nFont resolution:")
    for role in ("title", "body", "footer"):
        f = _font(role, 48)
        check(f"role '{role}' resolves a TrueType", getattr(f, "path", None) is not None,
              type(f).__name__)

    # 8. Real jar assets integrity: BrandProfile jar_reference_path must exist
    print("\nReal jar assets integrity:")
    from content_generator.core.brand_guard import BRAND, REFERENCE_IMAGES
    check("BRAND jar reference exists on disk", os.path.exists(BRAND.jar_reference_path), BRAND.jar_reference_path)
    existing_refs = [p for p in REFERENCE_IMAGES if os.path.exists(p)]
    check("all 32 jar references exist on disk", len(existing_refs) == 32, f"{len(existing_refs)}/32")

    # 9. Thumbnail generation creates image with real jar photo
    print("\nThumbnail generator real jar usage:")
    from content_generator.creative.thumbnail_generator import generate_reel_thumbnail, generate_yt_thumbnail
    reel_thumb = generate_reel_thumbnail({"hook_text": "ZERO CHICORY TEST"}, day=1, label="test_reel")
    check("reel thumbnail generates real jar file", bool(reel_thumb.get("file_path") and os.path.exists(reel_thumb["file_path"])), str(reel_thumb))
    yt_thumb = generate_yt_thumbnail({"product": "Purista"}, day=1)
    check("yt thumbnail generates real jar file", bool(yt_thumb.get("file_path") and os.path.exists(yt_thumb["file_path"])), str(yt_thumb))

    # 10. Image generation pipeline creates real jar images for instagram_post and facebook_post
    print("\nDaily image generation includes instagram_post and facebook_post with real jar:")
    from content_generator.scheduler.daily import _do_generate_images
    sample_content = {
        "instagram_post": {"hook": "PURE COFFEE ONLY", "caption": "Real coffee caption\n\np3online.in"},
        "facebook_post": {"hook": "ZERO CHICORY ALWAYS", "body": "Facebook body text"},
    }
    gen_results = _do_generate_images(sample_content, day_number=1)
    check("instagram_post image generated from real jar", bool(gen_results.get("instagram_post") and os.path.exists(gen_results["instagram_post"])), str(gen_results.get("instagram_post")))
    check("facebook_post image generated from real jar", bool(gen_results.get("facebook_post") and os.path.exists(gen_results["facebook_post"])), str(gen_results.get("facebook_post")))

    print(f"\n{'RENDER SAFETY BROKEN' if failures else 'render safety OK'} "
          f"({len(failures)} failure(s))")
    return 1 if failures else 0


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    raise SystemExit(main())
