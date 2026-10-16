import urllib.error

from content_generator.creative import visual_gate as vg


def _reset():
    vg._DEAD.clear(); vg._LIST_CACHE.clear(); vg._OUTAGE["n"] = 0


def test_bar_unchanged():
    assert vg.AESTHETIC_PASS >= 8.0


def test_chain_order_free_first_nvidia_last():
    names = [n for n, _ in vg.VISION_PROVIDERS]
    assert names[-1] == "nvidia" and "openrouter" in names and names[0] == "gemini"


def test_falls_through_to_next_provider(monkeypatch, tmp_path):
    _reset()
    from PIL import Image
    p = tmp_path / "a.jpg"; Image.new("RGB", (64, 64), (90, 40, 20)).save(p)

    def boom(_):
        raise urllib.error.HTTPError("u", 429, "rate", {}, None)
    monkeypatch.setattr(vg, "VISION_PROVIDERS", [("a", boom), ("b", lambda _: (8.6, []))])
    r = vg.aesthetic_score(str(p))
    assert r["provider"] == "b" and r["score"] == 8.6


def test_outage_fails_fast_and_holds(monkeypatch, tmp_path):
    _reset()
    from PIL import Image
    p = tmp_path / "a.jpg"; Image.new("RGB", (64, 64)).save(p)
    calls = {"n": 0}

    def boom(_):
        calls["n"] += 1
        raise RuntimeError("down")
    monkeypatch.setattr(vg, "VISION_PROVIDERS", [("a", boom)])
    for _ in range(5):
        r = vg.aesthetic_score(str(p))
        assert r["score"] is None
    assert calls["n"] == 2  # stops calling once outage is declared
    assert vg.is_vision_hold({"reasons": ["vision_score_unavailable", "x"]})
    _reset()


def test_parse_rejects_missing_score():
    import pytest
    with pytest.raises(Exception):
        vg._parse("<html>oops</html>")


def test_sse_and_reasoning_parsing(monkeypatch):
    import io
    sse = 'data: {"choices":[{"delta":{"content":"{\\"score\\": 8.4,"}}]}\ndata: {"choices":[{"delta":{"content":" \\"issues\\": []}"}}]}\ndata: [DONE]\n'

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(vg.urllib.request, "urlopen", lambda *a, **k: R(sse.encode()))
    assert vg._openai_vision("https://x.test/v1", "k", "m", "b64")[0] == 8.4
    body = '{"choices":[{"message":{"content":null,"reasoning_content":"ok {\\"score\\": 8.1, \\"issues\\": []}"}}]}'
    monkeypatch.setattr(vg.urllib.request, "urlopen", lambda *a, **k: R(body.encode()))
    assert vg._openai_vision("https://x.test/v1", "k", "m", "b64")[0] == 8.1


def test_render_until_pass_stops_on_vision_hold(monkeypatch):
    from content_generator.creative import premium_cards
    n = {"c": 0}
    monkeypatch.setattr(premium_cards, "render", lambda *a, **k: {"path": "x"})

    def gate(meta, recent_layouts=()):
        n["c"] += 1
        return {"passed": False, "reasons": ["vision_score_unavailable"]}
    out = premium_cards.render_until_pass("bold", "h", gate=gate, max_tries=8)
    assert out.get("held") and n["c"] == 1


def test_sub_repeating_strip_chip_is_dropped(monkeypatch):
    from content_generator.creative import premium_cards
    from content_generator.creative import render_claims as rc
    seen = []
    orig = premium_cards._text
    monkeypatch.setattr(premium_cards, "_text", lambda c, xy, t, *a, **k: (seen.append(t), orig(c, xy, t, *a, **k)))
    premium_cards.render("ultra_blend", "Milk loves it", rc.ULTRA_STRIP, out_path="/tmp/_t_ub.jpg")
    assert not any(rc.ULTRA_STRIP.lower() in str(t).lower() for t in seen)
