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
        ],
         "image_assets": [
            {"platform":"instagram","recommendations":[
                "raise exposure/background separation; avoid another near-black frame",
                "strengthen the first-frame visual hook in the upper safe zone"]}],
         "video_assets": [
            {"platform":"video","recommendations":[
                "increase scene/motion change; video is visually static"]}]}
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




def test_all_current_run_images_are_included(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    creative_dir = tmp_path / "creative"
    creative_dir.mkdir()
    img = Image.new("RGB", (300, 300), "white")
    jar = tmp_path / "real_jar.png"
    img.save(jar)
    render = creative_dir / "unreturned_renderer_asset_2026-10-09.jpg"
    img.save(render)

    from content_generator.creative import jar_provenance
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(tmp_path / "prov.json"))
    jar_provenance.record_jar_provenance(str(render), str(jar), "real_jar")

    row = audit.audit_generated_creatives(
        day_number=4, generation_id="g4", image_results={},
        creative_dir=str(creative_dir), content={},
    )
    assert any(x["path"] == str(render) for x in row["image_assets"])


def test_carousel_slide_copy_is_scanned(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    content = {
        "carousel": {
            "slides": [{"heading": "A useful slide headline", "body": "Save this for the next time you shop."}]
        }
    }
    row = audit.audit_generated_creatives(
        day_number=2, generation_id="g2", image_results={}, content=content,
    )
    assert not any("carousel lacks an explicit save/share cue" in x for x in row["recommendations"])



def test_centered_catalog_directive_changes_real_jar_placement(tmp_path, monkeypatch):
    from content_generator.creative import real_jar_composer

    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    monkeypatch.setattr(real_jar_composer, "_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(audit, "get_visual_adaptation_directives", lambda platform=None: {
        "break_centered_catalog": True,
        "boost_exposure": True,
        "boost_upper_activity": True,
    })

    # Exercise the real composer with the same authentic source inventory that
    # render-safety tests require; the result must retain registered provenance.
    result = real_jar_composer.compose_post_image(
        headline="VISUAL ADAPTATION TEST", body="Authentic jar", day=3, idx=2,
        width=600, height=600, label="adaptation_test",
    )
    assert result and Path(result).exists()
    from content_generator.creative.jar_provenance import verify_jar_provenance
    assert verify_jar_provenance(result)["verified"] is True



def test_visual_pixel_audit_failure_is_explicit():
    result = audit._recs({"error": "decoder failed"}, "instagram")
    assert result
    assert "visual pixel audit failed" in result[0]


def test_video_decode_failure_is_explicit(tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(b"not video bytes")
    result = audit._video(str(p))
    assert result.get("error")
    assert any("visual audit failed" in x for x in result["recommendations"])


def test_renderer_directives_ignore_copy_only_recommendations(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    audit._save([{
        "recommendations": ["carousel lacks an explicit save/share cue for algorithmic distribution"],
        "image_assets": [],
        "video_assets": [],
    }])
    dirs = audit.get_visual_adaptation_directives()
    assert dirs["diversify_palette"] is False
    assert dirs["boost_contrast"] is False


def test_platform_filter_keeps_visual_adaptation_local(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    audit._save([{
        "image_assets": [
            {"platform": "facebook", "recommendations": ["raise exposure/background separation; avoid another near-black frame"]},
            {"platform": "instagram", "recommendations": ["increase foreground/background contrast"]},
        ],
        "video_assets": [],
        "recommendations": [],
    }])
    fb = audit.get_visual_adaptation_directives(platform="facebook")
    ig = audit.get_visual_adaptation_directives(platform="instagram")
    assert fb["boost_exposure"] is True
    assert fb["boost_contrast"] is False
    assert ig["boost_contrast"] is True
    assert ig["boost_exposure"] is False


def test_centered_layout_recommendation_requires_pixel_evidence():
    flat = {"brightness": .5, "contrast": .1, "edge_density": .04,
            "upper_activity": .1, "lower_center_edge_ratio": 1.0,
            "lower_center_edge_density": .02}
    assert not any("focal composition dominates" in x for x in audit._recs(flat, "instagram"))
    centered = dict(flat, lower_center_edge_ratio=2.1, lower_center_edge_density=.04)
    assert any("focal composition dominates" in x for x in audit._recs(centered, "instagram"))



def test_vision_review_is_disabled_without_live_credentials(monkeypatch):
    monkeypatch.setenv("ENABLE_VISION_CREATIVE_AUDIT", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = audit._vision_review([], [])
    assert result["status"] == "skipped_no_api_key"
    assert result["assets"] == []


def test_vision_directives_are_persisted_for_next_render(tmp_path, monkeypatch):
    audit_path = tmp_path / "creative_post_audits.json"
    monkeypatch.setattr(audit, "_PATH", audit_path)
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    image_path = tmp_path / "ig_asset.jpg"
    Image.new("RGB", (200, 200), "white").save(image_path)
    monkeypatch.setattr(audit, "_vision_review", lambda images, videos, content=None: {
        "status": "ok", "model": "mocked", "assets": [{
            "asset": image_path.name, "score": 2, "strengths": [],
            "issues": ["too dark"], "directives": ["boost_exposure", "add_action_texture"]
        }], "portfolio_issues": [], "sampled": []
    })
    monkeypatch.setattr(audit, "_recs", lambda m, platform: [])
    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_jar_provenance",
                        lambda path: {"verified": True, "jar_asset_id": "brand_assets/puritybeans_reference.png"})
    row = audit.audit_generated_creatives(
        day_number=8, generation_id="vision_test",
        image_results={"instagram_post": str(image_path)},
        creative_dir=str(tmp_path), content={},
    )
    assert row["vision_audit"]["status"] == "ok"
    assert "too dark" in row["recommendations"][0] or any("too dark" in x for x in row["recommendations"])
    dirs = audit.get_visual_adaptation_directives(platform="instagram")
    assert dirs["boost_exposure"] is True
    assert dirs["add_action_texture"] is True


def test_vision_failure_is_recorded_and_non_blocking(tmp_path, monkeypatch):
    monkeypatch.setenv("ENABLE_VISION_CREATIVE_AUDIT", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(audit, "_vision_review", lambda images, videos, content=None: {
        "status": "failed_non_blocking", "assets": [], "recommendations": [],
        "error": "TimeoutError: mocked timeout"
    })
    # Ensure audit still returns an auditable record with no generated assets.
    monkeypatch.setattr(audit, "_PATH", tmp_path / "audit.json")
    monkeypatch.setattr(audit, "_DIR", tmp_path)
    row = audit.audit_generated_creatives(
        day_number=9, generation_id="vision_failure_test",
        image_results={}, creative_dir=str(tmp_path), content={},
    )
    assert row["vision_audit"]["status"] == "failed_non_blocking"
