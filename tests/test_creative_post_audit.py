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


def test_visual_adaptation_directives_extraction(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)

    audit._save([
        {"recommendations": [
            "raise exposure/background separation; avoid another near-black frame",
            "increase scene/motion change; video is visually static",
            "strengthen the first-frame visual hook in the upper safe zone",
        ]}
    ])
    dirs = audit.get_visual_adaptation_directives()
    assert dirs["boost_exposure"] is True
    assert dirs["boost_motion"] is True
    assert dirs["boost_upper_activity"] is True
    assert dirs["boost_contrast"] is False


def test_multi_platform_copy_audit_rules():
    content = {
        "yt_short": {"title": "Full length title for test", "description": "Quick brewing recipe"},
        "carousel": {"slides": [{"heading": "Slide 1 with length", "body": "Slide content"}]},
        "threads_post": {"body": "This is a statement without any question."},
        "linkedin_post": {"headline": "A" * 150, "body": "Long insight"},
    }
    row = audit.audit_generated_creatives(
        day_number=1,
        generation_id="test_gen",
        image_results={},
        content=content,
    )
    recs = " ".join(row["recommendations"])
    assert "YouTube Short lacks subscribe" in recs
    assert "carousel lacks an explicit save/share cue" in recs
    assert "Threads post needs an open-ended question" in recs
    assert "LinkedIn hook exceeds 140 chars" in recs

