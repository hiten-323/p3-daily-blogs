"""Owner kill switch: paused Instagram publishes nothing and burns no retries."""
import json

import pytest

from content_generator.core import instagram_pause as ip


@pytest.fixture
def pause_file(tmp_path, monkeypatch):
    f = tmp_path / "instagram_pause.json"
    monkeypatch.setenv("INSTAGRAM_PAUSE_FILE", str(f))
    monkeypatch.delenv("INSTAGRAM_PUBLISH_PAUSED", raising=False)
    return f


def test_file_controls_pause(pause_file):
    assert ip.instagram_paused() is False          # missing file -> not paused
    pause_file.write_text(json.dumps({"paused": True}))
    assert ip.instagram_paused() is True
    pause_file.write_text(json.dumps({"paused": False}))
    assert ip.instagram_paused() is False


def test_env_overrides_file(pause_file, monkeypatch):
    pause_file.write_text(json.dumps({"paused": False}))
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "true")
    assert ip.instagram_paused() is True
    pause_file.write_text(json.dumps({"paused": True}))
    monkeypatch.setenv("INSTAGRAM_PUBLISH_PAUSED", "false")
    assert ip.instagram_paused() is False


def test_unreadable_file_fails_safe(pause_file):
    pause_file.write_text("{not json")
    assert ip.instagram_paused() is True


def test_repo_switch_is_on():
    with open(ip.PAUSE_FILE, encoding="utf-8") as fh:
        assert json.load(fh)["paused"] is True


def test_publishers_never_call_meta_when_paused(pause_file, monkeypatch):
    pause_file.write_text(json.dumps({"paused": True}))
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "x")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", "1")
    import requests
    def boom(*a, **k):
        raise AssertionError("network call while paused")
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(requests, "get", boom)
    from content_generator.publisher import instagram as ig
    for res in (
        ig.post_content({}, day=1), ig.post_story({}, day=1), ig.post_reel_video("u", "c"),
        ig._post_single_image("x.jpg", "c"), ig._post_carousel(["a.jpg", "b.jpg"], "c"),
        ig._post_reel_direct_binary("x.mp4", "c"), ig.post_local_story("x.jpg"),
        ig.post_prepared_story("x.jpg"), ig._publish_container("1", "1", "t"),
    ):
        assert res["success"] is False and res["error"] == "instagram_paused"
        assert res["attempted"] is False and res["skipped"] is True


def test_retry_unposted_drops_instagram_targets(pause_file):
    from content_generator.scheduler import retry_unposted as ru
    pause_file.write_text(json.dumps({"paused": True}))
    t = ru.active_targets()
    assert not (set(t) & ru.INSTAGRAM_TARGETS)
    assert {"facebook", "linkedin", "youtube", "threads"} <= set(t)
    assert ru.unposted_targets([], 23) and not (set(ru.unposted_targets([], 23)) & ru.INSTAGRAM_TARGETS)
    pause_file.write_text(json.dumps({"paused": False}))
    assert ru.INSTAGRAM_TARGETS <= set(ru.active_targets())
