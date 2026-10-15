import json, os, shutil
import pytest
from content_generator.creative import approved_photos as ap

M = json.load(open("brand_assets/approved_photos/manifest.json"))



@pytest.fixture(autouse=True)
def _offline_visual_gate(monkeypatch, tmp_path):
    # CI has no vision API key; keep every deterministic visual check but skip the
    # remote vision score here (production still requires it, see test_premium_visuals).
    monkeypatch.setenv("VISUAL_VISION_REQUIRED", "0")
    from content_generator.creative import visual_gate
    monkeypatch.setattr(visual_gate, "_LAYOUT_LOG", str(tmp_path / "visual_layouts.json"))

def test_manifest_schema_and_files():
    assert len(M["items"]) == 27
    for it in M["items"]:
        assert it["sku"] in {"bold", "purica", "purista", "ultra_blend"}
        assert it["size"] in {"50g", "100g"}
        assert it["type"] in {"cutout", "lifestyle", "infographic", "back", "real_photo", "approved_card"}
        assert os.path.exists(os.path.join("brand_assets/approved_photos", it["file"]))
        x0, y0, x1, y1 = it["jar_bbox"]
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def test_ai_renders_blocked():
    for it in M["items"]:
        if it["type"] in ("lifestyle", "infographic"):
            assert it["blocked"] and not it["allowed_surfaces"], it["file"]
            assert it["blocked_reason"]
    for s in ("ig_post", "ig_story", "carousel_cover", "reel_thumb", "blog"):
        assert all(i["type"] in ("cutout", "back", "real_photo", "approved_card") for i in ap.items(s))


def test_bold_tone_is_global_desaturation():
    for it in M["items"]:
        if it["sku"] == "bold" and it["type"] == "cutout" and not it["blocked"]:
            assert "tone" not in it  # usable Bold cutouts are true-colour hi-res
        if it.get("primary"):
            assert "tone" not in it  # hi-res cutout keeps true colours
        if it["sku"] != "bold":
            assert "tone" not in it


def test_tone_is_uniform():
    from PIL import Image
    img = Image.new("RGB", (40, 40), (120, 60, 200))
    out = ap._apply_tone(img, {"saturation": 0.78})
    assert len(set(out.getdata())) == 1  # same pixel in -> same pixel out everywhere


@pytest.mark.parametrize("w,h", [(1080, 1080), (1080, 1350), (1080, 1920)])
def test_every_sku_renders_studio_card_and_passes_qa(w, h, tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    from content_generator.creative.jar_provenance import verify_jar_provenance
    for sku in ("bold", "purica", "purista", "ultra_blend"):
        p = ap.render("ig_post", w, h, "Headline here", "sub", 1, 0, sku, f"{sku}{w}{h}")
        assert p and verify_jar_provenance(p)["verified"]
        assert "cutout" in verify_jar_provenance(p)["jar_asset_id"]


def test_sku_copy_never_gets_other_sku_jar(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    from content_generator.creative.jar_provenance import verify_jar_provenance
    p = ap.render("ig_post", 1080, 1080, "Why Purista?", "", 3, 0, None, "pur")
    assert "/purista/" in verify_jar_provenance(p)["jar_asset_id"].replace("\\", "/")


def test_real_photo_drop_folder_takes_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    real = os.path.join("brand_assets/approved_photos/purica/real")
    dst = os.path.join(real, "zz_test_real.png")
    shutil.copy("brand_assets/approved_photos/purica/purica_100g_cutout_front.png", dst)
    try:
        assert ap.real_photos("purica")[0]["type"] == "real_photo"
        from content_generator.creative.jar_provenance import verify_jar_provenance
        p = ap.render("ig_story", 1080, 1920, "Hi", "", 0, 0, "purica", "realtest")
        assert "/real/" in verify_jar_provenance(p)["jar_asset_id"].replace("\\", "/")
    finally:
        os.remove(dst)
    assert ap.real_photos("purica") == []


@pytest.mark.parametrize("tw,th", [(1080, 1080), (1080, 1350), (1080, 1920)])
def test_crop_keeps_jar_and_all_baked_text(tw, th):
    for it in M["items"]:
        if it["type"] not in ("lifestyle", "infographic"):
            continue
        w, h = it["width"], it["height"]
        box, ok = ap.crop_window(w, h, ap.union(ap.protected_boxes(it)), tw, th)
        if ok:
            for b in ap.protected_boxes(it):
                assert box[0] <= b[0] * w + 1 and box[2] >= b[2] * w - 1
                assert box[1] <= b[1] * h + 1 and box[3] >= b[3] * h - 1


def test_qa_layout_rejects_bad_band():
    assert "overlay_touches_baked_text" in ap.qa_layout((1000, 1000), [(100, 100, 400, 300)], (0, 250, 1000, 350))
    assert "overlay_band_too_tall" in ap.qa_layout((1000, 1000), [], (0, 0, 1000, 300))
    assert "baked_text_cut_off" in ap.qa_layout((1000, 1000), [(900, 0, 1100, 50)], None)


def test_qa_rejects_cut_and_blurry():
    from PIL import Image
    img = Image.new("RGB", (500, 500), (128, 128, 128))
    assert "jar_cut_off" in ap.qa_jar(img, (400, 100, 600, 400))
    assert "jar_not_sharp" in ap.qa_jar(img, (100, 100, 300, 400))


@pytest.mark.parametrize("w,h", [(1080, 1350), (1080, 1920), (1080, 1080)])
def test_cutout_jar_fills_card_and_label_sharp(w, h, tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    seen = []
    orig = ap._save
    monkeypatch.setattr(ap, "_save", lambda img, jar, label, src=None, **k: (seen.append((img.size, jar)), orig(img, jar, label, src, **k))[1])
    for it in ap.items("ig_post", None, ("cutout",)):
        assert ap.render_studio_card(it, w, h, "Headline", "Sub", it["file"].replace("/", "_"))
    for (W, H), jar in seen:
        frac_h, frac_w = (jar[3] - jar[1]) / H, (jar[2] - jar[0]) / W
        assert 0.60 <= frac_h <= 0.72 or frac_w >= 0.79, (frac_h, frac_w)
        assert abs((jar[0] + jar[2]) / 2 - W / 2) < 3


def test_label_sharpness_qa_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    monkeypatch.setattr(ap, "MIN_LABEL_SHARPNESS_RATIO", 99.0)
    it = ap.items("ig_post", "bold", ("cutout",))[0]
    assert ap.render_studio_card(it, 1080, 1350, "H", "S", "x") is None


def test_subline_never_repeats_shop_cta():
    assert "p3online" not in ap._strip_shop("Bold • 100% coffee • Shop p3online.in")
    assert ap.SKU_COPY["ultra_blend"][1].startswith("70% coffee")
    for head, sub in ap.SKU_COPY.values():
        assert "no chicory" not in (head + sub).lower() and "zero chicory" not in (head + sub).lower()


@pytest.mark.parametrize("text", [
    "Bold is 100% Robusta.", "Bold: strong Robusta instant coffee", "Try Bold, our Arabica jar",
    "Bold • 100% Robusta • lead-free glass jar",
])
def test_claim_checker_fails_bold_bean_variety(text):
    from content_generator.core.product_truth import product_truth_findings
    assert any("Bold is pure coffee" in f["reason"] for f in product_truth_findings(text)), text


@pytest.mark.parametrize("text", [
    "Bold is pure coffee, in a lead-free glass jar.", "Purista is pure Robusta. Bold is pure coffee.",
])
def test_claim_checker_allows_bold_100_coffee(text):
    from content_generator.core.product_truth import product_truth_findings
    assert not any("Bold is pure coffee" in f["reason"] for f in product_truth_findings(text))


def test_no_bold_bean_variety_anywhere_in_copy_sources():
    import glob, re
    from content_generator.core.product_truth import product_truth_findings
    assert "robusta" not in (ap.SKU_COPY["bold"][0] + ap.SKU_COPY["bold"][1]).lower()
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS
    b = SHOPIFY_PRODUCTS["bold"]
    assert not re.search(r"(?i)robusta|arabica", b["title"] + b["short_name"] + b["flavor_profile"])
    bad = []
    for f in glob.glob("content_generator/**/*.py", recursive=True) + glob.glob("config/**/*.py", recursive=True):
        for line in open(f, encoding="utf-8"):
            if "never name a bean variety" in line or "never call Bold" in line or "re.compile" in line:
                continue
            for sent in re.split(r"(?<=[.!?])\s+|\\n", line):
                if re.search(r"\bBold\b", sent) and re.search(r"(?i)\b(robusta|arabica)\b", sent):
                    if product_truth_findings(sent):
                        bad.append((f, sent.strip()[:120]))
    assert not bad, bad


def test_cleaner_keeps_bullet_separators():
    from content_generator.creative.real_jar_composer import _sanitize_text
    assert _sanitize_text("Bold • pure coffee • lead-free glass jar") == "Bold • pure coffee • lead-free glass jar"


@pytest.mark.parametrize("text", ["Purica is 100% Arabica.", "100% PURE COFFEE", "Made with 100 percent coffee beans."])
def test_fssai_hundred_percent_hard_fail(text):
    from content_generator.core.product_truth import product_truth_findings
    assert any("FSSAI" in f["reason"] for f in product_truth_findings(text))


def test_no_hundred_percent_in_copy_defaults_and_prompts():
    import glob, re
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS
    for slug, p in SHOPIFY_PRODUCTS.items():
        for k in ("short_name", "bean_type", "flavor_profile", "chicory"):
            assert not re.search(r"\b100\s*%", str(p.get(k, ""))), (slug, k)
    for head, sub in ap.SKU_COPY.values():
        assert "100" not in head + sub
    for f in glob.glob("content_generator/prompts/*.py") + ["content_generator/scheduler/fallback.py",
                                                            "content_generator/creative/approved_photos.py"]:
        assert not re.search(r"\b100\s*%", open(f, encoding="utf-8").read()), f


def test_bold_story_uses_hitens_card_and_posts_use_hires_cutout(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "_OUT_DIR", str(tmp_path))
    from content_generator.creative.jar_provenance import verify_jar_provenance
    st = ap.render("ig_story", 1080, 1920, "x", "y", 0, 0, "bold", "bstory")
    assert verify_jar_provenance(st)["jar_asset_id"].endswith("bold_100g_approved_card_story.png")
    for d in range(4):
        p = ap.render("ig_post", 1080, 1350, "H", "S", d, 0, "bold", f"bpost{d}")
        assert verify_jar_provenance(p)["jar_asset_id"].endswith("bold_100g_cutout_wide_hires.png")
    for f in ("bold/bold_100g_cutout_front.png", "bold/bold_50g_cutout_front.png"):
        assert [i for i in M["items"] if i["file"] == f][0]["blocked"]
    wide = [i for i in M["items"] if i["file"] == "bold/bold_100g_cutout_wide_hires.png"][0]
    assert wide["primary"] and wide["size"] == "100g" and "tone" not in wide


def test_hires_alpha_cutout_has_clean_background():
    from PIL import Image
    a = Image.open("brand_assets/approved_photos/bold/bold_100g_cutout_hires_alpha.png")
    assert a.mode == "RGBA"
    al = a.getchannel("A")
    w, h = a.size
    for p in [(2, 2), (w - 3, 2), (2, h // 2), (w - 3, h // 2)]:
        assert al.getpixel(p) < 10   # background fully transparent, no cream halo
    assert al.getpixel((w // 2, h // 2)) == 255  # label opaque (white text not punched out)
