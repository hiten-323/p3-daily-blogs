"""Per-post learning loop: real metrics -> per-platform reuse/retire lessons."""
from __future__ import annotations

import datetime as dt
import json

from content_generator.analytics import insights_fetcher, platform_learning, post_outcomes
from content_generator.prompts.growth_engine import platforms

NOW = dt.datetime(2026, 11, 15, 6, 0, tzinfo=dt.timezone.utc)


def _post(platform, day, hook, window, metrics, hours_ago=30, media="m"):
    return {
        "platform": platform, "asset_id": f"{platform}_day{day}", "media_id": f"{media}{day}{platform}",
        "hook": hook, "format": "x",
        "published_at": (NOW - dt.timedelta(hours=hours_ago)).isoformat(),
        "measurement_snapshots": [{"window": window, "metrics": metrics}] if metrics else [],
    }


def _content(day, **pieces):
    return {"day_number": day, **pieces}


def test_instagram_without_insights_scope_still_measures_likes_and_comments(monkeypatch):
    insights_fetcher._reset_circuit()
    insights_fetcher._PUBLIC_ONLY_NOTED["done"] = True

    def fake(path, params, bypass_circuit=False):
        if path.endswith("/insights"):
            insights_fetcher._note_failure(path, "(#10) Application does not have permission for this action")
            return None
        return {"like_count": 7, "comments_count": 2, "media_product_type": "FEED"}

    monkeypatch.setattr(insights_fetcher, "_graph_get", fake)
    assert insights_fetcher._fetch_media_insights("123") == {"likes": 7, "comments": 2}
    insights_fetcher._reset_circuit()


def test_early_and_18h_windows_are_due_on_same_day_slot_runs():
    published = dt.datetime(2026, 11, 14, 7, 0, 0)
    post = {"published_at": published.isoformat(), "measurement_snapshots": []}
    # 09:53 morning slot (~3h later) -> same-day early read
    assert insights_fetcher._next_due_window(post, published + dt.timedelta(hours=3)) == ("early", 2)
    # next day's 06:13 generate run (~23h later) now gets the 24h read
    post = {"published_at": published.isoformat(), "measurement_snapshots": [{"window": "early"}]}
    assert insights_fetcher._next_due_window(post, published + dt.timedelta(hours=23)) == ("24h", 24)


def test_early_snapshot_is_stored_but_never_a_learning_sample(tmp_path, monkeypatch):
    posts_path = tmp_path / "published_posts.json"
    published = (NOW - dt.timedelta(hours=4)).isoformat()
    posts_path.write_text(json.dumps([{
        "platform": "threads", "asset_id": "threads_day1", "media_id": "t1", "published_at": published,
        "measurement_snapshots": [],
    }]), encoding="utf-8")
    monkeypatch.setattr(platform_learning, "POSTS_PATH", posts_path)
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "x")
    monkeypatch.setattr(platform_learning, "_fetch_threads", lambda mid: {"views": 40, "likes": 2})
    recorded = []
    monkeypatch.setattr("content_generator.core.learning_engine.record_performance",
                        lambda **kw: recorded.append(kw))
    result = platform_learning.fetch_pending_platform_metrics(now=NOW)
    rows = json.loads(posts_path.read_text(encoding="utf-8"))
    assert result["snapshots"] == 1
    assert rows[0]["measurement_snapshots"][0]["window"] == "early"
    assert recorded == []


def test_facebook_drops_unsupported_shares_field_instead_of_losing_counts(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "x")
    calls = []

    def fake_meta(object_id, token, fields):
        calls.append(fields)
        if "shares" in fields:
            platform_learning._LAST_HTTP_ERROR["detail"] = "(#100) Tried accessing nonexisting field (shares)"
            return None
        return {"likes": {"summary": {"total_count": 5}}, "comments": {"summary": {"total_count": 1}}}

    monkeypatch.setattr(platform_learning, "_meta_get", fake_meta)
    monkeypatch.setattr(platform_learning, "_request_json", lambda *a, **k: None)
    assert platform_learning._fetch_facebook("p_1") == {"likes": 5, "comments": 1}
    assert len(calls) == 2


def test_facebook_missing_permission_is_a_named_block(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "x")

    def fake_meta(object_id, token, fields):
        platform_learning._LAST_HTTP_ERROR["detail"] = "requires the 'pages_read_engagement' permission"
        return None

    monkeypatch.setattr(platform_learning, "_meta_get", fake_meta)
    metrics, status = platform_learning._fetch_platform_metrics(
        {"platform": "facebook", "media_id": "p_1"})
    assert metrics is None and status == "missing_pages_read_engagement_permission"


def test_youtube_public_view_count_parser():
    html = 'x "videoDetails":{"videoId":"abc","title":"t","viewCount":"1234","author":"p"} y'
    assert platform_learning.parse_youtube_public_stats(html) == {"views": 1234}
    assert platform_learning.parse_youtube_public_stats("nothing") is None


def test_youtube_upload_only_scope_falls_back_to_public_views(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(platform_learning, "_youtube_access_token", lambda: "tok")

    def forbidden(url, headers=None):
        platform_learning._LAST_HTTP_ERROR["detail"] = "Request had insufficient authentication scopes."
        return None

    monkeypatch.setattr(platform_learning, "_request_json", forbidden)
    monkeypatch.setattr(platform_learning, "_fetch_youtube_public", lambda mid: {"views": 88})
    assert platform_learning._fetch_youtube("vid") == {"views": 88}


def test_outcomes_join_pieces_and_name_winning_and_losing_templates():
    content = {}
    posts = []
    for day, template, views in ((1, "fast_cut_curiosity", 900), (2, "fast_cut_curiosity", 1000),
                                 (3, "pov_ritual", 100), (4, "pov_ritual", 120), (5, "myth_vs_fact", 400)):
        hook = f"Hook number {day} about a very specific coffee moment {template}"
        content[day] = _content(day, growth_reel={"hook": hook, "ad_template_id": template,
                                                  "angle": f"angle{day % 2}", "editorial_score": 8.5})
        posts.append(_post("instagram", day, hook, "24h", {"views": views, "likes": views // 50}))
    result = post_outcomes.build_outcomes(NOW, posts=posts, content_by_day=content)
    ig = result["platforms"]["instagram"]
    assert ig["ranked"] == 5
    assert all(r["label"] == "growth_reel" for r in result["posts"])
    assert any(w["value"] == "fast_cut_curiosity" and w["dimension"] == "template" for w in ig["winners"])
    assert any(l["value"] == "pov_ritual" for l in ig["losers"])
    scores = post_outcomes.template_scores(data=result)
    assert scores["fast_cut_curiosity"]["ratio"] > scores["pov_ritual"]["ratio"]
    block = post_outcomes.prompt_block("growth_reel", {"platforms": result["platforms"], "lookback_days": 30})
    assert "REUSE" in block and "RETIRE" in block and "fast_cut_curiosity" in block


def test_outcomes_never_compare_different_windows_or_bases():
    posts = [
        _post("threads", 1, "a", "early", {"views": 5}),
        _post("threads", 2, "b", "7d", {"views": 500}),
        _post("threads", 3, "c", "7d", {"likes": 3}),
    ]
    result = post_outcomes.build_outcomes(NOW, posts=posts, content_by_day={})
    assert all(r["relative"] is None for r in result["posts"])  # no cohort reaches 3 posts


def test_outcomes_report_measurement_gaps_instead_of_zeros():
    posts = [_post("instagram", 1, "h", None, None)]
    posts[0]["measurement_status"] = "pending"
    result = post_outcomes.build_outcomes(NOW, posts=posts, content_by_day={})
    ig = result["platforms"]["instagram"]
    assert ig["measured"] == 0 and ig["unmeasured_statuses"] == {"pending": 1}
    assert any("instagram_manage_insights" in g for g in ig["gaps"])


def test_archetype_label_is_not_treated_as_a_hook():
    piece = {"chosen_hook": "Direct Accusation", "hook_text": "certainty_check"}
    assert post_outcomes.piece_hook(piece) == ""
    piece["hook"] = "Most jars hide the ratio in tiny print."
    assert post_outcomes.piece_hook(piece) == "Most jars hide the ratio in tiny print."


def test_platform_prompt_includes_real_outcomes(monkeypatch):
    monkeypatch.setattr(post_outcomes, "load", lambda: {"lookback_days": 30, "platforms": {"threads": {
        "posts": 4, "measured": 4, "ranked": 4, "metrics_seen": ["views"],
        "winners": [{"dimension": "angle", "value": "myth vs fact", "ratio": 1.9, "n": 3, "provisional": True}],
        "losers": [], "top_posts": [], "bottom_posts": [], "gaps": [],
    }}})
    text = platforms._real_outcomes("threads_post")
    assert "LEARNED FROM OUR REAL THREADS POSTS" in text and "myth vs fact" in text
