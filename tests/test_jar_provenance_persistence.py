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
