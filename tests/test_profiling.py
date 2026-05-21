from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from probraw.core.models import PatchSample, Recipe, SampleSet, write_json
from probraw.profile.builder import build_profile, validate_profile, write_samples_cgats
from probraw.profile.gamut import (
    _lab_inside_standard_rgb,
    _standard_rgb_to_lab,
    build_gamut_diagnostics,
    build_gamut_pair_diagnostics,
    evaluate_lab_gamut_membership,
    rgb_surface_samples,
)
import probraw.profile.builder as profiling


def test_build_profile_generates_icc_and_sidecar(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        icc_bytes = profiling.build_matrix_shaper_icc(
            description=description,
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
        out_icc.write_bytes(icc_bytes)

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", lambda _profile, _rgb: np.asarray([s.reference_lab for s in samples], dtype=np.float64))

    samples = []
    for i in range(1, 25):
        samples.append(
            PatchSample(
                patch_id=f"P{i:02d}",
                measured_rgb=[0.1 + i * 0.01, 0.2 + i * 0.005, 0.3 + i * 0.004],
                reference_rgb=None,
                reference_lab=[30 + i, -5 + i * 0.1, -10 + i * 0.1],
                excluded_pixel_ratio=0.1,
                saturated_pixel_ratio=0.0,
            )
        )

    sample_set = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="2005",
        illuminant="D50",
        strategy="trimmed_mean",
        samples=samples,
        missing_reference_patches=[],
    )

    out_icc = tmp_path / "camera.icc"
    result = build_profile(sample_set, Recipe(), out_icc, camera_model="Cam", lens_model="Lens")

    assert out_icc.exists()
    assert out_icc.stat().st_size > 256
    assert Path(result.output_profile_json).exists()
    assert result.metadata["profile_engine_used"] == "argyll"
    assert result.patch_errors[0].reference_lab == samples[0].reference_lab
    assert result.patch_errors[0].profile_lab == samples[0].reference_lab


def test_standard_gamut_diagnostics_include_expected_rgb_spaces():
    payload = build_gamut_diagnostics(generated_profile=None, monitor_profile=None, grid_size=7)

    assert [series["label"] for series in payload["series"]] == [
        "sRGB",
        "Adobe RGB (1998)",
        "ProPhoto RGB",
    ]
    assert payload["series"][0]["points_lab"].shape == (218, 3)
    assert len(payload["series"][0]["quads"]) == 216
    assert payload["series"][0]["health"]["status"] == "ok"


def test_pair_gamut_diagnostics_compare_only_two_profiles():
    payload = build_gamut_pair_diagnostics(
        profile_a={"kind": "standard", "key": "adobe_rgb"},
        profile_b={"kind": "standard", "key": "srgb"},
        grid_size=7,
    )

    assert [series["label"] for series in payload["series"]] == ["Adobe RGB (1998)", "sRGB"]
    assert [series["role"] for series in payload["series"]] == ["wire", "solid"]
    assert payload["comparisons"][0]["source"] == "Adobe RGB (1998)"
    assert payload["comparisons"][0]["target"] == "sRGB"


def test_pair_gamut_diagnostics_marks_out_of_gamut_source_samples():
    payload = build_gamut_pair_diagnostics(
        profile_a={"kind": "standard", "key": "adobe_rgb"},
        profile_b={"kind": "standard", "key": "srgb"},
        grid_size=7,
    )

    adobe = payload["series"][0]

    assert adobe["out_of_gamut_samples"] > 0
    assert adobe["out_of_gamut_lab"].shape[1] == 3
    assert adobe["out_of_gamut_rgb"].shape == adobe["out_of_gamut_lab"].shape
    assert adobe["out_of_gamut_target"] == "sRGB"


def test_standard_gamut_membership_recognizes_own_surface_samples():
    rgb = rgb_surface_samples(5)
    lab = _standard_rgb_to_lab(rgb, "srgb")

    inside = _lab_inside_standard_rgb(lab, "srgb")

    assert inside.all()


def test_lab_gamut_membership_reports_common_profile_intersection():
    lab = _standard_rgb_to_lab(np.asarray([[0.0, 1.0, 0.0]], dtype=np.float64), "adobe_rgb")

    membership = evaluate_lab_gamut_membership(
        lab,
        profile_a={"kind": "standard", "key": "adobe_rgb"},
        profile_b={"kind": "standard", "key": "srgb"},
        grid_size=7,
    )

    assert membership["inside_a"].tolist() == [True]
    assert membership["inside_b"].tolist() == [False]
    assert membership["inside_common"].tolist() == [False]
    assert membership["label_a"] == "Adobe RGB (1998)"
    assert membership["label_b"] == "sRGB"


def test_argyll_builder_accepts_icm_output(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(profiling, "external_tool_path", lambda name: "colprof" if name == "colprof" else None)

    def fake_run(args, cwd, stdout, stderr, text):
        Path(cwd, "camera_profile.icm").write_bytes(b"icm-profile")
        return SimpleNamespace(returncode=0, stdout="Profile done")

    monkeypatch.setattr(profiling, "run_external", fake_run)

    out_icc = tmp_path / "camera.icc"
    profiling._build_profile_with_argyll(
        out_icc=out_icc,
        measured_rgb=np.asarray([[0.1, 0.2, 0.3]], dtype=np.float64),
        reference_lab=np.asarray([[50.0, 0.0, 0.0]], dtype=np.float64),
        patch_ids=["P01"],
        description="unit",
        extra_args=["-qm", "-as"],
    )

    assert out_icc.read_bytes() == b"icm-profile"


def test_argyll_builder_colprof_cache_reuses_previous_profile(tmp_path: Path, monkeypatch):
    colprof_path = tmp_path / "colprof.exe"
    colprof_path.write_bytes(b"fake-colprof")
    monkeypatch.setattr(profiling, "external_tool_path", lambda name: str(colprof_path) if name == "colprof" else None)
    monkeypatch.setenv("PROBRAW_ARGYLL_CACHE_DIR", str(tmp_path / "argyll-cache"))
    monkeypatch.setenv("PROBRAW_ARGYLL_COLPROF_CACHE", "1")

    calls: list[list[str]] = []

    def fake_run(args, cwd, stdout, stderr, text):
        calls.append([str(part) for part in args])
        Path(cwd, "camera_profile.icc").write_bytes(b"cached-profile" * 16)
        return SimpleNamespace(returncode=0, stdout="Profile done")

    monkeypatch.setattr(profiling, "run_external", fake_run)

    kwargs = dict(
        measured_rgb=np.asarray([[0.1, 0.2, 0.3]], dtype=np.float64),
        reference_lab=np.asarray([[50.0, 0.0, 0.0]], dtype=np.float64),
        patch_ids=["P01"],
        description="unit",
        extra_args=["-qm", "-as"],
    )
    out_first = tmp_path / "first.icc"
    out_second = tmp_path / "second.icc"

    profiling._build_profile_with_argyll(out_icc=out_first, **kwargs)
    profiling._build_profile_with_argyll(out_icc=out_second, **kwargs)

    assert out_first.read_bytes() == b"cached-profile" * 16
    assert out_second.read_bytes() == b"cached-profile" * 16
    assert len(calls) == 1


def test_argyll_builder_colprof_cache_can_be_disabled(tmp_path: Path, monkeypatch):
    colprof_path = tmp_path / "colprof.exe"
    colprof_path.write_bytes(b"fake-colprof")
    monkeypatch.setattr(profiling, "external_tool_path", lambda name: str(colprof_path) if name == "colprof" else None)
    monkeypatch.setenv("PROBRAW_ARGYLL_CACHE_DIR", str(tmp_path / "argyll-cache"))
    monkeypatch.setenv("PROBRAW_ARGYLL_COLPROF_CACHE", "0")

    calls: list[list[str]] = []

    def fake_run(args, cwd, stdout, stderr, text):
        calls.append([str(part) for part in args])
        Path(cwd, "camera_profile.icc").write_bytes(b"no-cache-profile")
        return SimpleNamespace(returncode=0, stdout="Profile done")

    monkeypatch.setattr(profiling, "run_external", fake_run)

    kwargs = dict(
        measured_rgb=np.asarray([[0.1, 0.2, 0.3]], dtype=np.float64),
        reference_lab=np.asarray([[50.0, 0.0, 0.0]], dtype=np.float64),
        patch_ids=["P01"],
        description="unit",
        extra_args=["-qm", "-as"],
    )

    profiling._build_profile_with_argyll(out_icc=tmp_path / "first.icc", **kwargs)
    profiling._build_profile_with_argyll(out_icc=tmp_path / "second.icc", **kwargs)

    assert len(calls) == 2


@pytest.mark.skipif(shutil.which("xicclu") is None, reason="requiere xicclu/ArgyllCMS")
def test_validate_profile_uses_real_icc_not_sidecar_matrix(tmp_path: Path):
    profile = tmp_path / "srgb.icc"
    profile.write_bytes(
        profiling.build_matrix_shaper_icc(
            description="synthetic validation profile",
            matrix_camera_to_xyz=np.eye(3),
            gamma=1.0,
        )
    )
    write_json(
        profile.with_suffix(".profile.json"),
        {
            "matrix_camera_to_xyz": [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
        },
    )

    rgb = [0.25, 0.4, 0.6]
    reference_lab = _lookup_lab_with_xicclu(profile, rgb)
    samples = SampleSet(
        chart_name="synthetic",
        chart_version="1",
        illuminant="D50",
        strategy="direct",
        samples=[
            PatchSample(
                patch_id="P01",
                measured_rgb=rgb,
                reference_rgb=None,
                reference_lab=reference_lab,
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ],
        missing_reference_patches=[],
    )

    result = validate_profile(samples, profile)

    assert result.error_summary.max_delta_e76 < 1e-5
    assert result.error_summary.max_delta_e2000 < 1e-5


def test_validate_profile_requires_real_icc_even_if_sidecar_exists(tmp_path: Path):
    profile = tmp_path / "missing.icc"
    write_json(profile.with_suffix(".profile.json"), {"matrix_camera_to_xyz": np.eye(3).tolist()})
    samples = SampleSet(
        chart_name="synthetic",
        chart_version="1",
        illuminant="D50",
        strategy="direct",
        samples=[
            PatchSample(
                patch_id="P01",
                measured_rgb=[0.2, 0.3, 0.4],
                reference_rgb=None,
                reference_lab=[50.0, 0.0, 0.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ],
        missing_reference_patches=[],
    )

    with pytest.raises(FileNotFoundError, match="No existe perfil ICC"):
        validate_profile(samples, profile)


def test_write_samples_cgats_exports_lab_rgb_ti3(tmp_path: Path):
    samples = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="unit",
        illuminant="D50",
        strategy="trimmed_mean(trim_percent=0.1,reject_saturated=true)",
        samples=[
            PatchSample(
                patch_id="P01",
                measured_rgb=[0.1, 0.2, 0.3],
                reference_rgb=None,
                reference_lab=[50.0, 1.0, -2.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ],
        missing_reference_patches=[],
    )
    out = tmp_path / "samples.ti3"

    write_samples_cgats(samples, out)

    text = out.read_text(encoding="ascii")
    assert text.startswith("CTI3")
    assert 'COLOR_REP "LAB_RGB"' in text
    assert 'CHART_NAME "ColorChecker 24"' in text
    assert "P01 50.000000 1.000000 -2.000000 10.000000 20.000000 30.000000" in text


def _lookup_lab_with_xicclu(profile: Path, rgb: list[float]) -> list[float]:
    proc = subprocess.run(
        ["xicclu", "-v0", "-ff", "-ir", "-pl", str(profile)],
        input=" ".join(str(v) for v in rgb) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return [float(v) for v in proc.stdout.split()[:3]]
