import os

import pytest

# imageio-ffmpeg downloads a binary with no short timeout when this is unset.
if os.path.isfile("/usr/bin/ffmpeg"):
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/usr/bin/ffmpeg")


@pytest.fixture(autouse=True)
def _reset_nvidia_model_health():
    """NVIDIA model health is process-wide; keep tests independent."""
    from content_generator.providers import nvidia
    nvidia._reset_model_health()
    yield
    nvidia._reset_model_health()


import pytest as _pytest_cinematic


@_pytest_cinematic.fixture(autouse=True)
def _legacy_video_path_in_tests(monkeypatch):
    """Legacy reel/short/story tests assert the frame-based path; cinematic has its own tests."""
    monkeypatch.setenv("CINEMATIC_VIDEO", "0")
    monkeypatch.setenv("LLM_MODEL_DISCOVERY", "0")  # no live /models calls in tests
