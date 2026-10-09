from content_generator.pipeline.generator import _has_native_threads_text


def test_threads_native_text_contract_accepts_only_native_copy():
    assert _has_native_threads_text({"angle": "coffee truth", "text": "Check your coffee jar label today."})
    assert _has_native_threads_text({"body": "Read the ingredients on your coffee jar."})
    assert not _has_native_threads_text({"growth_reel": {"caption": "Not a native Threads post"}})
    assert not _has_native_threads_text({"text": "x" * 481})
