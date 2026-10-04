"""
LinkedIn and YouTube post only when the piece is in approved_assets.

Run 37183964339 approved ['reel_1', 'carousel'], rejected yt_short and
linkedin_post, and still uploaded the Short and attempted the LinkedIn post.
A skip is not an attempt: it must not fail the run or the publish verification.
"""
import logging

import pytest

from content_generator.publisher import dispatcher, linkedin, youtube
from content_generator.scheduler.daily import _do_publish


def _score(overall, verdict):
    return {
        "overall": overall,
        "verdict": verdict,
        "shareability": overall,
        "saveability": overall,
        "emotion_pull": overall,
        "hook_strength": overall,
        "brand_clarity": overall,
        "feedback": verdict,
    }


def _rejected_linkedin():
    return {
        "hook": "You have been drinking chicory, not coffee.",
        "body": (
            "Most instant jars hide the recipe in the smallest type on the back. "
            "Chicory is a root. Coffee is a bean. The difference is the cup. "
        ) * 3,
        "cta": "Comment PURITY if you want the label checklist.",
        "hashtags": "#PurityBeans #Coffee",
        "editorial_score": _score(4.1, "REJECT"),
    }


def _rejected_short():
    return {
        "hook": "The jar looks the same",
        "script": "Most jars look like coffee. The label is the only place the recipe is written down.",
        "cta": "Read the back of the jar",
        "editorial_error": "brand: ['Missing brand mention']",
    }


def _passing(body):
    return {
        "hook": "Check the label before you brew the next cup.",
        "body": body,
        "script": body,
        "cta": "Shop Purity Beans at p3online.in today.",
        "hashtags": "#PurityBeans #PureCoffee",
        "editorial_score": _score(8.6, "PASS"),
    }


def _block_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network or upload called for a piece that is not approved")

    monkeypatch.setattr(linkedin, "_create_post", boom)
    monkeypatch.setattr(linkedin, "_upload_image", boom)
    monkeypatch.setattr(youtube, "_refresh_access_token", boom)
    monkeypatch.setattr(youtube, "_upload_video", boom)
    monkeypatch.setattr(youtube, "_create_slideshow_short", boom)
    monkeypatch.setenv("LI_API_ACCESS", "token")
    monkeypatch.setenv("LI_AUTHOR_URN", "urn:li:person:test")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")


def _allow_posts(monkeypatch):
    posted = {"linkedin": None, "youtube": None}

    def create(text, image_urn):
        posted["linkedin"] = text
        return {"success": True, "post_id": "li-1", "url": "https://linkedin.example/li-1", "error": None}

    def upload(token, path, title, description, tags):
        posted["youtube"] = title
        return {"success": True, "video_id": "yt-1", "url": "https://www.youtube.com/shorts/yt-1", "error": None}

    monkeypatch.setattr(linkedin, "_create_post", create)
    monkeypatch.setattr(linkedin, "_find_image", lambda content: None)
    monkeypatch.setattr(youtube, "_refresh_access_token", lambda: "token")
    monkeypatch.setattr(youtube, "_find_video", lambda content: "/tmp/approved-short.mp4")
    monkeypatch.setattr(youtube, "_upload_video", upload)
    monkeypatch.setenv("LI_API_ACCESS", "token")
    monkeypatch.setenv("LI_AUTHOR_URN", "urn:li:person:test")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    return posted


def _approve(monkeypatch, *keys):
    def fake(content):
        return {key: (content or {}).get(key) or {"key": key} for key in keys}

    monkeypatch.setattr(
        "content_generator.core.editorial_engine.approved_assets", fake,
    )


@pytest.fixture
def quiet_publish(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_TIMED_SLOTS", "true")
    monkeypatch.setenv("LEARNING_DIR", str(tmp_path / "learning"))
    monkeypatch.setattr(dispatcher, "_PUBLISH_LOG", str(tmp_path / "publish_log.json"))


def _clause(summary, label):
    for part in (summary or "").split(" | "):
        if part.startswith(label):
            return part
    return ""


def test_approved_piece_posts(monkeypatch, quiet_publish):
    _approve(monkeypatch, "linkedin_post", "yt_short")
    posted = _allow_posts(monkeypatch)
    content = {
        "linkedin_post": _passing("APPROVED LINKEDIN BODY about the label on the jar."),
        "yt_short": _passing("APPROVED YOUTUBE SHORT about the label on the jar."),
        "reels": [{"hook": "reel hook", "cta": "reel cta"}],
    }

    li = linkedin.post_content(content, day=276)
    yt = youtube.post_content(content, day=276)
    assert li["success"] is True
    assert yt["success"] is True
    assert "APPROVED LINKEDIN BODY" in posted["linkedin"]
    assert posted["youtube"]

    result = dispatcher.publish_all(content, day_number=276)
    assert result["linkedin"]["success"] is True
    assert result["youtube"]["success"] is True
    assert "linkedin" in result["published_platforms"]
    assert "youtube" in result["published_platforms"]


def test_rejected_piece_skipped(monkeypatch, quiet_publish, caplog):
    _block_network(monkeypatch)
    content = {
        "linkedin_post": _rejected_linkedin(),
        "yt_short": _rejected_short(),
        "reels": [{"hook": "Approved reel hook", "cta": "Shop the reel"}],
        "carousel": {"hook": "Approved carousel"},
    }
    caplog.set_level(logging.INFO)

    li = linkedin.post_content(content, day=276)
    yt = youtube.post_content(content, day=276)
    result = dispatcher.publish_all(content, day_number=276)

    for outcome, piece in ((li, "linkedin_post"), (yt, "yt_short"),
                           (result["linkedin"], "linkedin_post"),
                           (result["youtube"], "yt_short")):
        assert outcome["success"] is False
        assert outcome["attempted"] is False
        assert outcome["error"] == "not_attempted"
        assert outcome["gate"] == "rejected"
        assert outcome["piece"] == piece

    text = caplog.text
    assert "Skipping linkedin_post — rejected; not attempted" in text
    assert "Skipping yt_short — rejected; not attempted" in text
    assert "linkedin" not in result["published_platforms"]
    assert "youtube" not in result["published_platforms"]
    assert "Linkedin" in _clause(result["summary"], "Skipped")
    assert "Youtube" in _clause(result["summary"], "Skipped")
    assert "Linkedin" not in _clause(result["summary"], "Failed")
    assert "Youtube" not in _clause(result["summary"], "Failed")


def test_missing_piece_skipped(monkeypatch, quiet_publish, caplog):
    _block_network(monkeypatch)
    content = {
        "reels": [{"hook": "Approved reel hook", "cta": "Shop the reel"}],
        "carousel": {"hook": "Approved carousel"},
    }
    caplog.set_level(logging.INFO)

    li = linkedin.post_content(content, day=276)
    yt = youtube.post_content(content, day=276)
    result = dispatcher.publish_all(content, day_number=276)

    assert li["gate"] == "missing" and li["attempted"] is False
    assert yt["gate"] == "missing" and yt["attempted"] is False
    assert result["linkedin"]["gate"] == "missing"
    assert result["youtube"]["gate"] == "missing"
    assert result["linkedin"]["error"] == "not_attempted"
    assert result["youtube"]["error"] == "not_attempted"
    text = caplog.text
    assert "Skipping linkedin_post — missing; not attempted" in text
    assert "Skipping yt_short — missing; not attempted" in text
    assert "Linkedin" not in _clause(result["summary"], "Failed")
    assert "Youtube" not in _clause(result["summary"], "Failed")


def test_withheld_piece_is_held_and_not_attempted(monkeypatch, quiet_publish, caplog):
    _approve(monkeypatch)  # gate withholds everything
    _block_network(monkeypatch)
    content = {
        "linkedin_post": _passing("Editor passed this, a later gate withheld it from the set."),
        "yt_short": _passing("Editor passed this short, a later gate withheld it from the set."),
    }
    caplog.set_level(logging.INFO)
    result = dispatcher.publish_all(content, day_number=276)
    assert result["linkedin"]["gate"] == "held"
    assert result["youtube"]["gate"] == "held"
    assert result["linkedin"]["attempted"] is False
    assert result["youtube"]["attempted"] is False
    assert "Skipping linkedin_post — held; not attempted" in caplog.text
    assert "Skipping yt_short — held; not attempted" in caplog.text


def test_publish_skip_does_not_record_an_attempt(monkeypatch, quiet_publish):
    _block_network(monkeypatch)
    attempts = []

    def spy(**kwargs):
        attempts.append(kwargs.get("platform"))
        return {}

    monkeypatch.setattr("content_generator.analytics.telemetry.record_publish", spy)
    dispatcher.publish_all(
        {"linkedin_post": _rejected_linkedin(), "yt_short": _rejected_short()},
        day_number=276,
    )
    assert "linkedin" not in attempts
    assert "youtube" not in attempts


def test_stock_external_posts_need_an_editor_score(monkeypatch, quiet_publish):
    """Run 37192396900 sent a stock linkedin_post because evergreen counted as pre-vetted."""
    from content_generator.core.editorial_engine import (
        EditorialRejectException,
        _editorial_ok,
        approved_assets,
    )
    from content_generator.publisher import shopify_blog
    from content_generator.scheduler.fallback import _from_evergreen

    stock = {"source": "evergreen_distributor", "hook": "Stock", "body": "Stock body"}
    with pytest.raises(EditorialRejectException):
        _editorial_ok("linkedin_post", stock)
    with pytest.raises(EditorialRejectException):
        _editorial_ok("yt_short", {"source": "evergreen_template", "hook": "Stock"})
    with pytest.raises(EditorialRejectException):
        _editorial_ok("blog_post", {"source": "evergreen_distributor", "title": "Stock", "body": "x"})
    assert _editorial_ok("carousel", {"source": "evergreen_template", "hook": "On platform"}) is True
    assert _editorial_ok("instagram_post", {"source": "evergreen_template"}) is True
    scored = dict(stock, editorial_score=_score(9.0, "PASS"))
    assert _editorial_ok("linkedin_post", scored) is True

    content = _from_evergreen(3)
    content["yt_short"] = {"source": "evergreen_template", "hook": "Stock short", "script": "Stock"}
    content["blog_post"] = {"source": "evergreen_distributor", "title": "Stock blog", "body": "Stock"}
    approved = approved_assets(content)
    assert "linkedin_post" not in approved
    assert "yt_short" not in approved
    assert "blog_post" not in approved

    _block_network(monkeypatch)
    monkeypatch.setenv("FORCE_SLOT", "generate")

    def boom(*_args, **_kwargs):
        raise AssertionError("shopify blog posted a stock piece")

    monkeypatch.setattr(shopify_blog, "post_content", boom)
    result = dispatcher.publish_all(content, day_number=3)
    for key in ("linkedin", "youtube", "blog"):
        assert result[key]["attempted"] is False
        assert result[key]["error"] == "not_attempted"
        assert result[key]["gate"] == "rejected"


def test_daily_publish_keeps_rejected_pieces_visible(monkeypatch):
    seen = {}

    def capture(content, day_number=0):
        seen["content"] = content
        return {"published_platforms": [], "summary": "Skipped: Linkedin, Youtube"}

    monkeypatch.setattr(
        "content_generator.core.editorial_engine.get_valid_assets",
        lambda content: ["reel_1", "carousel"],
    )
    monkeypatch.setattr(dispatcher, "publish_all", capture)
    linkedin_post = _rejected_linkedin()
    yt_short = _rejected_short()
    _do_publish(
        {
            "reels": [{"hook": "approved"}],
            "carousel": {"hook": "approved"},
            "linkedin_post": linkedin_post,
            "yt_short": yt_short,
        },
        day_number=276,
    )
    assert seen["content"]["linkedin_post"] == linkedin_post
    assert seen["content"]["yt_short"] == yt_short
