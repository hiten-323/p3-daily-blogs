import json
from pathlib import Path

from PIL import Image, ImageDraw

from content_generator.analytics import creative_post_audit as audit


def test_image_metrics_are_real_not_prompt_only(tmp_path):
    p = tmp_path / "frame.jpg"
    im = Image.new("RGB", (1080, 1080), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((100, 100, 700, 700), fill="black")
    im.save(p)
    m = audit._img(str(p))
    assert m["width"] == 1080
    assert m["height"] == 1080
    assert m["contrast"] > 0


def test_video_failure_is_non_fatal(tmp_path):
    p = tmp_path / "not-a-video.mp4"
    p.write_bytes(b"not a video")
    result = audit._video(str(p))
    assert "error" in result or result["frames_sampled"] >= 0


def test_adaptation_requires_repeated_findings(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)

    rows = [
        {"recommendations": ["increase foreground/background contrast"]},
        {"recommendations": ["increase foreground/background contrast"]},
    ]
    audit._save(rows)
    block = audit.get_adaptation_block()
    assert "increase foreground/background contrast" in block
    assert "heuristic QA" in block


def test_adaptation_does_not_learn_from_single_outlier(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)

    audit._save([
        {"recommendations": ["one-off lighting issue"]},
        {"recommendations": ["different issue"]},
    ])
    assert audit.get_adaptation_block() == ""
