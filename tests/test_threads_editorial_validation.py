from content_generator.core.brand_validator import validate_asset


def test_threads_native_copy_does_not_require_promotional_link():
    piece = {
        "angle": "COFFEE TRUTH",
        "text": "Unpopular opinion: your coffee jar label tells you more than the front ever will. What does yours list?"
    }
    ok, issues = validate_asset("threads_post", piece)
    assert ok, issues


def test_threads_native_copy_still_rejects_empty_and_overlong_text():
    ok, issues = validate_asset("threads_post", {"text": ""})
    assert not ok
    assert any("Empty content" in issue for issue in issues)
    ok, issues = validate_asset("threads_post", {"text": "Coffee " * 100})
    assert not ok
    assert any("480 characters" in issue for issue in issues)
