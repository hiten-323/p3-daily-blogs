"""Durable jar provenance must survive process and scheduled-run boundaries."""
from content_generator.creative import jar_provenance


def test_jar_provenance_registry_round_trips_after_memory_reset(tmp_path, monkeypatch):
    out_dir = tmp_path / "creative"
    registry = out_dir / "jar_provenance.json"
    jar = tmp_path / "approved_real_jar.png"
    image = out_dir / "2026-10-18_instagram_post.png"
    jar.write_bytes(b"approved jar fixture")
    out_dir.mkdir(parents=True)
    image.write_bytes(b"rendered image fixture")

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
