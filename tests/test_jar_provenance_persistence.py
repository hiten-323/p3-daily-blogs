"""Durable jar provenance must survive process and scheduled-run boundaries."""
import json
from content_generator.creative import jar_provenance


def test_jar_provenance_registry_round_trips_after_memory_reset(tmp_path, monkeypatch):
    out_dir = tmp_path / "creative"
    registry = out_dir / "jar_provenance.json"
    asset_root = tmp_path / "brand_assets"
    jar = asset_root / "approved_real_jar.png"
    image = out_dir / "2026-10-18_instagram_post.png"
    asset_root.mkdir(parents=True)
    jar.write_bytes(b"approved jar fixture")
    out_dir.mkdir(parents=True)
    image.write_bytes(b"rendered image fixture")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(asset_root))

    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(registry))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    entry = jar_provenance.record_jar_provenance(
        str(image), str(jar), "approved_photo"
    )
    assert entry["asset_real_jar_verified"] is True
    assert registry.exists()

    # A new scheduled runner starts with an empty in-memory cache and reloads disk.
    jar_provenance._MEMORY_REGISTRY.clear()
    result = jar_provenance.verify_jar_provenance(str(image))
    assert result["verified"] is True
    assert result["jar_asset_id"] == str(jar)
    assert result["render_source"] == "approved_photo"



def test_provenance_registry_write_is_atomic_on_replace_failure(tmp_path, monkeypatch):
    out_dir = tmp_path / "creative"
    registry = out_dir / "jar_provenance.json"
    out_dir.mkdir(parents=True)
    registry.write_text('{"previous": {"asset_real_jar_verified": true}}', encoding="utf-8")

    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(registry))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {"next": {"asset_real_jar_verified": True}})

    def fail_replace(_src, _dst):
        raise OSError("simulated interrupted registry replace")

    monkeypatch.setattr(jar_provenance.os, "replace", fail_replace)
    jar_provenance._save_registry()

    # The previous complete registry remains intact and no partial file leaks.
    assert json.loads(registry.read_text(encoding="utf-8")) == {
        "previous": {"asset_real_jar_verified": True}
    }
    assert not list(out_dir.glob(".jar_provenance.*.tmp"))



def test_existing_file_outside_brand_assets_cannot_be_registered_as_a_real_jar(tmp_path, monkeypatch):
    out_dir = tmp_path / "creative"
    out_dir.mkdir()
    outside = tmp_path / "generated_fake_jar.png"
    image = out_dir / "2026-10-18_post.png"
    outside.write_bytes(b"not a trusted brand asset")
    image.write_bytes(b"rendered image")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(out_dir / "jar_provenance.json"))
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(tmp_path / "brand_assets"))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    entry = jar_provenance.record_jar_provenance(str(image), str(outside), "approved_photo")
    assert entry["asset_real_jar_verified"] is False
    assert jar_provenance.verify_jar_provenance(str(image))["verified"] is False


def test_provenance_does_not_collide_for_same_filename_in_different_directories(tmp_path, monkeypatch):
    asset_root = tmp_path / "brand_assets"
    asset_root.mkdir()
    jar = asset_root / "authentic_jar.png"
    jar.write_bytes(b"trusted jar fixture")

    out_dir = tmp_path / "creative"
    out_dir.mkdir()
    registry = out_dir / "jar_provenance.json"

    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    img_a = dir_a / "product.png"
    img_b = dir_b / "product.png"
    img_a.write_bytes(b"content A")
    img_b.write_bytes(b"content B")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(registry))
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(asset_root))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    # Register only img_a as verified
    entry_a = jar_provenance.record_jar_provenance(str(img_a), str(jar), "approved_photo")
    assert entry_a["asset_real_jar_verified"] is True

    # img_a must verify; img_b must fail closed despite identical basename
    res_a = jar_provenance.verify_jar_provenance(str(img_a))
    res_b = jar_provenance.verify_jar_provenance(str(img_b))
    assert res_a["verified"] is True
    assert res_b["verified"] is False
    assert res_b["reason"] in ("unregistered_image", "image_path_mismatch")

    # Roundtrip test across process reload
    jar_provenance._MEMORY_REGISTRY.clear()
    assert jar_provenance.verify_jar_provenance(str(img_a))["verified"] is True
    assert jar_provenance.verify_jar_provenance(str(img_b))["verified"] is False


def test_provenance_rejects_tampered_image_content(tmp_path, monkeypatch):
    asset_root = tmp_path / "brand_assets"
    asset_root.mkdir()
    jar = asset_root / "real_jar.png"
    jar.write_bytes(b"authentic jar content")

    out_dir = tmp_path / "creative"
    out_dir.mkdir()
    image = out_dir / "genuine_image.png"
    image.write_bytes(b"initial authentic render")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(out_dir / "jar_provenance.json"))
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(asset_root))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    entry = jar_provenance.record_jar_provenance(str(image), str(jar), "approved_photo")
    assert entry["asset_real_jar_verified"] is True
    assert jar_provenance.verify_jar_provenance(str(image))["verified"] is True

    # Tamper with the image file content on disk at the same registered path
    image.write_bytes(b"tampered fake render content")
    result = jar_provenance.verify_jar_provenance(str(image))
    assert result["verified"] is False
    assert result["reason"] == "image_content_tampered"


def test_provenance_rejects_modified_source_jar_content(tmp_path, monkeypatch):
    asset_root = tmp_path / "brand_assets"
    asset_root.mkdir()
    jar = asset_root / "real_jar.png"
    jar.write_bytes(b"authentic jar content")

    out_dir = tmp_path / "creative"
    out_dir.mkdir()
    image = out_dir / "rendered_image.png"
    image.write_bytes(b"authentic render")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(out_dir / "jar_provenance.json"))
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(asset_root))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    entry = jar_provenance.record_jar_provenance(str(image), str(jar), "approved_photo")
    assert entry["asset_real_jar_verified"] is True
    assert jar_provenance.verify_jar_provenance(str(image))["verified"] is True

    # Modify the source jar asset on disk
    jar.write_bytes(b"swapped corrupted jar bytes")
    result = jar_provenance.verify_jar_provenance(str(image))
    assert result["verified"] is False
    assert result["reason"] == "source_jar_content_tampered"


def test_provenance_record_fails_closed_on_persistence_failure(tmp_path, monkeypatch):
    asset_root = tmp_path / "brand_assets"
    asset_root.mkdir()
    jar = asset_root / "real_jar.png"
    jar.write_bytes(b"authentic jar content")

    out_dir = tmp_path / "creative"
    out_dir.mkdir()
    image = out_dir / "rendered_image.png"
    image.write_bytes(b"authentic render")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(jar_provenance, "_OUT_DIR", str(out_dir))
    monkeypatch.setattr(jar_provenance, "_PROVENANCE_FILE", str(out_dir / "jar_provenance.json"))
    monkeypatch.setattr(jar_provenance, "_TRUSTED_JAR_ASSET_ROOT", str(asset_root))
    monkeypatch.setattr(jar_provenance, "_MEMORY_REGISTRY", {})

    def fail_save():
        return False

    monkeypatch.setattr(jar_provenance, "_save_registry", fail_save)

    entry = jar_provenance.record_jar_provenance(str(image), str(jar), "approved_photo")
    assert entry["asset_real_jar_verified"] is False
    assert entry["reason"] == "persistence_failed"

    # Memory registry and subsequent verification must not report verified
    assert jar_provenance.verify_jar_provenance(str(image))["verified"] is False


