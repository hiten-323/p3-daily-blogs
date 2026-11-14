"""Shared retry failures for Instagram, Facebook, Threads, and YouTube.

Schema prompts must ask for the fields the publisher validates. A ladder that
has already exhausted its ceiling must stop. Tokens stay out of URLs and logs.
A missing Short is rendered or the publish fails closed. Structural defaults
must not put an anti-chicory line back into a piece the quality gate rejected.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request

from content_generator.core.brand_guard import EDITORIAL_THRESHOLD
from content_generator.core.fallback_ladder import PASS_FLOOR, scratch_prompt
from content_generator.core.growth_engine import PASS_THRESHOLD
from content_generator.core.piece_integrity import _fit_threads_length, ensure_structural_fields
from content_generator.core.product_truth import product_truth_findings
from content_generator.prompts.threads import accept_threads_regen
from content_generator.publisher import facebook as fb
from content_generator.publisher import meta_graph
from content_generator.publisher import threads
from content_generator.publisher import youtube
from content_generator.scheduler import retry_unposted as ru
from content_generator.scheduler.daily import _apply_regeneration, _schema_issues


def _keys(label: str, piece: dict) -> list[str]:
    prompt = scratch_prompt(label, piece, "below 8", 8.0, "brand")
    raw = prompt.split("Return ONE JSON object with these keys: ", 1)[1]
    return json.loads(raw.split(".", 1)[0])


def test_editorial_and_fallback_gates_stay_at_8():
    assert PASS_FLOOR == 8.0
    assert PASS_THRESHOLD == 8.0
    assert EDITORIAL_THRESHOLD == 8.0


def test_scratch_prompt_asks_for_the_native_fields():
    stub = {"type": "instagram_post", "needs_regen": True, "featured_product": "Ultra Blend"}
    instagram = _keys("instagram_post", dict(stub, type="instagram_post"))
    for key in ("caption", "comment_trigger", "save_trigger", "share_trigger", "hashtags"):
        assert key in instagram
    threads_keys = _keys("threads_post", dict(stub, type="threads_post"))
    assert "text" in threads_keys
    short_keys = _keys("yt_short", dict(stub, type="yt_short"))
    for key in ("product", "tagline", "scenes"):
        assert key in short_keys


def test_threads_regen_rejects_an_article_and_an_unbroken_overlong_line():
    assert accept_threads_regen({"text": "a" * 40, "blog_post": "article"}) is None
    assert accept_threads_regen({"text": "a" * 600}) is None
    native = (
        "Turn the jar.\n\n"
        "The label lists the blend before you brew it. Reply with the first word."
    )
    accepted = accept_threads_regen({"text": native}, {"featured_product": "Ultra Blend"})
    assert accepted["text"] == native
    assert accepted["featured_product"] == "Ultra Blend"
    stored = _apply_regeneration("threads_post", {"featured_product": "Ultra Blend"}, {"text": "a" * 600})
    assert stored is None
    kept = _apply_regeneration("threads_post", {"featured_product": "Ultra Blend"}, {"text": native})
    assert kept["text"].startswith("Turn the jar.")
    assert _schema_issues("threads_post", {"text": ""}) == ["threads text is required"]
    assert _schema_issues("threads_post", {"text": "x" * 481}) == ["threads text is over 480 characters"]


def test_threads_length_fit_always_ends_inside_the_gate():
    piece = {"text": ("word " * 160).strip()}
    assert "." not in piece["text"]
    _fit_threads_length(piece)
    assert len(piece["text"]) <= 480
    assert piece["text"]


def test_structural_defaults_do_not_reintroduce_anti_chicory_copy():
    piece = ensure_structural_fields(
        {
            "type": "facebook_post",
            "featured_product": "Ultra Blend",
            "body": "Ultra Blend is 70% coffee and 30% chicory.",
        },
        "facebook_post",
    )
    packed = json.dumps(piece)
    assert "NoChicory" not in packed
    assert "disguised" not in packed.lower()
    assert product_truth_findings(piece.get("body") or "", "Ultra Blend") == []


def test_yt_short_apply_rejects_a_schema_miss_and_keeps_a_repairable_short():
    assert _apply_regeneration("yt_short", {"featured_product": "Ultra Blend"}, {"product": "only"}) is None
    scenes = [
        {
            "scene": i,
            "type": "problem",
            "duration_s": 2,
            "on_screen": f"line {i} on the jar",
            "spoken": f"line {i} spoken on the jar",
            "visual_direction": "Hold on the line already written.",
        }
        for i in range(1, 6)
    ]
    kept = _apply_regeneration(
        "yt_short",
        {"featured_product": "Ultra Blend"},
        {"featured_product": "Ultra Blend", "hook": "Turn the jar over now", "scenes": scenes},
    )
    assert kept["product"] == "Ultra Blend"
    assert kept["tagline"]
    assert len(kept["scenes"]) >= 5


def test_graph_post_puts_the_token_in_the_header(monkeypatch):
    seen = {}

    class Response:
        status_code = 200

        def json(self):
            return {"id": "1"}

    def request(method, url, params=None, data=None, headers=None, timeout=None, **kwargs):
        seen.update(method=method, url=url, params=params, data=data, headers=headers)
        return Response()

    monkeypatch.setattr("requests.request", request)
    meta_graph.graph_request(
        "POST",
        "https://graph.facebook.com/v21.0/me/media",
        {"access_token": "tok-secret", "caption": "hi"},
    )
    assert seen["data"]["caption"] == "hi"
    assert "access_token" not in seen["data"]
    assert seen["headers"]["Authorization"] == "Bearer tok-secret"
    assert "tok-secret" not in seen["url"]
    assert not seen["params"]


def test_threads_token_stays_out_of_the_url_and_the_error(monkeypatch):
    token = "threads-secret-token"
    seen = []

    class Body:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(req, timeout=None):
        seen.append(req.full_url)
        assert token not in req.full_url
        assert req.get_header("Authorization") == f"Bearer {token}"
        if req.data and b"text=" in req.data:
            assert token.encode() not in req.data
            return Body({"id": "container-1"})
        if "fields=permalink" in req.full_url:
            return Body({"permalink": "https://www.threads.net/t/abc"})
        return Body({"status": "FINISHED"})

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert threads.create_thread_container("user-1", token, "Turn the jar and read the label.") == "container-1"
    assert threads.get_container_status("container-1", token) == "FINISHED"
    assert threads.get_thread_permalink("post-1", token) == "https://www.threads.net/t/abc"
    assert seen

    def boom(req, timeout=None):
        err = urllib.error.HTTPError(req.full_url, 400, "bad", {}, None)
        err.read = lambda: f"leaked {token} in the body".encode()
        raise err

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setenv("THREADS_USER_ID", "user-1")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", token)
    monkeypatch.setattr(threads, "is_configured", lambda: True)
    monkeypatch.setattr(
        "content_generator.publisher.prepublish_gate.authorize_publish",
        lambda *args, **kwargs: {"allowed": True},
    )
    result = threads.post_content({"threads_post": {"text": "Turn the jar and read the label today."}})
    assert result["success"] is False
    assert token not in result["error"]


def test_threads_zero_interval_poll_stops():
    calls = {"n": 0}

    def status(container_id, token):
        calls["n"] += 1
        return "IN_PROGRESS"

    try:
        threads.wait_for_container(
            "container-1", "token", timeout_s=30, interval_s=0, status_fn=status, sleep=lambda _s: None,
        )
    except TimeoutError as exc:
        assert "container-1" in str(exc)
    else:
        raise AssertionError("zero interval should time out")
    assert calls["n"] == 1


def test_facebook_derived_page_token_is_masked(monkeypatch, capsys):
    derived = "derived-page-secret"

    class Response:
        def __init__(self, body):
            self.status_code = 200
            self._body = body

        def json(self):
            return self._body

    def get(url, params=None, headers=None, timeout=None):
        if str(url).endswith("/me"):
            return Response({"id": "user-9"})
        return Response({"access_token": derived})

    monkeypatch.setattr("requests.get", get)
    assert fb.resolve_page_access_token("page-1", "user-token") == derived
    leftover = capsys.readouterr().out.replace(f"::add-mask::{derived}", "")
    assert derived not in leftover


def test_youtube_upload_resumes_one_session_and_hides_tokens(monkeypatch, caplog, tmp_path):
    video = tmp_path / "short.mp4"
    video.write_bytes(b"x" * 80)
    access = "ya-access-secret"
    refresh = "ya-refresh-secret"
    posts = []
    puts = []

    class Response:
        def __init__(self, code, headers=None, body=None):
            self.status_code = code
            self.headers = headers or {}
            self._body = body or {}
            self.text = ""

        def json(self):
            return self._body

    def post(url, headers=None, json=None, data=None, timeout=None):
        posts.append(url)
        return Response(200, {"Location": "https://upload.example/session-1"})

    def put(url, headers=None, data=None, timeout=None):
        puts.append((url, (headers or {}).get("Content-Range")))
        if len(puts) == 1:
            return Response(308, {"Range": "bytes=0-19"})
        if len(puts) == 2:
            return Response(503)
        return Response(200, body={"id": "video-1"})

    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("requests.put", put)
    result = youtube._upload_video(access, str(video), "Turn the jar", "Read the label.", ["purity"])
    assert result["success"] is True
    assert result["video_id"] == "video-1"
    assert len(posts) == 1
    assert len({url for url, _range in puts}) == 1
    assert access not in json.dumps(result)

    def fail_put(url, headers=None, data=None, timeout=None):
        return Response(400, body={"error": {"message": f"nope {access}"}})

    monkeypatch.setattr("requests.put", fail_put)
    failed = youtube._upload_video(access, str(video), "Turn the jar", "Read the label.", ["purity"])
    assert access not in failed["error"]

    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "ya-client-secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", refresh)

    def token_post(url, data=None, timeout=None, **kwargs):
        return Response(400, body={"error_description": f"invalid {refresh}", "error": "invalid_grant"})

    monkeypatch.setattr("requests.post", token_post)
    with caplog.at_level("WARNING"):
        assert youtube._refresh_access_token() is None
    assert refresh not in caplog.text
    assert "ya-client-secret" not in caplog.text


def test_native_short_is_not_a_reel_and_retry_renders_one(monkeypatch, tmp_path):
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(tmp_path))
    reel = tmp_path / "reel_1_day1_2026-11-07.mp4"
    reel.write_bytes(b"reel")
    content = {"date": "2026-11-07", "day_number": 1, "yt_short": {"product": "Ultra Blend"}}
    assert youtube.find_native_short(content) is None
    assert youtube._find_video(content) == str(reel)

    calls = {}

    def build(piece, day, label="short_video", on_date=None):
        calls["on_date"] = on_date
        path = tmp_path / "short_video_day1_2026-11-07_cinematic.mp4"
        path.write_bytes(b"short")
        return str(path)

    monkeypatch.setattr("content_generator.creative.short_video.build_short_video", build)
    assert ru.ensure_yt_video(content) is True
    assert calls["on_date"] == "2026-11-07"
    assert "cinematic" in (youtube.find_native_short(content) or "")


def _live_records(*missing_platforms: str) -> list[dict]:
    live = "VERIFIED_LIVE"
    rows = [{"slot": slot, "platform": platform, "status": live} for slot, platform in (
        ("morning", "instagram_story"),
        ("morning", "facebook"),
        ("generate", "linkedin"),
        ("generate", "youtube"),
        ("generate", "threads"),
    )]
    rows.append({"slot": "morning", "platform": "instagram", "status": live, "asset": "instagram_post"})
    rows.append({"slot": "morning", "platform": "instagram", "status": live, "asset": "carousel"})
    rows.append({"slot": "morning", "platform": "instagram_video", "status": live, "asset": "growth_reel"})
    rows.append({"slot": "evening", "platform": "instagram_video", "status": live, "asset": "reel_1"})
    return [row for row in rows if row["platform"] not in missing_platforms]


def test_regen_cap_drops_exhausted_native_targets_and_keeps_open_ones():
    content = {
        "mandatory_regen_rounds": {"facebook_post": 12, "threads_post": 3, "yt_short": 12},
        "facebook_post": {"ladder_exhausted": True, "held": True, "hold_reason": "FALLBACK LADDER EXHAUSTED: 6.0"},
        "threads_post": {"text": "Turn the jar.", "needs_regen": True},
        "yt_short": {"held": True, "ladder_exhausted": True, "hold_reason": "FALLBACK LADDER EXHAUSTED: 6.0"},
    }
    assert ru.regen_cap_blocks_target(content, "facebook")
    assert ru.regen_cap_blocks_target(content, "youtube")
    assert not ru.regen_cap_blocks_target(content, "threads")
    when = dt.datetime(2026, 11, 7, 12, 7)
    records = _live_records("facebook", "threads", "youtube")
    pending = ru.pending_targets(when, records=records, pack_exists=True, content=content)
    assert "facebook" not in pending
    assert "youtube" not in pending
    assert "threads" in pending
    unchanged = ru.pending_targets(when, records=records, pack_exists=True)
    assert "facebook" in unchanged
    assert "youtube" in unchanged
    assert "threads" in unchanged

def test_secret_mask_only_emits_actions_command_in_ci(monkeypatch, capsys):
    from content_generator.publisher.secret_mask import mask_secret

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    mask_secret("local-secret")
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    mask_secret("ci-secret")
    assert capsys.readouterr().out == "::add-mask::ci-secret\n"
