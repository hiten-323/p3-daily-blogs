import pytest


@pytest.fixture(autouse=True)
def _reset_nvidia_model_health():
    """NVIDIA model health is process-wide; keep tests independent."""
    from content_generator.providers import nvidia
    nvidia._reset_model_health()
    yield
    nvidia._reset_model_health()
