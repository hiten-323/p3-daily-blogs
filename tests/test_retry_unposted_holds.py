"""Locks the 2026-10-21 retry-unposted holds without lowering any gate."""
import io
import urllib.error
import urllib.request
from email.message import EmailMessage

from PIL import Image

from content_generator.creative import premium_cards as pc
from content_generator.creative import visual_gate as vg


def test_held_premium_slide_is_deleted_before_discovery(tmp_path, monkeypatch):
    from content_generator.creative import approved_photos as ap

    leftover = tmp_path / "carousel_slide_6_day293_premium_2026-10-21.jpg"
    leftover.write_bytes(b"jpeg")
    monkeypatch.setattr(ap, "enabled", lambda: True)
    monkeypatch.setattr(ap, "items", lambda *a, **k: [{"primary": True, "type": "cutout", "sku": "bold"}])
    monkeypatch.setattr(
        "content_generator.creative.premium_cards.render_until_pass",
        lambda *a, **k: {
            "held": True,
            "path": str(leftover),
            "visual_gate": {"reasons": ["same_layout_as_last_tile:editorial_top"]},
        },
    )

    assert ap.render(
        "ig_post", 1080, 1350, "Bold coffee", "Read the jar.",
        product="bold", prefer="studio", label="carousel_slide_6",
    ) is None
    assert not leftover.exists()


def test_unverified_premium_record_is_discarded(tmp_path, monkeypatch):
    from content_generator.creative import approved_photos as ap

    path = tmp_path / "carousel_slide_6_day293_premium_2026-10-21.jpg"
    path.write_bytes(b"jpeg")
    monkeypatch.setattr(ap, "enabled", lambda: True)
    monkeypatch.setattr(ap, "items", lambda *a, **k: [{"primary": True, "type": "cutout", "sku": "bold"}])
    monkeypatch.setattr(
        "content_generator.creative.premium_cards.render_until_pass",
        lambda *a, **k: {"path": str(path), "layout": "editorial_top"},
    )
    monkeypatch.setattr("content_generator.creative.visual_gate.remember_layout", lambda *a, **k: None)
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.record_jar_provenance",
        lambda *a, **k: {"asset_real_jar_verified": False},
    )

    assert ap.render(
        "ig_post", 1080, 1350, "Bold coffee", "Read the jar.",
        product="bold", prefer="studio", label="carousel_slide_6",
    ) is None
    assert not path.exists()


def test_discovery_publishes_the_verified_sibling_only(tmp_path, monkeypatch):
    from content_generator.publisher.instagram import _find_carousel_images

    creative = tmp_path / "creative"
    creative.mkdir()
    today = "2026-10-21"
    premium = creative / f"carousel_slide_6_day293_premium_{today}.jpg"
    fallback = creative / f"carousel_slide_6_day293_{today}.jpg"
    premium.write_bytes(b"premium")
    fallback.write_bytes(b"fallback")
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(creative))

    def verify(path):
        name = path.rsplit("/", 1)[-1]
        return {"verified": name == fallback.name}

    monkeypatch.setattr("content_generator.creative.jar_provenance.verify_jar_provenance", verify)
    found = _find_carousel_images({"date": today, "day_number": 293, "carousel": {"title": "t"}})
    assert found == [str(fallback)]


def test_discovery_keeps_every_file_when_none_are_verified(tmp_path, monkeypatch):
    from content_generator.publisher.instagram import _find_carousel_images

    creative = tmp_path / "creative"
    creative.mkdir()
    today = "2026-10-21"
    for name in (
        f"carousel_slide_6_day293_premium_{today}.jpg",
        f"carousel_slide_6_day293_{today}.jpg",
    ):
        (creative / name).write_bytes(b"x")
    monkeypatch.setenv("CREATIVE_OUTPUT_DIR", str(creative))
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_jar_provenance",
        lambda path: {"verified": False, "reason": "unregistered_image"},
    )
    found = _find_carousel_images({"date": today, "day_number": 293, "carousel": {"title": "t"}})
    assert len(found) == 2


def test_verified_premium_is_preferred_over_the_fallback(tmp_path, monkeypatch):
    from content_generator.publisher.instagram import _prefer_verified_slide

    premium = str(tmp_path / "carousel_slide_1_day293_premium_2026-10-21.jpg")
    fallback = str(tmp_path / "carousel_slide_1_day293_2026-10-21.jpg")
    monkeypatch.setattr(
        "content_generator.creative.jar_provenance.verify_jar_provenance",
        lambda path: {"verified": True},
    )
    assert _prefer_verified_slide([fallback, premium]) == [premium]


def test_content_pack_threads_string_is_not_empty_content():
    from content_generator.core.brand_validator import validate_asset
    from content_generator.core.piece_integrity import ensure_structural_fields

    native = (
        "Read the jar: Purica by Purity Beans is pure Arabica, and the ingredient "
        "list is the whole story. That is the post."
    )
    pack = {
        "facebook_post": {"caption": "A different platform."},
        "carousel": {"slides": [{"heading": "one"}]},
        "threads_post": native,
    }
    piece = ensure_structural_fields(pack, "threads_post")
    _ok, issues = validate_asset("threads_post", piece)
    assert "Empty content" not in issues
    assert piece["text"].startswith("Read the jar:")


def test_existing_threads_text_is_not_replaced():
    from content_generator.core.piece_integrity import ensure_structural_fields

    original = "Already written native copy about reading the Bold jar and the label on the front."
    piece = {"text": original, "threads_post": "A different string that must not replace the text field at all."}
    out = ensure_structural_fields(piece, "threads_post")
    assert out["text"].startswith("Already written")


def test_carousel_caption_is_not_promoted_into_threads():
    from content_generator.core.brand_validator import validate_asset
    from content_generator.core.piece_integrity import ensure_structural_fields

    piece = ensure_structural_fields(
        {"caption": "A long carousel caption that is not a native Threads post and must stay out.", "slides": [{}]},
        "threads_post",
    )
    _ok, issues = validate_asset("threads_post", piece)
    assert "Empty content" in issues
    assert "text" not in piece


def test_brand_block_does_not_offer_the_banned_per_cup_price():
    from content_generator.core.fallback_ladder import scratch_prompt
    from content_generator.prompts.brand import brand_block

    text = brand_block()
    assert "Rs18/cup" not in text
    assert "₹18" not in text
    assert "omit every per-cup price and cup count" in text
    assert "70% coffee" in text
    scratch = scratch_prompt("facebook_post", {"featured_product": "Bold"}, "per-cup", 8.0, text)
    assert "omit the figure" in scratch
    assert "Rs18/cup" not in scratch


def test_bold_day_drops_per_cup_sentences_and_the_gate_still_rejects_them():
    from content_generator.core.product_truth import omit_per_cup_for_non_ultra, product_truth_findings

    bold = {
        "caption": "Bold is pure coffee. About ₹5 a cup and 66 cups from one jar. Shop the jar.",
        "editorial_error": "brand: Per-cup price/yield is verified only for Ultra Blend",
    }
    omit_per_cup_for_non_ultra(bold, "Bold")
    assert "₹5" not in bold["caption"]
    assert "66 cups" not in bold["caption"]
    assert "Bold is pure coffee" in bold["caption"]
    assert "Per-cup" in bold["editorial_error"]

    named = {"caption": "Bold is today's jar. Ultra Blend is about ₹5 a cup when that jar is the one you mean."}
    omit_per_cup_for_non_ultra(named, "Bold")
    assert "Ultra Blend is about ₹5 a cup" in named["caption"]

    ultra = {"caption": "About ₹5 a cup from this jar."}
    omit_per_cup_for_non_ultra(ultra, "Ultra Blend")
    assert ultra["caption"] == "About ₹5 a cup from this jar."

    findings = product_truth_findings("Bold is about ₹5 a cup.", featured="Bold")
    assert any("Per-cup price/yield" in f["reason"] for f in findings)


def test_gemini_image_models_skip_retired_ids(monkeypatch):
    from content_generator.creative import gemini_scene as gs

    gs._DEAD_IMAGE_MODELS.clear()
    monkeypatch.delenv("GEMINI_IMAGE_MODEL", raising=False)
    order = gs._image_model_order()
    assert order[0] == "gemini-nano-banana-2.1"
    assert "gemini-2.0-flash-exp" not in order

    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-exp")
    assert gs._image_model_order()[0] == "gemini-nano-banana-2.1"

    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    assert gs._image_model_order()[0] == "gemini-3.1-flash-image"
    gs._DEAD_IMAGE_MODELS.clear()


def test_gemini_404_retires_the_model_and_tries_the_next(monkeypatch):
    from content_generator.creative import gemini_scene as gs

    gs._DEAD_IMAGE_MODELS.clear()
    monkeypatch.delenv("GEMINI_IMAGE_MODEL", raising=False)
    calls = []

    class _Body:
        def read(self):
            return b'{"candidates":[{"content":{"parts":[]}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if "gemini-nano-banana-2.1" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", EmailMessage(), io.BytesIO(b""))
        return _Body()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = gs._fetch_scene("test-key", b"{}")
    assert data["candidates"]
    assert "gemini-nano-banana-2.1" in gs._DEAD_IMAGE_MODELS
    assert any("gemini-3.1-flash-image" in url for url in calls)

    calls.clear()
    again = gs._fetch_scene("test-key", b"{}")
    assert again["candidates"]
    assert all("gemini-nano-banana-2.1" not in url for url in calls)
    gs._DEAD_IMAGE_MODELS.clear()


def test_story_cta_pill_does_not_overlap_the_jar(tmp_path):
    cta = "FOLLOW @PUREPANTRYPROVISIONS"
    assert vg.AESTHETIC_PASS == 8.0
    # Stories never use split_left; the CTA frame is one of these three.
    for layout in ("hero_center", "editorial_top", "diagonal_band"):
        meta = pc.render(
            "bold", "Read the jar", "Pure coffee.",
            width=1080, height=1920, cta=cta, layout=layout, seed=1,
            out_path=str(tmp_path / f"{layout}.jpg"),
        )
        pill = pc.cta_pill_box(1080, 1920, cta)
        assert meta["jar_box"][3] <= pill[1]
        assert not vg._overlap(meta["jar_box"], pill, pad=-4)
        reasons, _ = vg.heuristic_checks(Image.open(meta["path"]), meta)
        assert not any(r.startswith("text_overlaps_jar") for r in reasons), (layout, reasons)
