from pathlib import Path
import shutil

import numpy as np
import pytest
import tifffile

import probraw.profile.export as export_module
from probraw.core.models import Recipe
from probraw.core.external import external_tool_path
from probraw.core.utils import read_image
from probraw.profile.export import (
    _argyll_reference_profile,
    _resolve_batch_workers,
    _versioned_batch_paths,
    batch_develop,
    color_management_mode,
    write_profiled_tiff,
)
from probraw.profile.generic import ensure_generic_output_profile
from probraw.provenance.c2pa import C2PASignConfig
from probraw.provenance.probraw_proof import ProbRawProofConfig, generate_ed25519_identity, verify_probraw_proof
from probraw.sidecar import load_raw_sidecar


class FakeC2PAClient:
    def sign_file(
        self,
        source_path: Path,
        dest_path: Path,
        manifest: dict,
        *,
        cert_path: Path,
        key_path: Path,
        alg: str,
        timestamp_url: str | None = None,
        source_ingredient_path: Path | None = None,
    ) -> dict:
        dest_path.write_bytes(source_path.read_bytes() + b"\nFAKE-C2PA")
        return {
            "active_manifest": "probraw:test",
            "manifests": {"probraw:test": manifest},
            "validation_status": [],
        }

    def read_manifest_store(self, asset_path: Path) -> dict:
        return {"validation_status": []}


def _fake_c2pa_config(tmp_path: Path) -> C2PASignConfig:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_bytes(b"cert")
    key.write_bytes(b"key")
    return C2PASignConfig(cert_path=cert, key_path=key, client=FakeC2PAClient())


def _proof_config(tmp_path: Path) -> ProbRawProofConfig:
    private_key = tmp_path / "proof-private.pem"
    public_key = tmp_path / "proof-public.pem"
    generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    return ProbRawProofConfig(
        private_key_path=private_key,
        public_key_path=public_key,
        signer_name="Unit Test",
    )


def _fake_standard_profiles(tmp_path: Path, monkeypatch) -> Path:
    profile_dir = tmp_path / "standard-profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "sRGB.icm").write_bytes(b"s" * 256)
    (profile_dir / "AdobeRGB1998.icc").write_bytes(b"a" * 256)
    (profile_dir / "ProPhoto.icm").write_bytes(b"p" * 256)
    monkeypatch.setenv("PROBRAW_STANDARD_ICC_DIR", str(profile_dir))
    return profile_dir


def test_color_management_mode_assigns_camera_profile_by_default():
    recipe = Recipe(output_space="scene_linear_camera_rgb", output_linear=True)
    assert color_management_mode(recipe) == "camera_rgb_with_input_icc"


def test_color_management_mode_requires_non_linear_srgb_output():
    recipe = Recipe(output_space="srgb", output_linear=True)
    with pytest.raises(RuntimeError, match="output_space=srgb requiere output_linear=false"):
        color_management_mode(recipe)


def test_color_management_mode_accepts_generic_output_spaces():
    assert color_management_mode(Recipe(output_space="adobe_rgb", output_linear=False)) == "converted_adobe_rgb"
    assert color_management_mode(Recipe(output_space="prophoto_rgb", output_linear=False)) == "converted_prophoto_rgb"


def test_export_has_no_8bit_lcms_tiff16_conversion_path():
    assert not hasattr(export_module, "_write_converted_output_tiff_with_lcms8")


def test_write_profiled_tiff_embeds_standard_output_profile_without_chart(tmp_path: Path, monkeypatch):
    _fake_standard_profiles(tmp_path, monkeypatch)
    out = tmp_path / "manual_prophoto.tiff"
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="prophoto_rgb", output_linear=False, tone_curve="gamma:1.8"),
        profile_path=None,
        generic_profile_dir=tmp_path / "profiles",
    )

    assert mode == "standard_prophoto_rgb_output_icc"
    assert ensure_generic_output_profile("prophoto_rgb", directory=tmp_path / "profiles").exists()
    with tifffile.TiffFile(out) as tif:
        tags = tif.pages[0].tags
        assert 34675 in tags
        assert len(bytes(tags[34675].value)) > 128


def test_write_profiled_tiff_applies_zip_compression(tmp_path: Path):
    out = tmp_path / "camera_rgb.tiff"
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"p" * 256)
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="scene_linear_camera_rgb", output_linear=True),
        profile_path=profile,
        tiff_compression="zip",
    )

    assert mode == "camera_rgb_with_input_icc"
    with tifffile.TiffFile(out) as tif:
        assert tif.pages[0].compression.name == "ADOBE_DEFLATE"
        assert 34675 in tif.pages[0].tags


def test_batch_develop_without_chart_uses_standard_output_profile(tmp_path: Path, monkeypatch):
    _fake_standard_profiles(tmp_path, monkeypatch)
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="prophoto_rgb", output_linear=False, tone_curve="gamma:1.8"),
        profile_path=None,
        out_dir=out_dir,
        proof_config=_proof_config(tmp_path),
    )

    entry = manifest.entries[0]
    assert manifest.profile_path == ""
    assert manifest.color_management_mode == "standard_prophoto_rgb_output_icc"
    assert entry.color_management_mode == "standard_prophoto_rgb_output_icc"
    assert Path(entry.profile_path).name == "ProPhoto.icm"
    assert Path(entry.profile_path).parent == out_dir / "_profiles"
    assert (out_dir / "capture_01.tiff").exists()


def test_write_profiled_tiff_assigns_input_profile_without_conversion(tmp_path: Path):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    out = tmp_path / "camera_rgb.tiff"
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
    )

    assert mode == "camera_rgb_with_input_icc"
    with tifffile.TiffFile(out) as tif:
        tags = tif.pages[0].tags
        assert 34675 in tags
        assert bytes(tags[34675].value) == b"camera-profile-placeholder"


def test_write_profiled_tiff_rejects_camera_rgb_without_input_profile(tmp_path: Path):
    out = tmp_path / "camera_rgb_no_profile.tiff"
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)

    with pytest.raises(RuntimeError, match="perfil ICC de entrada activo"):
        write_profiled_tiff(
            out,
            image,
            recipe=Recipe(output_space="scene_linear_camera_rgb", output_linear=True),
            profile_path=None,
        )

    assert not out.exists()


def test_batch_develop_keeps_linear_audit_separate_from_final_outputs(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    assert (out_dir / "capture_01.tiff").exists()
    assert (out_dir / "capture_01.tiff.probraw.proof.json").exists()
    assert not (out_dir / "capture_01.linear.tiff").exists()
    assert (out_dir / "_linear_audit" / "capture_01.scene_linear.tiff").exists()
    assert manifest.entries[0].linear_audit_tiff == str(out_dir / "_linear_audit" / "capture_01.scene_linear.tiff")


def test_batch_develop_versions_existing_final_and_audit_outputs(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    audit_dir = out_dir / "_linear_audit"
    raws.mkdir()
    out_dir.mkdir()
    audit_dir.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)

    previous_final = out_dir / "capture_01.tiff"
    previous_audit = audit_dir / "capture_01.scene_linear.tiff"
    previous_final.write_bytes(b"previous-final")
    previous_audit.write_bytes(b"previous-audit")

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    entry = manifest.entries[0]
    assert previous_final.read_bytes() == b"previous-final"
    assert previous_audit.read_bytes() == b"previous-audit"
    assert entry.output_tiff == str(out_dir / "capture_01_v002.tiff")
    assert entry.linear_audit_tiff == str(audit_dir / "capture_01_v002.scene_linear.tiff")
    assert Path(entry.output_tiff).exists()
    assert Path(entry.linear_audit_tiff or "").exists()


def test_versioned_batch_paths_avoids_reserved_collisions(tmp_path: Path):
    out_dir = tmp_path / "out"
    audit_dir = out_dir / "_linear_audit"
    out_dir.mkdir()
    audit_dir.mkdir()
    reserved_outputs: set[str] = set()
    reserved_audits: set[str] = set()

    first_final, first_audit = _versioned_batch_paths(
        out_dir,
        audit_dir,
        "capture_01",
        reserved_outputs=reserved_outputs,
        reserved_audits=reserved_audits,
    )
    second_final, second_audit = _versioned_batch_paths(
        out_dir,
        audit_dir,
        "capture_01",
        reserved_outputs=reserved_outputs,
        reserved_audits=reserved_audits,
    )

    assert first_final == out_dir / "capture_01.tiff"
    assert first_audit == audit_dir / "capture_01.scene_linear.tiff"
    assert second_final == out_dir / "capture_01_v002.tiff"
    assert second_audit == audit_dir / "capture_01_v002.scene_linear.tiff"


def test_resolve_batch_workers_respects_env_override(monkeypatch):
    monkeypatch.setenv("PROBRAW_BATCH_WORKERS", "4")

    assert _resolve_batch_workers(1) == 1
    assert _resolve_batch_workers(3) == 3


def test_resolve_batch_workers_accepts_explicit_override(monkeypatch):
    monkeypatch.setenv("PROBRAW_BATCH_WORKERS", "8")

    assert _resolve_batch_workers(5, workers=1) == 1
    assert _resolve_batch_workers(5, workers=3) == 3
    assert _resolve_batch_workers(2, workers=9) == 2


def test_resolve_batch_workers_accepts_auto_keywords(monkeypatch):
    monkeypatch.setattr(export_module, "_available_cpu_count", lambda: 8)
    monkeypatch.setattr(export_module, "_available_physical_memory_bytes", lambda: 32 * 1024 * 1024 * 1024)
    monkeypatch.setenv("PROBRAW_BATCH_WORKERS", "auto")
    assert _resolve_batch_workers(2) == 2
    monkeypatch.setenv("PROBRAW_BATCH_WORKERS", "max")
    assert _resolve_batch_workers(2) == 2
    monkeypatch.setenv("PROBRAW_BATCH_WORKERS", "all")
    assert _resolve_batch_workers(2) == 2


def test_resolve_batch_workers_auto_limits_by_memory(monkeypatch):
    monkeypatch.delenv("PROBRAW_BATCH_WORKERS", raising=False)
    monkeypatch.delenv("PROBRAW_BATCH_MEMORY_RESERVE_MB", raising=False)
    monkeypatch.delenv("PROBRAW_BATCH_WORKER_RAM_MB", raising=False)
    monkeypatch.setattr(export_module, "_available_cpu_count", lambda: 16)
    monkeypatch.setattr(export_module, "_available_physical_memory_bytes", lambda: 3 * 1024 * 1024 * 1024)

    # Defaults reserve 1 GiB and estimate ~2.8 GiB per worker.
    assert _resolve_batch_workers(8) == 1


def test_resolve_batch_workers_auto_honours_memory_env_tuning(monkeypatch):
    monkeypatch.delenv("PROBRAW_BATCH_WORKERS", raising=False)
    monkeypatch.setenv("PROBRAW_BATCH_MEMORY_RESERVE_MB", "512")
    monkeypatch.setenv("PROBRAW_BATCH_WORKER_RAM_MB", "512")
    monkeypatch.setattr(export_module, "_available_cpu_count", lambda: 12)
    monkeypatch.setattr(export_module, "_available_physical_memory_bytes", lambda: 3 * 1024 * 1024 * 1024)

    # 3 GiB available - 512 MiB reserve = 2.5 GiB budget => 5 workers @ 512 MiB.
    assert _resolve_batch_workers(12) == 5


def test_resolve_batch_workers_auto_uses_capture_size_estimate(tmp_path: Path, monkeypatch):
    small = tmp_path / "small.nef"
    small.write_bytes(b"0" * (8 * 1024 * 1024))
    monkeypatch.delenv("PROBRAW_BATCH_WORKERS", raising=False)
    monkeypatch.delenv("PROBRAW_BATCH_WORKER_RAM_MB", raising=False)
    monkeypatch.setattr(export_module, "_available_cpu_count", lambda: 8)
    monkeypatch.setattr(export_module, "_available_physical_memory_bytes", lambda: 8 * 1024 * 1024 * 1024)

    workers = _resolve_batch_workers(
        8,
        files=[small],
        recipe=Recipe(demosaic_algorithm="linear"),
    )

    assert workers > 1


def test_estimated_worker_ram_keeps_raw_floor_for_compressed_inputs(tmp_path: Path, monkeypatch):
    small_raw = tmp_path / "compressed.nef"
    small_raw.write_bytes(b"0" * (4 * 1024 * 1024))
    monkeypatch.delenv("PROBRAW_BATCH_WORKER_RAM_MB", raising=False)

    assert export_module._estimated_worker_ram_mb(
        files=[small_raw],
        recipe=Recipe(demosaic_algorithm="linear"),
    ) >= 1800


def test_batch_develop_writes_true_linear_audit_before_output_adjustments(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")

    image = np.zeros((6, 8, 3), dtype=np.uint16)
    image[..., 0] = 7000
    image[..., 1] = 14000
    image[..., 2] = 21000
    source = raws / "capture_01.tiff"
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        output_space="camera_rgb",
        output_linear=False,
        exposure_compensation=1.0,
        tone_curve="srgb",
    )
    manifest = batch_develop(
        raws_dir=raws,
        recipe=recipe,
        profile_path=profile,
        out_dir=out_dir,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    source_linear = read_image(source)
    audit_linear = read_image(Path(manifest.entries[0].linear_audit_tiff or ""))
    rendered = read_image(out_dir / "capture_01.tiff")

    assert np.allclose(audit_linear, source_linear, atol=1 / 65535)
    assert not np.allclose(rendered, audit_linear, atol=1e-3)


def test_batch_develop_keeps_scene_linear_audit_for_standard_raw_output(tmp_path: Path, monkeypatch):
    _fake_standard_profiles(tmp_path, monkeypatch)
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    raw = raws / "capture_01.nef"
    raw.write_bytes(b"fake raw bytes")
    calls: list[str] = []

    def fake_develop_scene_linear_array(_path, _recipe, cache_dir=None):
        calls.append("scene")
        return np.full((4, 5, 3), 0.2, dtype=np.float32)

    def fake_develop_standard_linear_array(_path, _recipe, cache_dir=None):
        calls.append("standard")
        return np.full((4, 5, 3), 0.8, dtype=np.float32)

    monkeypatch.setattr(export_module, "develop_scene_linear_array", fake_develop_scene_linear_array)
    monkeypatch.setattr(export_module, "develop_standard_linear_array", fake_develop_standard_linear_array)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="srgb", output_linear=False, tone_curve="linear"),
        profile_path=None,
        out_dir=out_dir,
        proof_config=_proof_config(tmp_path),
    )

    assert calls == ["scene", "standard"]
    assert np.allclose(read_image(Path(manifest.entries[0].linear_audit_tiff or "")), 0.2, atol=1 / 65535)
    assert np.allclose(read_image(out_dir / "capture_01.tiff"), 0.8, atol=1 / 65535)
    sidecar = load_raw_sidecar(raw)
    assert sidecar["raw_processing"]["output_color_space"] == "srgb"
    assert sidecar["raw_processing"]["postprocess_kwargs"]


def test_batch_develop_can_sign_with_probraw_proof_without_c2pa(tmp_path: Path):
    raws = tmp_path / "inputs"
    out_dir = tmp_path / "out"
    raws.mkdir()
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"camera-profile-placeholder")
    image = np.full((6, 8, 3), 0.25, dtype=np.float32)
    tifffile.imwrite(str(raws / "capture_01.tiff"), (image * 65535).astype(np.uint16), photometric="rgb", metadata=None)
    proof_config = _proof_config(tmp_path)

    manifest = batch_develop(
        raws_dir=raws,
        recipe=Recipe(output_space="camera_rgb", output_linear=True),
        profile_path=profile,
        out_dir=out_dir,
        proof_config=proof_config,
    )

    entry = manifest.entries[0]
    proof_path = Path(entry.proof_path or "")
    assert proof_path.exists()
    assert entry.c2pa_embedded is False
    verified = verify_probraw_proof(
        proof_path,
        output_tiff=Path(entry.output_tiff),
        source_raw=Path(entry.source_raw),
        public_key_path=proof_config.public_key_path,
    )
    assert verified["status"] == "ok"


@pytest.mark.skipif(external_tool_path("cctiff") is None, reason="requiere cctiff/ArgyllCMS")
def test_write_profiled_tiff_converts_to_srgb_with_cmm(tmp_path: Path):
    profile = tmp_path / "source_srgb.icc"
    shutil.copy2(_argyll_reference_profile("sRGB.icm"), profile)
    out = tmp_path / "converted_srgb.tiff"
    image = np.zeros((10, 12, 3), dtype=np.float32)
    image[..., 0] = 0.2
    image[..., 1] = 0.3
    image[..., 2] = 0.4

    mode = write_profiled_tiff(
        out,
        image,
        recipe=Recipe(output_space="srgb", output_linear=False),
        profile_path=profile,
    )

    assert mode == "converted_srgb"
    arr = tifffile.imread(out)
    assert arr.dtype == np.uint16
    assert arr.shape == image.shape
    with tifffile.TiffFile(out) as tif:
        assert 34675 in tif.pages[0].tags


def test_argyll_reference_profile_searches_debian_share_path(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "usr" / "bin"
    ref_dir = tmp_path / "usr" / "share" / "color" / "argyll" / "ref"
    bin_dir.mkdir(parents=True)
    ref_dir.mkdir(parents=True)
    tool = bin_dir / "cctiff"
    profile = ref_dir / "sRGB.icm"
    tool.write_text("", encoding="utf-8")
    profile.write_bytes(b"profile")

    import probraw.profile.export as export_module

    monkeypatch.setattr(export_module, "external_tool_path", lambda command: str(tool) if command == "cctiff" else None)

    assert export_module._argyll_reference_profile("sRGB.icm") == profile


def test_argyll_reference_profile_searches_argyllcms_share_path(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "usr" / "bin"
    ref_dir = tmp_path / "usr" / "share" / "argyllcms" / "ref"
    bin_dir.mkdir(parents=True)
    ref_dir.mkdir(parents=True)
    tool = bin_dir / "colprof"
    profile = ref_dir / "ProPhoto.icm"
    tool.write_text("", encoding="utf-8")
    profile.write_bytes(b"profile")

    import probraw.profile.export as export_module

    monkeypatch.setattr(export_module, "external_tool_path", lambda command: str(tool) if command == "colprof" else None)

    assert export_module._argyll_reference_profile("ProPhoto.icm") == profile
