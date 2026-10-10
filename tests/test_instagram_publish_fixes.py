"""
Fixes that stopped morning/evening Instagram slots from publishing.

Covers the date comparison, approval of a realistic content file, hashtag cap,
feed aspect ratio, container ERROR/timeout, and held-reported-as-failure.
Run: python tests/test_instagram_publish_fixes.py
"""
import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LEARNING_DIR"] = tempfile.mkdtemp(prefix="pb_test_learning_")
os.environ.setdefault("INSTAGRAM_ACCOUNT_ID", "ig_test")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "token_test")

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def _score():
    return {"overall": 8.6, "verdict": "PASS", "feedback": "strong"}


def _reel():
    return {
        "id": "reel_1",
        "hook_text": "CHECK THE LABEL",
        "hook_spoken": "The back of the jar is the recipe, not the marketing.",
        "hook_text_overlay": "READ THE BACK",
        "frames": [
            {"on_screen": "READ THE BACK", "spoken": "The front of the pack is marketing. The back is the recipe."},
            {"on_screen": "INGREDIENTS", "spoken": "Find the ingredient list and read every line, not just the first."},
            {"on_screen": "THE DIFFERENCE", "spoken": "Chicory is a root. Coffee is a bean. The label says which one you bought."},
            {"on_screen": "ONE LINE", "spoken": "Purity Beans lists one thing: coffee. Zero chicory, nothing added."},
            {"on_screen": "YOUR TURN", "spoken": "Check the jar in your kitchen tonight and see what it actually says."},
        ],
        "caption": (
            "The front of a coffee pack is marketing. The back is the recipe. "
            "Check the ingredient list: chicory is a root, not a bean, and it changes the cup. "
            "Purity Beans is 100% coffee, zero chicory. Read the label, then visit p3online.in."
        ),
        "cta": "Read the label at p3online.in",
        "comment_trigger": "What does the label on your jar actually say?",
        "save_trigger": "Save this before your next grocery run.",
        "share_trigger": "Send this to whoever buys the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "editorial_score": _score(),
        # audio plan and loop note intentionally absent — regeneration used to drop them
    }


def _carousel():
    return {
        "id": "carousel_1",
        "title": "Why the label hides chicory",
        "caption": "",
        "slides": [
            {"slide": 1, "heading": "Read the ingredient list",
             "body": "It sits on the back, usually in the smallest type on the pack.",
             "visual": "Close-up of an ingredient panel"},
            {"slide": 2, "heading": "Count the ingredients",
             "body": "Coffee needs one. Anything else is there for a reason worth knowing.",
             "visual": "Finger tracing a short ingredient list"},
            {"slide": 3, "heading": "Look for chicory",
             "body": "It is a root, not a bean, and the label names it when it is present.",
             "visual": "Ingredient panel with chicory in frame"},
            {"slide": 4, "heading": "Check the order",
             "body": "Ingredients are listed by weight, so the first line is the bulk of the jar.",
             "visual": "First line of an ingredient panel"},
            {"slide": 5, "heading": "What actually changes",
             "body": "The difference is taste. A root makes the cup muddy. Coffee does not.",
             "visual": "Two cups side by side"},
            {"slide": 6, "heading": "Do it tonight",
             "body": "Turn the jar around and read the list. Purity Beans is 100% coffee, zero chicory. p3online.in",
             "visual": "Hand turning a jar on a kitchen counter"},
        ],
        "cta": "Read the label at p3online.in",
        "editorial_score": _score(),
    }


def _growth():
    return {
        "id": "growth_reel",
        "track": "growth",
        "chosen_hook": "The label is the recipe",
        "script": [
            {"time": "0-2s", "on_screen": "READ THE BACK", "voiceover": "The front of the pack is a promise."},
            {"time": "2-6s", "on_screen": "THE LABEL", "voiceover": "The ingredient list is the only line that cannot spin."},
            {"time": "6-12s", "on_screen": "A ROOT", "voiceover": "Chicory is a root. It is not a bean, and the label has to say so."},
            {"time": "12-18s", "on_screen": "WHY IT MATTERS", "voiceover": "Because the first ingredient is what the cup actually is."},
            {"time": "18-24s", "on_screen": "CHECK IT", "voiceover": "Check the jar tonight and see what is actually in the cup."},
            {"time": "24-30s", "on_screen": "LOOP", "voiceover": "Then turn it back to the front, which is where this started."},
        ],
        "sound_suggestion": "Quiet kitchen, voice forward, no lyric bed",
        "caption": (
            "The ingredient list is the only honest line on a coffee pack. "
            "Chicory is a root, not a bean, and it changes what the cup actually is. "
            "Check the label tonight and see what you have been brewing."
        ),
        "comment_trigger": "What did the ingredient list actually say?",
        "save_trigger": "Save this for the next time you buy coffee.",
        "share_trigger": "Send this to someone who never turns the jar around.",
        "hashtags": ["#coffee", "#coffeelabel", "#ingredientlist", "#instantcoffee", "#coffeeindia"],
        "editorial_score": _score(),
    }


def _realistic_content() -> dict:
    return {
        "date": "October 03, 2026",
        "day_number": 42,
        "generation_id": "gen_2026-10-03_abcd1234",
        "reels": [_reel()],
        "carousel": _carousel(),
        "growth_reel": _growth(),
        "instagram_post": {},
    }


def main():
    # 1. Date handling
    print("\nIST date field matches legacy long-form dates:")
    from content_generator.core.ist_dates import content_date_iso, content_matches_today, today_ist
    today = datetime.date(2026, 10, 3)
    check("legacy long form parses to ISO", content_date_iso("October 03, 2026") == "2026-10-03")
    check("unpadded legacy day parses", content_date_iso("October 3, 2026") == "2026-10-03")
    check("ISO date stays ISO", content_date_iso("2026-10-03") == "2026-10-03")
    check("ISO datetime uses the date", content_date_iso("2026-10-03T06:00:00") == "2026-10-03")
    ok, why = content_matches_today({"date": "October 03, 2026"}, today)
    check("legacy date matches that IST day", ok, why)
    ok, why = content_matches_today({"date": "October 02, 2026"}, today)
    check("previous day is stale_content", (not ok) and why.startswith("stale_content"), why)
    check("generator writes ISO via today_ist", "today_ist()" in open(
        "content_generator/pipeline/generator.py", encoding="utf-8").read())
    check("generator no longer writes Month DD, YYYY",
          'strftime("%B' not in open("content_generator/pipeline/generator.py", encoding="utf-8").read())
    # today_ist itself is the shared helper
    check("today_ist returns a date", isinstance(today_ist(), datetime.date))

    # 2. Approval of a realistic file, including a regen-damaged shape
    print("\napproved_assets on a realistic generated file:")
    from content_generator.core.editorial_engine import approved_assets
    from content_generator.core.piece_integrity import merge_regenerated_piece
    folder = tempfile.mkdtemp(prefix="pb_content_")
    path = os.path.join(folder, "content_2026-10-03.json")
    content = _realistic_content()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(content, fh)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    approved = approved_assets(loaded)
    check("carousel approved despite empty caption", "carousel" in approved, str(sorted(approved)))
    check("reel_1 approved without a pre-baked audio plan", "reel_1" in approved, str(sorted(approved)))
    check("growth_reel approved from prompt field names", "growth_reel" in approved, str(sorted(approved)))
    if "carousel" in approved:
        check("carousel caption was restored", len(str(approved["carousel"].get("caption") or "")) >= 50)
        check("carousel triggers restored", len(str(approved["carousel"].get("hashtags") or "")) >= 10)
    if "reel_1" in approved:
        piece = approved["reel_1"]
        check("reel kept a loop note", bool(piece.get("loop_note") or piece.get("loop_ending")))
        check("reel kept an audio plan", bool(piece.get("audio") or piece.get("music_vibe")))
        score = piece.get("editorial_score") or {}
        check("editorial subscores filled", all(score.get(k) is not None for k in (
            "shareability", "saveability", "emotion_pull", "hook_strength", "brand_clarity")))
    # A short rewrite must not replace the piece.
    from content_generator.scheduler.daily import _apply_regeneration
    short = {"hook_text": "READ THE LABEL", "caption": "too short to publish"}
    merged = merge_regenerated_piece(_reel(), short)
    check("merge keeps the long caption", len(merged["caption"]) >= 50, merged["caption"][:40])
    check("merge keeps frames", len(merged["frames"]) >= 5)
    check("merge applies the new hook", merged["hook_text"] == "READ THE LABEL")
    applied = _apply_regeneration("reel_1", _reel(), short)
    check("merged reel passes schema after structural repair", applied is not None)
    if applied:
        score = applied.get("editorial_score") or {}
        check("repair fills editorial subscores the schema requires",
              score.get("shareability") is not None and score.get("hook_strength") is not None)
    from content_generator.scheduler.slots import _select_evening_reel
    only_two = {"reel_2": {"hook": "Check the label"}}
    picked = _select_evening_reel(only_two)
    check("evening can publish reel_2", picked and picked[0] == "reel_2")
    both = {"growth_reel": {"hook": "g"}, "reel_1": {"hook": "a"}, "reel_2": {"hook": "b"}}
    check("evening still prefers growth_reel", _select_evening_reel(both)[0] == "growth_reel")

    # 3. Hashtag cap and the correct piece
    print("\nCaption uses the carousel and stays inside Instagram limits:")
    from content_generator.publisher import instagram as ig
    import content_generator.analytics.hashtag_bank as hb
    real_sel = hb.select_hashtags
    hb.select_hashtags = lambda day=0: " ".join(f"#Bank{i}" for i in range(25))
    try:
        reel_tags = " ".join(f"#ReelTag{i}" for i in range(20))
        post = {
            "carousel": {"title": "Read the label", "caption": "", "slides": _carousel()["slides"]},
            "reels": [{"caption": f"Reel body already tagged {reel_tags}", "hashtags": reel_tags}],
        }
        caption = ig._extract_caption(post, day=3)
        tags = [w for w in caption.split() if w.startswith("#")]
        check("does not borrow the reel hashtags", not any(t.startswith("#ReelTag") for t in tags), caption[-80:])
        check("uses the carousel title", "label" in caption.lower())
        check("hashtag count is 5-15", 5 <= len(tags) <= 15, str(len(tags)))
        check("hashtag count is under the hard max", len(tags) <= 30)
        check("caption length is at most 2200", len(caption) <= 2200, str(len(caption)))
        stuffed = "Check the ingredient list. " + " ".join(f"#Inline{i}" for i in range(28))
        capped = ig._assemble_caption(stuffed, {"hashtags": reel_tags}, day=3)
        capped_tags = [w for w in capped.split() if w.startswith("#")]
        check("inline hashtags are stripped before the bank is added",
              not any(t.startswith("#Inline") for t in capped_tags), str(capped_tags[:5]))
        check("stuffed caption still caps tags", len(capped_tags) <= 30, str(len(capped_tags)))
        check("stuffed caption still fits", len(capped) <= 2200, str(len(capped)))
    finally:
        hb.select_hashtags = real_sel

    # 4. Feed aspect
    print("\n9:16 thumbnail is not posted as a feed image:")
    from PIL import Image
    img_dir = tempfile.mkdtemp(prefix="pb_img_")
    src = os.path.join(img_dir, "reel_thumb.jpg")
    Image.new("RGB", (1080, 1920), (20, 10, 5)).save(src, "JPEG")
    check("9:16 is not feed-safe", not ig.aspect_is_feed_safe(ig.image_aspect_ratio(src)))
    feed = ig.prepare_feed_image(src)
    check("4:5 render was produced", bool(feed) and feed != src, str(feed))
    if feed:
        with Image.open(feed) as out:
            ratio = out.size[0] / out.size[1]
        check("rendered size is 1080x1350", Image.open(feed).size == (1080, 1350))
        check("rendered ratio is 4:5", abs(ratio - 0.8) < 0.01, str(ratio))
        check("4:5 is feed-safe", ig.aspect_is_feed_safe(ratio))

    # 5. Container ERROR, timeout, carousel child, transient retry
    print("\nContainer errors fail closed:")
    import requests
    from content_generator.publisher import meta_graph

    class _Resp:
        def __init__(self, data, status=200):
            self._data = data
            self.status_code = status
        def json(self):
            return self._data

    calls = []
    real_request = requests.request
    real_upload = ig._upload_to_public_url
    saved_retry = (meta_graph._RETRY_BASE_DELAY, meta_graph._POLL_INTERVAL, meta_graph._VIDEO_POLL_S)
    meta_graph._RETRY_BASE_DELAY = 0
    meta_graph._POLL_INTERVAL = 0
    meta_graph._VIDEO_POLL_S = 0

    def _install(handler):
        requests.request = handler
        ig._upload_to_public_url = lambda path: "https://cdn.example/" + os.path.basename(path)

    def _restore():
        requests.request = real_request
        ig._upload_to_public_url = real_upload

    try:
        calls.clear()
        def errored(method, url, params=None, timeout=None, headers=None):
            calls.append((method, url, params or {}))
            if method == "GET":
                return _Resp({"status_code": "ERROR", "status": "Media download failed"})
            return _Resp({"id": "container_err"})
        _install(errored)
        result = ig._post_single_image(src, "caption body")
        published = [c for c in calls if "media_publish" in c[1]]
        check("ERROR container is not published", not result["success"] and not published, result.get("error"))
        check("ERROR reason is surfaced", "Media download failed" in (result.get("error") or ""), result.get("error"))

        calls.clear()
        def stalled(method, url, params=None, timeout=None, headers=None):
            calls.append((method, url, params or {}))
            if method == "GET":
                return _Resp({"status_code": "IN_PROGRESS"})
            return _Resp({"id": "container_wait"})
        _install(stalled)
        result = ig.post_reel_video("https://cdn.example/reel.mp4", "caption")
        published = [c for c in calls if "media_publish" in c[1]]
        check("video timeout is not published", not result["success"] and not published, result.get("error"))
        check("timeout names the last status", "timeout" in (result.get("error") or "").lower(), result.get("error"))

        calls.clear()
        def one_child(method, url, params=None, timeout=None, headers=None):
            calls.append((method, url, params or {}))
            params = params or {}
            if method == "GET":
                return _Resp({"status_code": "FINISHED"})
            if params.get("is_carousel_item"):
                if "bad" in str(params.get("image_url")):
                    return _Resp({"error": {"message": "image rejected", "code": 9004}})
                return _Resp({"id": "child_only"})
            if "media_publish" in url:
                return _Resp({"id": "published_single"})
            return _Resp({"id": "single_container"})
        _install(one_child)
        bad = os.path.join(img_dir, "bad.jpg")
        Image.new("RGB", (1080, 1080), (1, 1, 1)).save(bad, "JPEG")
        result = ig._post_carousel([src, bad], "Carousel caption about the label")
        publish_ids = [c[2].get("creation_id") for c in calls if "media_publish" in c[1]]
        captioned = [c for c in calls if c[0] == "POST" and str(c[1]).endswith("/media") and c[2].get("caption")]
        check("failed child does not publish the item container",
              "child_only" not in publish_ids, str(publish_ids))
        check("fallback single post carries the caption", bool(captioned), str(calls)[:200])
        check("fallback publish succeeded", result.get("success") is True, result.get("error"))

        calls.clear()
        state = {"n": 0}
        def flaky(method, url, params=None, timeout=None, headers=None):
            calls.append((method, url, params or {}))
            state["n"] += 1
            if state["n"] == 1:
                return _Resp({"error": {"message": "rate limit reached", "code": 4, "is_transient": True}}, 400)
            if method == "GET":
                return _Resp({"status_code": "FINISHED"})
            if "media_publish" in url:
                return _Resp({"id": "published_ok"})
            return _Resp({"id": "container_ok"})
        _install(flaky)
        result = ig._post_single_image(src, "caption after retry")
        check("transient Meta error is retried", state["n"] >= 2 and result.get("success"), result.get("error"))
    finally:
        _restore()
        meta_graph._RETRY_BASE_DELAY, meta_graph._POLL_INTERVAL, meta_graph._VIDEO_POLL_S = saved_retry

    # 6. Unexpected holds fail the run
    print("\nUnexpected holds fail the run:")
    from content_generator.core.publish_contract import build, evaluate
    held = build("morning", 1, {}, {}, status="held", reason="stale_content — file is dated October 03, 2026")
    verdict = evaluate(held)
    check("stale hold is not ok", verdict["status"] == "held" and not verdict["ok"], str(verdict))
    legit = build("evening", 1, {}, {}, status="skipped", reason="already published today")
    check("already published today stays green", evaluate(legit)["ok"])
    gate = build("evening", 1, {}, {}, status="held", reason="canonical_validation_failed")
    check("empty gate hold fails the run", not evaluate(gate)["ok"])

    # 7. Alerting when webhook or SMTP is configured, and quiet when it is not
    print("\nFailure alerts follow the configured channel:")
    from content_generator.scheduler.watchdog import alert_failure
    import urllib.request
    real_open = urllib.request.urlopen
    opened = {"n": 0}
    def _open(req, timeout=10):
        opened["n"] += 1
        class _R:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return b""
        return _R()
    saved = {k: os.environ.get(k) for k in (
        "ALERT_WEBHOOK_URL", "ALERT_EMAIL_TO", "SMTP_PASS", "SMTP_USER", "NURTURE_FROM_EMAIL")}
    try:
        os.environ.pop("ALERT_WEBHOOK_URL", None)
        os.environ.pop("ALERT_EMAIL_TO", None)
        os.environ.pop("SMTP_PASS", None)
        urllib.request.urlopen = _open
        opened["n"] = 0
        alert_failure("quiet")
        check("empty secrets do not call the webhook", opened["n"] == 0)
        os.environ["ALERT_WEBHOOK_URL"] = "https://example.test/hook"
        alert_failure("webhook")
        check("webhook is called when ALERT_WEBHOOK_URL is set", opened["n"] == 1)
        import smtplib
        sent = {"n": 0}
        class _SMTP:
            def __init__(self, host, port, timeout=15):
                sent["host"] = host
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def starttls(self):
                return None
            def login(self, user, password):
                sent["user"] = user
            def send_message(self, msg):
                sent["n"] += 1
        real_smtp = smtplib.SMTP
        smtplib.SMTP = _SMTP
        os.environ["ALERT_EMAIL_TO"] = "founder@example.com"
        os.environ["SMTP_PASS"] = "test-pass"
        os.environ["SMTP_USER"] = "engine@example.com"
        os.environ["NURTURE_FROM_EMAIL"] = "engine@example.com"
        try:
            alert_failure("smtp")
        finally:
            smtplib.SMTP = real_smtp
        check("SMTP alert uses SMTP_PASS and ALERT_EMAIL_TO", sent["n"] == 1, str(sent))
    finally:
        urllib.request.urlopen = real_open
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # 8. Reels use only a valid MP4 for the current content day; stale videos are never reused.
    print("\\nRendered Reel discovery:")
    from content_generator.publisher import instagram as ig
    from content_generator.core.ist_dates import today_ist
    previous_creative_dir = os.environ.get("CREATIVE_OUTPUT_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="pb_reel_assets_") as video_dir:
            os.environ["CREATIVE_OUTPUT_DIR"] = video_dir
            reel_day = 282
            current_path = os.path.join(
                video_dir, f"reel_1_video_day{reel_day}_{today_ist().isoformat()}.mp4"
            )
            with open(current_path, "wb") as fh:
                fh.write(b"v" * 20_000)
            check("finds current-day rendered reel", ig._find_reel_video(reel_day) == current_path)
            os.remove(current_path)
            stale_path = os.path.join(video_dir, f"reel_1_video_day{reel_day}_2026-10-09.mp4")
            with open(stale_path, "wb") as fh:
                fh.write(b"v" * 20_000)
            check("never reuses stale reel video", ig._find_reel_video(reel_day) is None)
    finally:
        if previous_creative_dir is None:
            os.environ.pop("CREATIVE_OUTPUT_DIR", None)
        else:
            os.environ["CREATIVE_OUTPUT_DIR"] = previous_creative_dir

    print(f"\n{'INSTAGRAM PUBLISH FIXES FAILED' if failures else 'instagram publish fixes hold'} "
          f"({len(failures)} failure(s))")
    return 1 if failures else 0


def test_main():
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    raise SystemExit(main())
