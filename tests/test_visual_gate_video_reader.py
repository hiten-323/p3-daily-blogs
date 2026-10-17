import os
import sys
import types

import numpy as np


class FakeFrameImage:
    def save(self, path, quality=90):
        with open(path, "wb") as f:
            f.write(b"fake-frame")


class FakeReader:
    def __init__(self):
        self.closed = False
        self.indices = []

    def count_frames(self):
        return 25

    def get_data(self, index):
        self.indices.append(index)
        return np.zeros((4, 4, 3), dtype=np.uint8)

    def close(self):
        self.closed = True


def test_evaluate_video_uses_supported_v2_ffmpeg_reader(monkeypatch, tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from content_generator.creative import visual_gate

    reader = FakeReader()
    captured = {}

    def get_reader(path, format=None):
        captured["path"] = path
        captured["format"] = format
        return reader

    imageio = types.ModuleType("imageio")
    imageio.__path__ = []
    imageio_v2 = types.ModuleType("imageio.v2")
    imageio_v2.get_reader = get_reader
    monkeypatch.setitem(sys.modules, "imageio", imageio)
    monkeypatch.setitem(sys.modules, "imageio.v2", imageio_v2)

    class FakeImage:
        def save(self, path, quality=90):
            with open(path, "wb") as f:
                f.write(b"frame")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    from PIL import Image
    monkeypatch.setattr(Image, "fromarray", lambda frame: FakeImage())
    monkeypatch.setattr(Image, "open", lambda path: FakeImage())
    monkeypatch.setattr(visual_gate, "heuristic_checks", lambda image, meta, recent_layouts=(): ([], {}))
    monkeypatch.setattr(visual_gate, "evaluate", lambda meta, recent_layouts=(), vision=None: {"passed": True, "reasons": [], "metrics": {}})

    video = tmp_path / "sample.mp4"
    video.write_bytes(b"fake-video")
    result = visual_gate.evaluate_video(str(video), samples=3)

    assert captured["format"] == "FFMPEG"
    assert reader.indices == [0, 12, 24]
    assert reader.closed
    assert result["passed"] is True
    assert len(result["frames"]) == 3
    assert not os.path.exists(str(video) + ".gateframe.jpg")
