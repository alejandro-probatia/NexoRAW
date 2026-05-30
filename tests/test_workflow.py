from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile

from probraw.chart.detection import detect_chart_from_corners_array
from probraw.chart.sampling import ReferenceCatalog
from probraw.core.models import (
    BatchManifest,
    ChartDetectionResult,
    ErrorSummary,
    PatchDetection,
    PatchError,
    PatchSample,
    Point2,
    ProfileBuildResult,
    Recipe,
    SampleSet,
    ValidationResult,
    read_json,
)
from probraw.core.recipe import load_recipe
from probraw.provenance.c2pa import C2PASignConfig
from probraw.provenance.probraw_proof import ProbRawProofConfig, generate_ed25519_identity
from probraw.workflow import auto_generate_profile_from_charts, auto_profile_batch
import probraw.workflow as workflow
import probraw.profile.builder as profiling


class FakeC2PAClient:
    def sign_file(self, source_path, dest_path, manifest, **_kwargs):
        dest_path.write_bytes(source_path.read_bytes() + b"\nFAKE-C2PA")
        return {"active_manifest": "probraw:test", "manifests": {"probraw:test": manifest}, "validation_status": []}

    def read_manifest_store(self, asset_path):
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
    if not private_key.exists():
        generate_ed25519_identity(private_key_path=private_key, public_key_path=public_key)
    return ProbRawProofConfig(private_key_path=private_key, public_key_path=public_key)


def _write_synthetic_raw(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)
    return path


def _patch_synthetic_raw_developer(monkeypatch) -> None:
    def fake_develop_image_array(path, _recipe, cache_dir=None, **_kwargs):
        arr = np.asarray(tifffile.imread(str(path)))
        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
        else:
            arr = arr.astype(np.float32)
        return np.clip(arr, 0.0, 1.0)

    monkeypatch.setattr(workflow, "develop_image_array", fake_develop_image_array)


def test_auto_profile_batch_end_to_end(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    targets_dir = tmp_path / "targets"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    charts_dir.mkdir()
    targets_dir.mkdir()

    img = _synthetic_colorchecker_image()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", img)
    _write_synthetic_raw(charts_dir / "chart_02.NEF", img)
    tifffile.imwrite(str(targets_dir / "target_01.tiff"), img, photometric="rgb", metadata=None)
    tifffile.imwrite(str(targets_dir / "target_02.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "camera.icc"
    profile_report = tmp_path / "profile_report.json"

    result = auto_profile_batch(
        chart_captures_dir=charts_dir,
        target_captures_dir=targets_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        batch_out_dir=out_dir,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
        qa_mean_delta_e2000_max=999.0,
        qa_max_delta_e2000_max=999.0,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert (out_dir / "batch_manifest.json").exists()
    assert result["chart_captures_used"] >= 1
    assert len(result["batch_manifest"]["entries"]) == 2


def test_collect_chart_samples_minimal_artifacts_omits_images(tmp_path: Path, monkeypatch):
    chart = tmp_path / "chart_01.NEF"
    chart.write_bytes(b"placeholder")
    image = np.full((20, 30, 3), 0.25, dtype=np.float32)

    def fake_develop_image_array(_path, _recipe, cache_dir=None):
        return image

    detection = ChartDetectionResult(
        chart_type="unit",
        confidence_score=1.0,
        valid_patch_ratio=1.0,
        homography=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        chart_polygon=[Point2(0, 0), Point2(29, 0), Point2(29, 19), Point2(0, 19)],
        patches=[
            PatchDetection(
                patch_id="P01",
                polygon=[Point2(2, 2), Point2(10, 2), Point2(10, 10), Point2(2, 10)],
                sample_region=[Point2(2, 2), Point2(10, 2), Point2(10, 10), Point2(2, 10)],
            )
        ],
        warnings=[],
    )

    monkeypatch.setattr(workflow, "develop_image_array", fake_develop_image_array)
    monkeypatch.setattr(workflow, "detect_chart_from_array", lambda *_args, **_kwargs: detection)

    result = workflow._collect_chart_samples(
        chart_files=[chart],
        recipe=Recipe(),
        reference=ReferenceCatalog(
            {
                "chart_name": "unit",
                "chart_version": "1",
                "illuminant": "D50",
                "patches": [{"patch_id": "P01", "reference_lab": [50, 0, 0]}],
            }
        ),
        chart_type="colorchecker24",
        min_confidence=0.35,
        allow_fallback_detection=False,
        chart_dev_dir=tmp_path / "developed",
        detect_dir=tmp_path / "detections",
        sample_dir=tmp_path / "samples",
        overlay_dir=tmp_path / "overlays",
        pass_name="unit",
        workers=1,
        artifacts="minimal",
    )

    assert len(result["accepted_samples"]) == 1
    assert list((tmp_path / "detections").glob("*.json"))
    assert list((tmp_path / "samples").glob("*.json"))
    assert not list((tmp_path / "developed").glob("*.tiff"))
    assert not list((tmp_path / "overlays").glob("*.png"))


def test_collect_chart_samples_rejects_saturated_neutral_patch(tmp_path: Path, monkeypatch):
    chart = tmp_path / "chart_saturated.NEF"
    chart.write_bytes(b"placeholder")
    image = np.ones((20, 30, 3), dtype=np.float32)
    detection = ChartDetectionResult(
        chart_type="unit",
        confidence_score=1.0,
        valid_patch_ratio=1.0,
        homography=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        chart_polygon=[Point2(0, 0), Point2(29, 0), Point2(29, 19), Point2(0, 19)],
        patches=[
            PatchDetection(
                patch_id="P19",
                polygon=[Point2(2, 2), Point2(10, 2), Point2(10, 10), Point2(2, 10)],
                sample_region=[Point2(2, 2), Point2(10, 2), Point2(10, 10), Point2(2, 10)],
            )
        ],
        warnings=[],
    )

    monkeypatch.setattr(workflow, "develop_image_array", lambda *_args, **_kwargs: image)
    monkeypatch.setattr(workflow, "detect_chart_from_array", lambda *_args, **_kwargs: detection)

    result = workflow._collect_chart_samples(
        chart_files=[chart],
        recipe=Recipe(),
        reference=ReferenceCatalog(
            {
                "chart_name": "unit",
                "chart_version": "1",
                "illuminant": "D50",
                "patches": [{"patch_id": "P19", "reference_lab": [96.0, 0, 0]}],
            }
        ),
        chart_type="colorchecker24",
        min_confidence=0.35,
        allow_fallback_detection=False,
        chart_dev_dir=tmp_path / "developed",
        detect_dir=tmp_path / "detections",
        sample_dir=tmp_path / "samples",
        overlay_dir=tmp_path / "overlays",
        pass_name="unit",
        workers=1,
        artifacts="minimal",
    )

    assert result["accepted_samples"] == []
    assert result["skipped"][0]["reason"] == "neutral_patch_saturation"
    assert result["skipped"][0]["patch_id"] == "P19"
    assert result["skipped"][0]["saturated_pixel_ratio"] == pytest.approx(1.0)
    assert Path(result["skipped"][0]["sample_json"]).exists()


def test_collect_chart_samples_reports_blocking_fallback_detection(tmp_path: Path, monkeypatch):
    chart = tmp_path / "chart_fallback.NEF"
    chart.write_bytes(b"placeholder")
    image = np.full((20, 30, 3), 0.25, dtype=np.float32)
    detection = ChartDetectionResult(
        chart_type="unit",
        confidence_score=0.05,
        valid_patch_ratio=0.0,
        homography=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        chart_polygon=[Point2(0, 0), Point2(29, 0), Point2(29, 19), Point2(0, 19)],
        patches=[],
        warnings=["fallback geometrico no fiable"],
        detection_mode="fallback",
    )

    monkeypatch.setattr(workflow, "develop_image_array", lambda *_args, **_kwargs: image)
    monkeypatch.setattr(workflow, "detect_chart_from_array", lambda *_args, **_kwargs: detection)

    result = workflow._collect_chart_samples(
        chart_files=[chart],
        recipe=Recipe(),
        reference=ReferenceCatalog(
            {
                "chart_name": "unit",
                "chart_version": "1",
                "illuminant": "D50",
                "patches": [{"patch_id": "P01", "reference_lab": [50, 0, 0]}],
            }
        ),
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=False,
        chart_dev_dir=tmp_path / "developed",
        detect_dir=tmp_path / "detections",
        sample_dir=tmp_path / "samples",
        overlay_dir=tmp_path / "overlays",
        pass_name="unit",
        workers=1,
        artifacts="minimal",
    )

    assert result["accepted_samples"] == []
    skipped = result["skipped"][0]
    assert skipped["reason"] == "fallback_detection"
    assert skipped["detection_mode"] == "fallback"
    assert skipped["warnings"] == ["fallback geometrico no fiable"]
    assert skipped["confidence"] == pytest.approx(0.05)


def test_auto_generate_profile_error_includes_skipped_capture_details(tmp_path: Path, monkeypatch):
    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work"
    charts_dir.mkdir()
    chart = charts_dir / "chart_01.NEF"
    _write_synthetic_raw(chart, np.zeros((10, 10, 3), dtype=np.uint16))

    def fake_collect_chart_samples(**_kwargs):
        return {
            "accepted_samples": [],
            "detections": {},
            "skipped": [
                {
                    "capture": str(chart),
                    "reason": "fallback_detection",
                    "detection_mode": "fallback",
                    "confidence": 0.05,
                    "warnings": ["fallback geometrico no fiable"],
                }
            ],
        }

    monkeypatch.setattr(workflow, "_collect_chart_samples", fake_collect_chart_samples)

    with pytest.raises(RuntimeError, match="fallback_detection.*confianza=0.050"):
        auto_generate_profile_from_charts(
            chart_captures_dir=charts_dir,
            recipe=Recipe(),
            reference=ReferenceCatalog(
                {
                    "chart_name": "unit",
                    "chart_version": "1",
                    "illuminant": "D50",
                    "patches": [{"patch_id": "P01", "reference_lab": [50, 0, 0]}],
                }
            ),
            profile_out=tmp_path / "profile.icc",
            profile_report_out=tmp_path / "profile_report.json",
            work_dir=work_dir,
        )


def test_split_training_validation_keeps_manual_detection_in_training(tmp_path: Path):
    fallback_capture = tmp_path / "_DSC3632.NEF"
    manual_capture = tmp_path / "_DSC3633.NEF"

    training, validation = workflow._split_training_validation_files(
        [fallback_capture, manual_capture],
        1,
        preferred_training_files=[manual_capture],
    )

    assert training == [manual_capture]
    assert validation == [fallback_capture]


def test_auto_generate_profile_from_charts_only(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_profile"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", img)
    _write_synthetic_raw(charts_dir / "chart_02.NEF", img)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "profile_only.icc"
    profile_report = tmp_path / "profile_only_report.json"
    progress_events: list[dict[str, object]] = []

    result = auto_generate_profile_from_charts(
        chart_captures_dir=charts_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
        qa_mean_delta_e2000_max=999.0,
        qa_max_delta_e2000_max=999.0,
        progress_callback=progress_events.append,
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert result["chart_captures_total"] == 2
    assert result["chart_captures_used"] >= 1
    assert "profile" in result
    assert result["profile_status"]["status"] == "validated"
    assert any(item["id"] == "independent_validation_recommended" for item in result["workflow_recommendations"])
    assert read_json(profile_report)["metadata"]["profile_status"] == "validated"
    assert read_json(profile_report)["metadata"]["workflow_recommendations"] == result["workflow_recommendations"]
    assert progress_events
    assert progress_events[-1]["progress"] == 100
    assert "Muestreando carta" in {event["phase"] for event in progress_events}
    assert "Construyendo ICC" in {event["phase"] for event in progress_events}


def test_auto_generate_profile_from_explicit_chart_files(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_a = tmp_path / "charts_a"
    charts_b = tmp_path / "charts_b"
    work_dir = tmp_path / "work_explicit"
    charts_a.mkdir()
    charts_b.mkdir()

    img = _synthetic_colorchecker_image()
    chart_01 = _write_synthetic_raw(charts_a / "chart_01.NEF", img)
    chart_02 = _write_synthetic_raw(charts_b / "chart_02.NEF", img)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "profile_from_files.icc"
    profile_report = tmp_path / "profile_from_files_report.json"

    result = auto_generate_profile_from_charts(
        chart_captures_dir=tmp_path / "unused_charts_dir",
        chart_capture_files=[chart_02, chart_01],
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
    )

    assert profile_out.exists()
    assert profile_report.exists()
    assert result["chart_captures_total"] == 2
    assert result["chart_captures_used"] >= 1


def test_auto_generate_profile_uses_manual_detection(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_manual"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    chart = _write_synthetic_raw(charts_dir / "chart_manual.NEF", img)
    manual_detection = detect_chart_from_corners_array(
        img.astype(np.float32) / 65535.0,
        corners=[(0.0, 0.0), (720.0, 0.0), (720.0, 480.0), (0.0, 480.0)],
        chart_type="colorchecker24",
    )

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    result = auto_generate_profile_from_charts(
        chart_captures_dir=tmp_path / "unused",
        chart_capture_files=[chart],
        manual_detections={chart: manual_detection},
        recipe=recipe,
        reference=reference,
        profile_out=tmp_path / "manual.icc",
        profile_report_out=tmp_path / "manual_report.json",
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.95,
        allow_fallback_detection=False,
    )

    detection_payload = (work_dir / "detections" / "001_chart_manual.json").read_text(encoding="utf-8")
    assert result["chart_captures_used"] == 1
    assert '"detection_mode": "manual"' in detection_payload


def test_auto_generate_profile_writes_holdout_qa_report(tmp_path: Path, monkeypatch):
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

    def fake_validate_profile(samples, profile_path):
        return ValidationResult(
            profile_path=str(profile_path),
            error_summary=ErrorSummary(
                mean_delta_e76=2.0,
                median_delta_e76=2.0,
                p95_delta_e76=3.0,
                max_delta_e76=4.0,
                mean_delta_e2000=1.5,
                median_delta_e2000=1.4,
                p95_delta_e2000=2.1,
                max_delta_e2000=2.8,
            ),
            patch_errors=[
                PatchError(patch_id="P01", delta_e76=1.1, delta_e2000=0.8),
                PatchError(patch_id="P02", delta_e76=3.5, delta_e2000=2.8),
            ],
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    monkeypatch.setattr(workflow, "validate_profile", fake_validate_profile)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_holdout"
    qa_report = tmp_path / "qa_session_report.json"
    charts_dir.mkdir()

    img = _synthetic_colorchecker_image()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", img)
    _write_synthetic_raw(charts_dir / "chart_02.NEF", img)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    profile_out = tmp_path / "holdout.icc"
    profile_report = tmp_path / "holdout_report.json"
    result = auto_generate_profile_from_charts(
        chart_captures_dir=charts_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report,
        validation_report_out=qa_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
        validation_holdout_count=1,
        qa_mean_delta_e2000_max=999.0,
        qa_max_delta_e2000_max=999.0,
    )

    assert qa_report.exists()
    assert result["training_captures_total"] == 1
    assert result["chart_captures_used"] == 1
    assert result["validation_captures_total"] == 1
    assert result["validation_captures_used"] == 1
    assert result["profile_status"]["status"] == "validated"
    assert result["validation"]["qa_report"]["status"] == "validated"
    assert result["validation"]["qa_report"]["validation_worst_patches"][0]["patch_id"] == "P02"
    assert read_json(profile_report)["metadata"]["profile_status"] == "validated"
    assert read_json(profile_out.with_suffix(".profile.json"))["profile_status"] == "validated"
    qa = result["validation"]["qa_report"]
    check_ids = {check["id"] for check in qa["checks"]}
    assert "training_low_signal" in check_ids
    assert "validation_low_signal" in check_ids
    assert qa["training_capture_quality"]["capture_count"] == 1
    assert qa["training_capture_quality"]["captures"][0]["brightest_neutral_luma"] > 0.0
    assert qa["training_sample_quality"]["median_patch_luma"] > 0.0
    assert (work_dir / "samples_aggregated_validation.json").exists()


def test_qa_report_keeps_missing_validation_non_blocking(tmp_path: Path):
    samples = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="2005",
        illuminant="D50",
        strategy="trimmed_mean",
        samples=[
            PatchSample(
                patch_id="P19",
                measured_rgb=[0.65, 0.65, 0.65],
                reference_rgb=None,
                reference_lab=[96.5, 0.0, 0.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
                sample_center=[10.0, 10.0],
            )
        ],
        missing_reference_patches=[],
    )
    profile_result = ProfileBuildResult(
        output_icc=str(tmp_path / "draft.icc"),
        output_profile_json=str(tmp_path / "draft.profile.json"),
        model="matrix3x3",
        matrix_camera_to_xyz=np.eye(3).tolist(),
        trc_gamma=1.0,
        error_summary=ErrorSummary(
            mean_delta_e76=1.0,
            median_delta_e76=1.0,
            p95_delta_e76=1.0,
            max_delta_e76=1.0,
            mean_delta_e2000=1.0,
            median_delta_e2000=1.0,
            p95_delta_e2000=1.0,
            max_delta_e2000=1.0,
        ),
        patch_errors=[
            PatchError(
                patch_id="P19",
                delta_e76=1.0,
                delta_e2000=1.0,
                reference_lab=[96.5, 0.0, 0.0],
                profile_lab=[96.3, 0.7, -0.6],
            )
        ],
        metadata={},
    )

    qa = workflow._build_session_qa_report(
        training_files=[tmp_path / "training.tiff"],
        validation_files=[tmp_path / "validation.tiff"],
        training_samples=samples,
        validation_samples=None,
        training_capture_samples=[samples],
        validation_capture_samples=[],
        training_profile_result=profile_result,
        validation_result=None,
        validation_skipped=[{"capture": str(tmp_path / "validation.tiff"), "reason": "sin muestras"}],
        qa_mean_delta_e2000_max=5.0,
        qa_max_delta_e2000_max=10.0,
    )

    assert qa["status"] == "not_validated"
    availability = next(check for check in qa["checks"] if check["id"] == "validation_samples_available")
    assert availability["severity"] == "warning"
    assert availability["passed"] is False
    assert qa["training_neutral_axis_error"]["max_ab_residual"] > 0.0


def test_auto_profile_batch_refuses_rejected_session_profile(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        out_icc.write_bytes(
            profiling.build_matrix_shaper_icc(
                description=description,
                matrix_camera_to_xyz=np.eye(3),
                gamma=1.0,
            )
        )

    def fake_validate_profile(samples, profile_path):
        return ValidationResult(
            profile_path=str(profile_path),
            error_summary=ErrorSummary(
                mean_delta_e76=30.0,
                median_delta_e76=30.0,
                p95_delta_e76=30.0,
                max_delta_e76=30.0,
                mean_delta_e2000=25.0,
                median_delta_e2000=25.0,
                p95_delta_e2000=25.0,
                max_delta_e2000=25.0,
            ),
            patch_errors=[PatchError(patch_id="P01", delta_e76=30.0, delta_e2000=25.0)],
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    monkeypatch.setattr(workflow, "validate_profile", fake_validate_profile)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    targets_dir = tmp_path / "targets"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work_rejected"
    charts_dir.mkdir()
    targets_dir.mkdir()

    img = _synthetic_colorchecker_image()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", img)
    _write_synthetic_raw(charts_dir / "chart_02.NEF", img)
    tifffile.imwrite(str(targets_dir / "target_01.tiff"), img, photometric="rgb", metadata=None)

    repo_root = Path(__file__).resolve().parents[1]
    recipe = load_recipe(repo_root / "testdata/recipes/scientific_recipe.yml")
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")

    with pytest.raises(RuntimeError, match="estado rejected"):
        auto_profile_batch(
            chart_captures_dir=charts_dir,
            target_captures_dir=targets_dir,
            recipe=recipe,
            reference=reference,
            profile_out=tmp_path / "rejected.icc",
            profile_report_out=tmp_path / "rejected_report.json",
            batch_out_dir=out_dir,
            work_dir=work_dir,
            chart_type="colorchecker24",
            min_confidence=0.0,
            allow_fallback_detection=True,
            validation_holdout_count=1,
        )

    assert not (out_dir / "batch_manifest.json").exists()


def test_profile_status_resolves_draft_rejected_and_expired():
    generated_at = "2026-04-20T10:00:00+00:00"

    draft = workflow._build_profile_status(
        validation_payload=None,
        qa_report_path=None,
        generated_at=generated_at,
        valid_until=None,
    )
    training_validated = workflow._build_profile_status(
        validation_payload=None,
        qa_report_path=None,
        generated_at=generated_at,
        valid_until=None,
        training_error_summary={"mean_delta_e2000": 1.2, "max_delta_e2000": 3.4},
    )
    rejected = workflow._build_profile_status(
        validation_payload={"qa_report": {"status": "rejected"}},
        qa_report_path="/tmp/qa.json",
        generated_at=generated_at,
        valid_until=None,
    )
    expired = workflow._build_profile_status(
        validation_payload={"qa_report": {"status": "validated"}},
        qa_report_path="/tmp/qa.json",
        generated_at=generated_at,
        valid_until="2026-04-21T10:00:00+00:00",
        now="2026-04-22T10:00:00+00:00",
    )
    bad_training = workflow._build_profile_status(
        validation_payload=None,
        qa_report_path=None,
        generated_at=generated_at,
        valid_until=None,
        training_error_summary={"mean_delta_e2000": 26.8, "max_delta_e2000": 46.9},
    )

    assert draft["status"] == "draft"
    assert training_validated["status"] == "validated"
    assert training_validated["training_status"] == "passed"
    assert rejected["status"] == "rejected"
    assert expired["status"] == "expired"
    assert bad_training["status"] == "rejected"
    assert bad_training["training_status"] == "rejected"


def test_sanitize_recipe_for_profiling_normalizes_non_scientific_fields():
    from probraw.workflow import sanitize_recipe_for_profiling

    recipe = Recipe(
        white_balance_mode="camera_metadata",
        wb_multipliers=[1.1, 1.0, 2.2, 1.0],
        exposure_compensation=1.25,
        tone_curve="srgb",
        output_linear=False,
        output_space="srgb",
        denoise="mild",
        sharpen="medium",
    )

    sanitized, changes = sanitize_recipe_for_profiling(recipe)

    assert sanitized.denoise == "off"
    assert sanitized.sharpen == "off"
    assert sanitized.white_balance_mode == "fixed"
    assert sanitized.wb_multipliers == [1.0, 1.0, 1.0, 1.0]
    assert sanitized.exposure_compensation == 0.0
    assert sanitized.tone_curve == "linear"
    assert sanitized.output_linear is True
    assert sanitized.output_space == "scene_linear_camera_rgb"
    fields_changed = {c["field"] for c in changes}
    assert {
        "denoise",
        "sharpen",
        "white_balance_mode",
        "wb_multipliers",
        "exposure_compensation",
        "tone_curve",
        "output_linear",
        "output_space",
    } <= fields_changed
    # Original recipe must remain untouched (immutable contract).
    assert recipe.denoise == "mild"
    assert recipe.sharpen == "medium"
    assert recipe.exposure_compensation == 1.25


def test_sanitize_recipe_for_profiling_is_noop_for_scientific_recipe():
    from probraw.workflow import sanitize_recipe_for_profiling

    recipe = Recipe()
    sanitized, changes = sanitize_recipe_for_profiling(recipe)

    assert sanitized is recipe
    assert changes == []


def test_auto_generate_profile_persists_profile_and_render_recipes(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        out_icc.write_bytes(
            profiling.build_matrix_shaper_icc(
                description=description,
                matrix_camera_to_xyz=np.eye(3),
                gamma=1.0,
            )
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    work_dir = tmp_path / "work_render_recipe"
    charts_dir.mkdir()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", _synthetic_colorchecker_image())

    repo_root = Path(__file__).resolve().parents[1]
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")
    recipe = Recipe(
        tone_curve="srgb",
        output_linear=False,
        output_space="srgb",
        denoise="mild",
        sharpen="medium",
    )
    profile_report = tmp_path / "render_recipe_report.json"

    result = auto_generate_profile_from_charts(
        chart_captures_dir=charts_dir,
        recipe=recipe,
        reference=reference,
        profile_out=tmp_path / "render_recipe.icc",
        profile_report_out=profile_report,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
    )

    profile_recipe = load_recipe(Path(str(result["profile_recipe_path"])))
    render_recipe = load_recipe(Path(str(result["render_recipe_path"])))
    assert profile_recipe.tone_curve == "linear"
    assert profile_recipe.output_linear is True
    assert profile_recipe.output_space == "scene_linear_camera_rgb"
    assert profile_recipe.denoise == "off"
    assert profile_recipe.sharpen == "off"
    assert render_recipe.tone_curve == "linear"
    assert render_recipe.output_linear is True
    assert render_recipe.output_space == "scene_linear_camera_rgb"
    assert render_recipe.denoise == "mild"
    assert render_recipe.sharpen == "medium"

    report_metadata = read_json(profile_report)["metadata"]
    assert report_metadata["requested_recipe"]["denoise"] == "mild"
    assert report_metadata["profile_recipe"]["denoise"] == "off"
    assert report_metadata["render_recipe"]["denoise"] == "mild"
    development_payload = result["development_profile"]
    assert development_payload["calibrated_recipe"]["denoise"] == "mild"
    assert development_payload["profile_calibrated_recipe"]["denoise"] == "off"
    assert development_payload["render_calibrated_recipe"]["denoise"] == "mild"
    assert {c["field"] for c in report_metadata["recipe_profiling_normalizations"]} >= {
        "denoise",
        "sharpen",
        "tone_curve",
        "output_linear",
        "output_space",
    }


def test_auto_profile_batch_uses_render_recipe_after_profile_calibration(tmp_path: Path, monkeypatch):
    def fake_build_profile_with_argyll(
        out_icc: Path,
        measured_rgb: np.ndarray,
        reference_lab: np.ndarray,
        patch_ids: list[str],
        description: str,
        extra_args: list[str] | None,
    ) -> None:
        out_icc.write_bytes(
            profiling.build_matrix_shaper_icc(
                description=description,
                matrix_camera_to_xyz=np.eye(3),
                gamma=1.0,
            )
        )

    captured: dict[str, Recipe] = {}
    captured_workers: dict[str, int | None] = {}

    def fake_batch_develop(raws_dir, recipe, profile_path, out_dir, **_kwargs):
        captured["recipe"] = recipe
        captured_workers["workers"] = _kwargs.get("workers")
        return BatchManifest(
            recipe_sha256="unit",
            profile_path=str(profile_path),
            color_management_mode="unit",
            output_color_space=recipe.output_space,
            software_version="unit",
            entries=[],
        )

    monkeypatch.setattr(profiling, "_build_profile_with_argyll", fake_build_profile_with_argyll)
    monkeypatch.setattr(profiling, "_lookup_lab_with_icc", _fake_lookup_lab)
    monkeypatch.setattr(workflow, "batch_develop", fake_batch_develop)
    _patch_synthetic_raw_developer(monkeypatch)

    charts_dir = tmp_path / "charts"
    targets_dir = tmp_path / "targets"
    work_dir = tmp_path / "work_batch_render"
    out_dir = tmp_path / "out_batch_render"
    charts_dir.mkdir()
    targets_dir.mkdir()
    _write_synthetic_raw(charts_dir / "chart_01.NEF", _synthetic_colorchecker_image())

    repo_root = Path(__file__).resolve().parents[1]
    reference = ReferenceCatalog.from_path(repo_root / "testdata/references/colorchecker24_reference.json")
    recipe = Recipe(
        tone_curve="srgb",
        output_linear=False,
        output_space="srgb",
        denoise="mild",
        sharpen="medium",
    )

    auto_profile_batch(
        chart_captures_dir=charts_dir,
        target_captures_dir=targets_dir,
        recipe=recipe,
        reference=reference,
        profile_out=tmp_path / "batch_render.icc",
        profile_report_out=tmp_path / "batch_render_report.json",
        batch_out_dir=out_dir,
        work_dir=work_dir,
        chart_type="colorchecker24",
        min_confidence=0.0,
        allow_fallback_detection=True,
        qa_mean_delta_e2000_max=999.0,
        qa_max_delta_e2000_max=999.0,
        workers=3,
        c2pa_config=_fake_c2pa_config(tmp_path),
        proof_config=_proof_config(tmp_path),
    )

    assert captured["recipe"].tone_curve == "linear"
    assert captured["recipe"].output_linear is True
    assert captured["recipe"].output_space == "scene_linear_camera_rgb"
    assert captured["recipe"].denoise == "mild"
    assert captured["recipe"].sharpen == "medium"
    assert captured_workers["workers"] == 3


def test_auto_generate_profile_rejects_non_raw_chart_files(tmp_path: Path):
    reference = ReferenceCatalog({"chart_name": "unit", "chart_version": "1", "illuminant": "D50", "patches": []})
    jpg = tmp_path / "chart.jpg"
    tiff = tmp_path / "chart.tiff"
    jpg.write_bytes(b"not-a-scientific-chart-source")
    tiff.write_bytes(b"not-a-raw-chart-source")

    with pytest.raises(RuntimeError, match="solo RAW/DNG originales"):
        auto_generate_profile_from_charts(
            chart_captures_dir=tmp_path / "unused",
            chart_capture_files=[jpg, tiff],
            recipe=Recipe(),
            reference=reference,
            profile_out=tmp_path / "bad_ext.icc",
            profile_report_out=tmp_path / "bad_ext_report.json",
            work_dir=tmp_path / "work_bad_ext",
        )


def _fake_lookup_lab(_profile: Path, measured_rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(measured_rgb, dtype=np.float64)
    base = np.array([50.0, 0.0, 0.0], dtype=np.float64)
    return np.repeat(base.reshape(1, 3), rgb.shape[0], axis=0)


def _synthetic_colorchecker_image() -> np.ndarray:
    rows, cols = 4, 6
    cell_h, cell_w = 120, 120
    h, w = rows * cell_h, cols * cell_w
    img = np.zeros((h, w, 3), dtype=np.uint16)

    # Deterministic patch palette with luminance progression.
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            rgb = np.array([
                3000 + idx * 1500,
                5000 + idx * 1200,
                7000 + idx * 900,
            ], dtype=np.uint16)
            y0, y1 = r * cell_h, (r + 1) * cell_h
            x0, x1 = c * cell_w, (c + 1) * cell_w
            img[y0:y1, x0:x1] = rgb

    return img
