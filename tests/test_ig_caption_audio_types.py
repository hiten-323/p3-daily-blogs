from content_generator.publisher.instagram import _assemble_caption


def test_audio_dict():
    c = _assemble_caption("Fresh brew", {"audio": {"recommendation": "Lo-fi beat"}})
    assert "🎵 Audio: Lo-fi beat" in c


def test_audio_str():
    c = _assemble_caption("Fresh brew", {"audio": "Trending lo-fi"})
    assert "🎵 Audio: Trending lo-fi" in c


def test_audio_missing_or_odd():
    for a in (None, "", 5, ["x"]):
        c = _assemble_caption("Fresh brew", {"audio": a})
        assert "🎵" not in c
