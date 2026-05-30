from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import os
from pathlib import Path
from typing import Any

import numpy as np

from .chart.detection import detect_chart_from_array, draw_detection_overlay_array
from .chart.sampling import ReferenceCatalog, sample_chart_from_array
from .core.models import (
    ChartDetectionResult,
    PatchDetection,
    PatchSample,
    Point2,
    Recipe,
    SampleSet,
    to_json_dict,
    write_json,
)
from .core.recipe import load_recipe, save_recipe, scientific_guard
from .core.utils import RAW_EXTENSIONS, write_tiff16
from .profile.builder import build_profile, validate_profile
from .profile.development import build_development_profile
from .profile.export import batch_develop
from .provenance.c2pa import C2PASignConfig
from .provenance.probraw_proof import ProbRawProofConfig
from .raw.pipeline import develop_image_array


PROFILE_CHART_EXTENSIONS = set(RAW_EXTENSIONS)
NEUTRAL_PATCH_IDS = ("P19", "P20", "P21", "P22", "P23", "P24")
LUMA_WEIGHTS = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float64)
LOW_SIGNAL_BRIGHT_NEUTRAL_MIN = 0.25
LOW_SIGNAL_MEDIAN_LUMA_MIN = 0.05
NEUTRAL_DENSITY_SPREAD_EV_MAX = 0.35
NEUTRAL_ILLUMINATION_GRADIENT_EV_MAX = 0.25
NEUTRAL_AB_RESIDUAL_WARN = 3.0
PROFILE_NEUTRAL_MAX_SATURATED_PIXEL_RATIO = 0.02
PROFILE_PATCH_MAX_SATURATED_PIXEL_RATIO = 0.20
PROFILE_MODEL_FLAGS = {
    "-as": "shaper+matrix",
    "-ag": "gamma+matrix",
    "-am": "matrix",
    "-al": "Lab cLUT",
    "-ax": "XYZ cLUT",
}
SPARSE_CHART_RISKY_PROFILE_FLAGS = {"-ax"}
PROFILE_STATUS_DRAFT = "draft"
PROFILE_STATUS_VALIDATED = "validated"
PROFILE_STATUS_REJECTED = "rejected"
PROFILE_STATUS_EXPIRED = "expired"
DEFAULT_QA_MEAN_DELTA_E2000_MAX = 5.0
DEFAULT_QA_MAX_DELTA_E2000_MAX = 10.0


def _emit_workflow_progress(
    progress_callback: Any | None,
    progress: float,
    phase: str,
    detail: str = "",
    *,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if progress_callback is None:
        return
    payload: dict[str, Any] = {
        "progress": max(0, min(100, int(round(float(progress))))),
        "phase": str(phase),
        "detail": str(detail or ""),
    }
    if current is not None:
        payload["current"] = int(current)
    if total is not None:
        payload["total"] = int(total)
    progress_callback(payload)


def auto_generate_profile_from_charts(
    chart_captures_dir: Path,
    recipe: Recipe,
    reference: ReferenceCatalog,
    profile_out: Path,
    profile_report_out: Path,
    work_dir: Path,
    development_profile_out: Path | None = None,
    calibrated_recipe_out: Path | None = None,
    calibrate_development: bool = True,
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    allow_fallback_detection: bool = False,
    camera_model: str | None = None,
    lens_model: str | None = None,
    chart_capture_files: list[Path] | None = None,
    manual_detections: dict[Path, Any] | None = None,
    validation_holdout_count: int = 0,
    validation_report_out: Path | None = None,
    qa_mean_delta_e2000_max: float = DEFAULT_QA_MEAN_DELTA_E2000_MAX,
    qa_max_delta_e2000_max: float = DEFAULT_QA_MAX_DELTA_E2000_MAX,
    profile_validity_days: int | None = None,
    cache_dir: Path | None = None,
    profile_workers: int | None = None,
    profile_artifacts: str = "full",
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    _emit_workflow_progress(
        progress_callback,
        1,
        "Preparando perfil",
        "Normalizando receta y preparando carpetas de trabajo",
    )
    requested_recipe = recipe
    profile_recipe, recipe_normalizations = sanitize_recipe_for_profiling(requested_recipe)
    render_recipe = requested_recipe
    _enforce_profile_recipe_guard(profile_recipe, phase="receta de perfilado inicial")
    work_dir.mkdir(parents=True, exist_ok=True)
    chart_dev_dir = work_dir / "chart_developed"
    detect_dir = work_dir / "detections"
    sample_dir = work_dir / "samples"
    overlay_dir = work_dir / "overlays"
    profile_recipe_file = work_dir / "recipe_profile_scientific.yml"

    for d in (chart_dev_dir, detect_dir, sample_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    chart_files = (
        _normalize_chart_capture_files(chart_capture_files)
        if chart_capture_files is not None
        else _list_chart_capture_files(chart_captures_dir)
    )
    if not chart_files:
        source = "la selección explícita" if chart_capture_files is not None else str(chart_captures_dir)
        raise RuntimeError(f"No se encontraron capturas de carta en: {source}")
    manual_detection_map = _normalize_detection_map(manual_detections)
    training_files, validation_files = _split_training_validation_files(
        chart_files,
        validation_holdout_count,
        preferred_training_files=list(manual_detection_map.keys()) if manual_detection_map else None,
    )
    _emit_workflow_progress(
        progress_callback,
        6,
        "Seleccionando capturas",
        f"{len(training_files)} de entrenamiento, {len(validation_files)} de validacion",
    )

    initial_pass = _collect_chart_samples(
        chart_files=training_files,
        recipe=profile_recipe,
        reference=reference,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        chart_dev_dir=chart_dev_dir,
        detect_dir=detect_dir,
        sample_dir=sample_dir,
        overlay_dir=overlay_dir,
        pass_name="development_profile_source",
        existing_detections=manual_detection_map,
        existing_detection_note="geometria de carta desde deteccion manual guardada",
        cache_dir=cache_dir,
        workers=profile_workers,
        artifacts=profile_artifacts,
        progress_callback=progress_callback,
        progress_start=8,
        progress_end=28 if calibrate_development else 54,
        progress_phase="Muestreando carta",
    )
    accepted_samples = initial_pass["accepted_samples"]
    skipped: list[dict[str, Any]] = list(initial_pass["skipped"])

    if not accepted_samples:
        detail = _skipped_capture_summary(skipped)
        suffix = f" Detalle: {detail}" if detail else ""
        raise RuntimeError(
            "No hubo capturas de carta válidas para construir perfil. "
            "Revisa exposición, encuadre de carta y min_confidence."
            f"{suffix}"
        )

    _emit_workflow_progress(
        progress_callback,
        31 if calibrate_development else 58,
        "Agregando muestras",
        "Combinando parches medidos antes de construir el perfil",
    )
    aggregated_initial = _aggregate_samples(accepted_samples, strategy=profile_recipe.sampling_strategy)
    write_json(work_dir / "samples_aggregated_development_source.json", aggregated_initial)

    development_profile_path: str | None = None
    calibrated_recipe_path: str | None = None
    development_payload: dict[str, Any] | None = None

    if calibrate_development:
        _emit_workflow_progress(
            progress_callback,
            36,
            "Calibrando revelado",
            "Ajustando neutralidad y respuesta tonal de la receta de perfilado",
        )
        development = build_development_profile(samples=aggregated_initial, base_recipe=profile_recipe)
        development_profile_file = development_profile_out or (work_dir / "development_profile.json")
        calibrated_recipe_file = calibrated_recipe_out or (work_dir / "recipe_calibrated.yml")
        profile_recipe = development.calibrated_recipe
        render_recipe = apply_profile_calibration_to_render_recipe(render_recipe, profile_recipe)
        _enforce_profile_recipe_guard(profile_recipe, phase="receta calibrada de perfilado")
        save_recipe(profile_recipe, profile_recipe_file)
        save_recipe(render_recipe, calibrated_recipe_file)
        development_payload = to_json_dict(development)
        development_payload["profile_calibrated_recipe"] = development_payload.get("calibrated_recipe", asdict(profile_recipe))
        development_payload["render_calibrated_recipe"] = asdict(render_recipe)
        development_payload["calibrated_recipe"] = asdict(render_recipe)
        development_payload["profile_recipe_path"] = str(profile_recipe_file)
        development_payload["render_recipe_path"] = str(calibrated_recipe_file)
        write_json(development_profile_file, development_payload)
        development_profile_path = str(development_profile_file)
        calibrated_recipe_path = str(calibrated_recipe_file)

        _emit_workflow_progress(
            progress_callback,
            44,
            "Remuestreando carta",
            "Repitiendo deteccion y muestreo con la receta calibrada",
        )
        calibrated_pass = _collect_chart_samples(
            chart_files=training_files,
            recipe=profile_recipe,
            reference=reference,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            existing_detections=initial_pass["detections"],
            chart_dev_dir=work_dir / "chart_developed_calibrated",
            detect_dir=work_dir / "detections_calibrated",
            sample_dir=work_dir / "samples_calibrated",
            overlay_dir=work_dir / "overlays_calibrated",
            pass_name="icc_profile_source",
            cache_dir=cache_dir,
            workers=profile_workers,
            artifacts=profile_artifacts,
            progress_callback=progress_callback,
            progress_start=45,
            progress_end=62,
            progress_phase="Remuestreando carta",
        )
        accepted_samples = calibrated_pass["accepted_samples"]
        skipped.extend(calibrated_pass["skipped"])
        if not accepted_samples:
            detail = _skipped_capture_summary(skipped)
            suffix = f" Detalle: {detail}" if detail else ""
            raise RuntimeError(
                "No hubo capturas válidas tras aplicar el perfil de revelado. "
                "Revisa el JSON de desarrollo y los overlays calibrados."
                f"{suffix}"
            )

    _emit_workflow_progress(
        progress_callback,
        64,
        "Preparando ICC",
        "Escribiendo datos medidos y receta cientifica para colprof",
    )
    aggregated_samples = _aggregate_samples(accepted_samples, strategy=profile_recipe.sampling_strategy)
    aggregated_samples_path = work_dir / "samples_aggregated.json"
    write_json(aggregated_samples_path, aggregated_samples)
    save_recipe(profile_recipe, profile_recipe_file)

    _emit_workflow_progress(
        progress_callback,
        68,
        "Construyendo ICC",
        "Calculando la transformacion colorimetrica del perfil de entrada",
    )
    profile_result = build_profile(
        samples=aggregated_samples,
        recipe=profile_recipe,
        out_icc=profile_out,
        camera_model=camera_model,
        lens_model=lens_model,
    )
    training_neutral_axis_error = _neutral_axis_error_summary(profile_result.patch_errors)
    if training_neutral_axis_error is not None:
        profile_result.metadata["neutral_axis_error"] = training_neutral_axis_error

    _emit_workflow_progress(
        progress_callback,
        76,
        "ICC construido",
        f"Perfil escrito en {Path(profile_out).name}",
    )
    validation_payload: dict[str, Any] | None = None
    qa_report_path: str | None = None
    if validation_files:
        _emit_workflow_progress(
            progress_callback,
            78,
            "Preparando validacion",
            "Reutilizando geometria de carta para capturas independientes",
        )
        validation_detection_map = _validation_detection_map(
            validation_files=validation_files,
            manual_detection_map=manual_detection_map,
            recipe=recipe,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            work_dir=work_dir,
            cache_dir=cache_dir,
        )
        _emit_workflow_progress(
            progress_callback,
            82,
            "Validando ICC",
            "Muestreando capturas de validacion independiente",
        )
        validation_pass = _collect_chart_samples(
            chart_files=validation_files,
            recipe=profile_recipe,
            reference=reference,
            chart_type=chart_type,
            min_confidence=min_confidence,
            allow_fallback_detection=allow_fallback_detection,
            chart_dev_dir=work_dir / "chart_developed_validation",
            detect_dir=work_dir / "detections_validation",
            sample_dir=work_dir / "samples_validation",
            overlay_dir=work_dir / "overlays_validation",
            pass_name="icc_validation_source",
            existing_detections=validation_detection_map,
            existing_detection_note="geometria de carta reutilizada desde pasada base de validacion",
            cache_dir=cache_dir,
            workers=profile_workers,
            artifacts=profile_artifacts,
            progress_callback=progress_callback,
            progress_start=83,
            progress_end=90,
            progress_phase="Validando ICC",
        )
        validation_samples = validation_pass["accepted_samples"]
        skipped.extend(validation_pass["skipped"])

        validation_result_payload: dict[str, Any] | None = None
        validation_samples_path: str | None = None
        if validation_samples:
            _emit_workflow_progress(
                progress_callback,
                92,
                "Calculando QA",
                "Comparando Lab medido contra referencia y perfil ICC",
            )
            aggregated_validation = _aggregate_samples(validation_samples, strategy=profile_recipe.sampling_strategy)
            aggregated_validation_path = work_dir / "samples_aggregated_validation.json"
            write_json(aggregated_validation_path, aggregated_validation)
            validation_samples_path = str(aggregated_validation_path)
            validation_result = validate_profile(samples=aggregated_validation, profile_path=profile_out)
            validation_result_payload = to_json_dict(validation_result)

        qa_report = _build_session_qa_report(
            training_files=training_files,
            validation_files=validation_files,
            training_samples=aggregated_samples,
            validation_samples=_aggregate_samples(validation_samples, strategy=profile_recipe.sampling_strategy)
            if validation_samples
            else None,
            training_capture_samples=accepted_samples,
            validation_capture_samples=validation_samples,
            training_profile_result=profile_result,
            validation_result=validation_result_payload,
            validation_skipped=validation_pass["skipped"],
            qa_mean_delta_e2000_max=qa_mean_delta_e2000_max,
            qa_max_delta_e2000_max=qa_max_delta_e2000_max,
        )
        qa_file = validation_report_out or (work_dir / "qa_session_report.json")
        write_json(qa_file, qa_report)
        qa_report_path = str(qa_file)
        validation_payload = {
            "validation_captures_total": len(validation_files),
            "validation_captures_used": len(validation_samples),
            "validation_captures_skipped": validation_pass["skipped"],
            "validation_samples": validation_samples_path,
            "validation_result": validation_result_payload,
            "qa_report": qa_report,
            "qa_report_path": qa_report_path,
        }
    else:
        _emit_workflow_progress(
            progress_callback,
            90,
            "Sin validacion independiente",
            "No hay capturas reservadas para holdout; se usara la QA contra la referencia colorimetrica de la carta",
        )

    _emit_workflow_progress(
        progress_callback,
        95,
        "Escribiendo informes",
        "Guardando metadatos, QA y recomendaciones de perfil",
    )
    profile_generated_at = _utc_now_iso()
    profile_valid_until = _profile_valid_until(profile_generated_at, profile_validity_days)
    profile_status = _build_profile_status(
        validation_payload=validation_payload,
        qa_report_path=qa_report_path,
        generated_at=profile_generated_at,
        valid_until=profile_valid_until,
        training_error_summary=asdict(profile_result.error_summary),
        qa_mean_delta_e2000_max=qa_mean_delta_e2000_max,
        qa_max_delta_e2000_max=qa_max_delta_e2000_max,
    )
    workflow_recommendations = _profile_workflow_recommendations(
        chart_type=chart_type,
        reference=reference,
        recipe=profile_recipe,
        chart_files=chart_files,
        validation_files=validation_files,
        validation_payload=validation_payload,
        training_neutral_axis_error=training_neutral_axis_error,
    )
    profile_result.metadata["session_profile_status"] = profile_status
    profile_result.metadata["profile_status"] = profile_status["status"]
    profile_result.metadata["workflow_recommendations"] = workflow_recommendations
    profile_result.metadata["recipe_profiling_normalizations"] = recipe_normalizations
    profile_result.metadata["requested_recipe"] = asdict(requested_recipe)
    profile_result.metadata["profile_recipe"] = asdict(profile_recipe)
    profile_result.metadata["profile_recipe_path"] = str(profile_recipe_file)
    profile_result.metadata["render_recipe"] = asdict(render_recipe)
    profile_result.metadata["render_recipe_path"] = calibrated_recipe_path
    write_json(Path(profile_result.output_profile_json), profile_result.metadata)
    write_json(profile_report_out, profile_result)

    _emit_workflow_progress(
        progress_callback,
        100,
        "Perfil finalizado",
        f"Estado: {profile_status['status']}",
    )
    return {
        "chart_captures_total": len(chart_files),
        "training_captures_total": len(training_files),
        "chart_captures_used": len(accepted_samples),
        "chart_captures_skipped": skipped,
        "validation_captures_total": len(validation_files),
        "validation_captures_used": validation_payload["validation_captures_used"] if validation_payload else 0,
        "development_profile_path": development_profile_path,
        "calibrated_recipe_path": calibrated_recipe_path,
        "development_profile": development_payload,
        "aggregated_samples": str(aggregated_samples_path),
        "profile": to_json_dict(profile_result),
        "profile_status": profile_status,
        "profile_report_path": str(profile_report_out),
        "profile_recipe_path": str(profile_recipe_file),
        "render_recipe": asdict(render_recipe),
        "render_recipe_path": calibrated_recipe_path,
        "validation": validation_payload,
        "qa_report_path": qa_report_path,
        "workflow_recommendations": workflow_recommendations,
        "recipe_profiling_normalizations": recipe_normalizations,
    }


def auto_profile_batch(
    chart_captures_dir: Path,
    target_captures_dir: Path,
    recipe: Recipe,
    reference: ReferenceCatalog,
    profile_out: Path,
    profile_report_out: Path,
    batch_out_dir: Path,
    work_dir: Path,
    development_profile_out: Path | None = None,
    calibrated_recipe_out: Path | None = None,
    calibrate_development: bool = True,
    chart_type: str = "colorchecker24",
    min_confidence: float = 0.35,
    allow_fallback_detection: bool = False,
    camera_model: str | None = None,
    lens_model: str | None = None,
    chart_capture_files: list[Path] | None = None,
    manual_detections: dict[Path, Any] | None = None,
    validation_holdout_count: int = 0,
    validation_report_out: Path | None = None,
    qa_mean_delta_e2000_max: float = DEFAULT_QA_MEAN_DELTA_E2000_MAX,
    qa_max_delta_e2000_max: float = DEFAULT_QA_MAX_DELTA_E2000_MAX,
    profile_validity_days: int | None = None,
    workers: int | None = None,
    cache_dir: Path | None = None,
    c2pa_config: C2PASignConfig | None = None,
    proof_config: ProbRawProofConfig | None = None,
    profile_workers: int | None = None,
    profile_artifacts: str = "full",
) -> dict[str, Any]:
    profile_payload = auto_generate_profile_from_charts(
        chart_captures_dir=chart_captures_dir,
        recipe=recipe,
        reference=reference,
        profile_out=profile_out,
        profile_report_out=profile_report_out,
        work_dir=work_dir,
        development_profile_out=development_profile_out,
        calibrated_recipe_out=calibrated_recipe_out,
        calibrate_development=calibrate_development,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        camera_model=camera_model,
        lens_model=lens_model,
        chart_capture_files=chart_capture_files,
        manual_detections=manual_detections,
        validation_holdout_count=validation_holdout_count,
        validation_report_out=validation_report_out,
        qa_mean_delta_e2000_max=qa_mean_delta_e2000_max,
        qa_max_delta_e2000_max=qa_max_delta_e2000_max,
        profile_validity_days=profile_validity_days,
        cache_dir=cache_dir,
        profile_workers=profile_workers,
        profile_artifacts=profile_artifacts,
    )

    batch_recipe = recipe
    calibrated_path = profile_payload.get("calibrated_recipe_path")
    if isinstance(calibrated_path, str) and calibrated_path:
        batch_recipe = load_recipe(Path(calibrated_path))

    status_payload = profile_payload.get("profile_status") if isinstance(profile_payload.get("profile_status"), dict) else {}
    status = str(status_payload.get("status") or PROFILE_STATUS_DRAFT)
    if status in {PROFILE_STATUS_REJECTED, PROFILE_STATUS_EXPIRED}:
        raise RuntimeError(f"Perfil de sesion no aplicable al lote: estado {status}")

    manifest = batch_develop(
        raws_dir=target_captures_dir,
        recipe=batch_recipe,
        profile_path=profile_out,
        out_dir=batch_out_dir,
        workers=workers,
        cache_dir=cache_dir,
        c2pa_config=c2pa_config,
        proof_config=proof_config,
    )
    manifest_path = batch_out_dir / "batch_manifest.json"
    write_json(manifest_path, manifest)

    return {
        "chart_captures_total": profile_payload["chart_captures_total"],
        "chart_captures_used": profile_payload["chart_captures_used"],
        "chart_captures_skipped": profile_payload["chart_captures_skipped"],
        "development_profile_path": profile_payload.get("development_profile_path"),
        "calibrated_recipe_path": profile_payload.get("calibrated_recipe_path"),
        "profile_recipe_path": profile_payload.get("profile_recipe_path"),
        "recipe_profiling_normalizations": profile_payload.get("recipe_profiling_normalizations"),
        "render_recipe": profile_payload.get("render_recipe"),
        "render_recipe_path": profile_payload.get("render_recipe_path"),
        "development_profile": profile_payload.get("development_profile"),
        "aggregated_samples": profile_payload["aggregated_samples"],
        "profile": profile_payload["profile"],
        "profile_status": profile_payload.get("profile_status"),
        "profile_report_path": profile_payload["profile_report_path"],
        "validation_captures_total": profile_payload.get("validation_captures_total", 0),
        "validation_captures_used": profile_payload.get("validation_captures_used", 0),
        "validation": profile_payload.get("validation"),
        "qa_report_path": profile_payload.get("qa_report_path"),
        "batch_manifest": to_json_dict(manifest),
        "batch_manifest_path": str(manifest_path),
    }


def sanitize_recipe_for_profiling(recipe: Recipe) -> tuple[Recipe, list[dict[str, str]]]:
    """Force the scientific-mode constraints required for chart measurement.

    Returns the normalized recipe plus a list of changes describing every field
    that had to be rewritten so the caller (CLI or GUI) can surface them.
    """
    changes: list[dict[str, str]] = []
    updates: dict[str, Any] = {}

    if recipe.white_balance_mode.strip().lower() != "fixed":
        changes.append({"field": "white_balance_mode", "from": str(recipe.white_balance_mode), "to": "fixed"})
        updates["white_balance_mode"] = "fixed"
    try:
        wb_values = [float(v) for v in (recipe.wb_multipliers or [])]
    except (TypeError, ValueError):
        wb_values = []
    if len(wb_values) != 4 or any(abs(value - 1.0) > 1e-6 for value in wb_values):
        changes.append({"field": "wb_multipliers", "from": str(recipe.wb_multipliers), "to": "[1.0, 1.0, 1.0, 1.0]"})
        updates["wb_multipliers"] = [1.0, 1.0, 1.0, 1.0]
    if abs(float(recipe.exposure_compensation)) > 1e-6:
        changes.append({"field": "exposure_compensation", "from": str(recipe.exposure_compensation), "to": "0.0"})
        updates["exposure_compensation"] = 0.0
    if recipe.denoise.lower() != "off":
        changes.append({"field": "denoise", "from": str(recipe.denoise), "to": "off"})
        updates["denoise"] = "off"
    if recipe.sharpen.lower() != "off":
        changes.append({"field": "sharpen", "from": str(recipe.sharpen), "to": "off"})
        updates["sharpen"] = "off"
    if recipe.tone_curve.lower() != "linear":
        changes.append({"field": "tone_curve", "from": str(recipe.tone_curve), "to": "linear"})
        updates["tone_curve"] = "linear"
    if not recipe.output_linear:
        changes.append({"field": "output_linear", "from": str(recipe.output_linear), "to": "True"})
        updates["output_linear"] = True
    output_space = str(recipe.output_space or "").strip().lower()
    if output_space not in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        changes.append({"field": "output_space", "from": str(recipe.output_space), "to": "scene_linear_camera_rgb"})
        updates["output_space"] = "scene_linear_camera_rgb"
    if not recipe.profiling_mode:
        changes.append({"field": "profiling_mode", "from": str(recipe.profiling_mode), "to": "True"})
        updates["profiling_mode"] = True

    if not updates:
        return recipe, changes
    return replace(recipe, **updates), changes


def apply_profile_calibration_to_render_recipe(render_recipe: Recipe, profile_recipe: Recipe) -> Recipe:
    """Transfer measured session calibration to the session-master render recipe.

    Once a chart has produced a session ICC, the master TIFF must stay in the
    same linear camera/session RGB domain used to build that ICC. Generic output
    spaces such as sRGB are reserved for derivative exports without a session
    profile, or for an explicit CMM conversion step after the master render.
    """
    return replace(
        render_recipe,
        white_balance_mode="fixed",
        wb_multipliers=[float(v) for v in profile_recipe.wb_multipliers],
        exposure_compensation=float(profile_recipe.exposure_compensation),
        tone_curve="linear",
        output_linear=True,
        working_space="scene_linear_camera_rgb",
        output_space="scene_linear_camera_rgb",
    )


def _enforce_profile_recipe_guard(recipe: Recipe, *, phase: str) -> None:
    guard = scientific_guard(recipe)
    errors = list(guard.warnings)
    if recipe.denoise.lower() != "off":
        errors.append(f"denoise debe estar desactivado durante perfilado: {recipe.denoise}")
    if recipe.sharpen.lower() != "off":
        errors.append(f"sharpen debe estar desactivado durante perfilado: {recipe.sharpen}")
    if recipe.tone_curve.lower() != "linear":
        errors.append(f"tone_curve debe ser linear durante perfilado: {recipe.tone_curve}")
    if not recipe.output_linear:
        errors.append("output_linear debe estar activo durante perfilado")
    output_space = str(recipe.output_space or "").strip().lower()
    if output_space not in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        errors.append(f"output_space debe conservar RGB de camara lineal durante perfilado: {recipe.output_space}")

    if errors:
        joined = "; ".join(dict.fromkeys(str(item) for item in errors))
        raise RuntimeError(f"{phase} no apta para perfilado cientifico: {joined}")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _profile_valid_until(generated_at: str, profile_validity_days: int | None) -> str | None:
    if profile_validity_days is None:
        return None
    generated = _parse_iso_datetime(generated_at)
    return (generated + timedelta(days=int(profile_validity_days))).replace(microsecond=0).isoformat()


def _build_profile_status(
    *,
    validation_payload: dict[str, Any] | None,
    qa_report_path: str | None,
    generated_at: str,
    valid_until: str | None,
    training_error_summary: dict[str, Any] | None = None,
    qa_mean_delta_e2000_max: float = DEFAULT_QA_MEAN_DELTA_E2000_MAX,
    qa_max_delta_e2000_max: float = DEFAULT_QA_MAX_DELTA_E2000_MAX,
    now: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    validation_status: str | None = None
    training_status: str | None = None

    status = PROFILE_STATUS_DRAFT
    if validation_payload is None:
        reasons.append("validacion_independiente_no_disponible")
    else:
        qa_report = validation_payload.get("qa_report") if isinstance(validation_payload.get("qa_report"), dict) else {}
        validation_status = str(qa_report.get("status") or "not_validated")
        if validation_status == "validated":
            status = PROFILE_STATUS_VALIDATED
            reasons.append("validacion_colorimetrica_superada")
        elif validation_status == "rejected":
            status = PROFILE_STATUS_REJECTED
            reasons.append("validacion_colorimetrica_rechazada")
        else:
            status = PROFILE_STATUS_DRAFT
            reasons.append("validacion_no_concluyente")

    if training_error_summary:
        try:
            mean_de = float(training_error_summary.get("mean_delta_e2000", float("inf")))
            max_de = float(training_error_summary.get("max_delta_e2000", float("inf")))
        except (TypeError, ValueError):
            mean_de = float("inf")
            max_de = float("inf")
        if mean_de > float(qa_mean_delta_e2000_max) or max_de > float(qa_max_delta_e2000_max):
            status = PROFILE_STATUS_REJECTED
            training_status = "rejected"
            reasons.append("error_entrenamiento_colorimetrico_alto")
        else:
            training_status = "passed"
            if status == PROFILE_STATUS_DRAFT:
                status = PROFILE_STATUS_VALIDATED
                reasons.append("qa_entrenamiento_colorimetrico_superada")

    if status == PROFILE_STATUS_VALIDATED and valid_until:
        now_dt = _parse_iso_datetime(now) if now else datetime.now(timezone.utc)
        expires_dt = _parse_iso_datetime(valid_until)
        if expires_dt <= now_dt:
            status = PROFILE_STATUS_EXPIRED
            reasons.append("vigencia_expirada")

    return {
        "status": status,
        "generated_at": generated_at,
        "valid_until": valid_until,
        "validation_status": validation_status,
        "training_status": training_status,
        "training_error_summary": training_error_summary,
        "thresholds": {
            "mean_delta_e2000_max": float(qa_mean_delta_e2000_max),
            "max_delta_e2000_max": float(qa_max_delta_e2000_max),
        },
        "qa_report_path": qa_report_path,
        "reasons": reasons,
    }


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _split_training_validation_files(
    chart_files: list[Path],
    validation_holdout_count: int,
    *,
    preferred_training_files: list[Path] | None = None,
) -> tuple[list[Path], list[Path]]:
    files = list(chart_files)
    holdout = max(0, int(validation_holdout_count))
    if holdout <= 0 or len(files) < 2:
        return files, []

    holdout = min(holdout, len(files) - 1)
    preferred_keys = {
        str(Path(path).expanduser().resolve())
        for path in list(preferred_training_files or [])
    }
    if not preferred_keys:
        return list(files[:-holdout]), list(files[-holdout:])

    validation: list[Path] = []
    validation_keys: set[str] = set()
    for path in reversed(files):
        key = str(Path(path).expanduser().resolve())
        if key in preferred_keys:
            continue
        validation.append(path)
        validation_keys.add(key)
        if len(validation) >= holdout:
            break

    if len(validation) < holdout:
        for path in reversed(files):
            key = str(Path(path).expanduser().resolve())
            if key in validation_keys:
                continue
            validation.append(path)
            validation_keys.add(key)
            if len(validation) >= holdout:
                break

    training = [
        path
        for path in files
        if str(Path(path).expanduser().resolve()) not in validation_keys
    ]
    if not training:
        return files, []
    return training, [path for path in files if str(Path(path).expanduser().resolve()) in validation_keys]


def _build_session_qa_report(
    *,
    training_files: list[Path],
    validation_files: list[Path],
    training_samples: SampleSet,
    validation_samples: SampleSet | None,
    training_capture_samples: list[SampleSet],
    validation_capture_samples: list[SampleSet],
    training_profile_result: Any,
    validation_result: dict[str, Any] | None,
    validation_skipped: list[dict[str, Any]],
    qa_mean_delta_e2000_max: float,
    qa_max_delta_e2000_max: float,
) -> dict[str, Any]:
    training_error = asdict(training_profile_result.error_summary)
    validation_error = validation_result.get("error_summary") if validation_result else None

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "id": "validation_samples_available",
            "severity": "warning",
            "passed": validation_result is not None,
                "message": (
                    "hay muestras independientes de validacion"
                    if validation_result
                    else "no hay muestras independientes validas; la validacion independiente queda como diagnostico no concluyente"
                ),
            }
        )

    if validation_error:
        mean_de = float(validation_error.get("mean_delta_e2000", float("inf")))
        max_de = float(validation_error.get("max_delta_e2000", float("inf")))
        checks.extend(
            [
                {
                    "id": "validation_mean_delta_e2000",
                    "severity": "error",
                    "value": mean_de,
                    "limit": float(qa_mean_delta_e2000_max),
                    "passed": mean_de <= float(qa_mean_delta_e2000_max),
                },
                {
                    "id": "validation_max_delta_e2000",
                    "severity": "error",
                    "value": max_de,
                    "limit": float(qa_max_delta_e2000_max),
                    "passed": max_de <= float(qa_max_delta_e2000_max),
                },
            ]
        )

    training_quality = _sample_quality(training_samples)
    validation_quality = _sample_quality(validation_samples) if validation_samples else None
    training_worst_patches = _rank_patch_errors(getattr(training_profile_result, "patch_errors", []))
    validation_worst_patches = _rank_patch_errors(validation_result.get("patch_errors", [])) if validation_result else []
    training_patch_outliers = _patch_error_outliers(training_worst_patches, qa_max_delta_e2000_max)
    validation_patch_outliers = _patch_error_outliers(validation_worst_patches, qa_max_delta_e2000_max)
    training_neutral_axis_error = _neutral_axis_error_summary(getattr(training_profile_result, "patch_errors", []))
    validation_neutral_axis_error = _neutral_axis_error_summary(validation_result.get("patch_errors", [])) if validation_result else None
    training_capture_quality = _capture_quality_summary(training_capture_samples)
    validation_capture_quality = _capture_quality_summary(validation_capture_samples) if validation_capture_samples else None
    for label, quality in (("training", training_quality), ("validation", validation_quality)):
        if not quality:
            continue
        max_sat = float(quality["max_saturated_pixel_ratio"])
        checks.append(
            {
                "id": f"{label}_max_saturation",
                "severity": "warning",
                "value": max_sat,
                "limit": 0.02,
                "passed": max_sat <= 0.02,
            }
        )

    for label, quality in (("training", training_capture_quality), ("validation", validation_capture_quality)):
        if not quality:
            continue
        checks.extend(_capture_quality_checks(label, quality))

    for label, outliers in (("training", training_patch_outliers), ("validation", validation_patch_outliers)):
        if not outliers:
            continue
        checks.append(
            {
                "id": f"{label}_patch_delta_e2000_outliers",
                "severity": "warning",
                "value": len(outliers),
                "limit": float(qa_max_delta_e2000_max),
                "passed": False,
                "patch_ids": [str(item["patch_id"]) for item in outliers],
            }
        )

    for label, neutral_error in (
        ("training", training_neutral_axis_error),
        ("validation", validation_neutral_axis_error),
    ):
        if not neutral_error:
            continue
        max_residual = float(neutral_error.get("max_ab_residual", 0.0))
        checks.append(
            {
                "id": f"{label}_neutral_axis_residual",
                "severity": "warning",
                "value": max_residual,
                "limit": NEUTRAL_AB_RESIDUAL_WARN,
                "passed": max_residual <= NEUTRAL_AB_RESIDUAL_WARN,
                "message": "deriva a*/b* en fila neutra; aviso de dominantes sin bloquear la generacion",
            }
        )

    hard_failures = [check for check in checks if check["severity"] == "error" and not check["passed"]]
    if validation_result is None:
        status = "not_validated"
    elif hard_failures:
        status = "rejected"
    else:
        status = "validated"

    return {
        "status": status,
        "training_captures": [str(p) for p in training_files],
        "validation_captures": [str(p) for p in validation_files],
        "thresholds": {
            "mean_delta_e2000_max": float(qa_mean_delta_e2000_max),
            "max_delta_e2000_max": float(qa_max_delta_e2000_max),
        },
        "training_error_summary": training_error,
        "validation_error_summary": validation_error,
        "training_sample_quality": training_quality,
        "validation_sample_quality": validation_quality,
        "training_capture_quality": training_capture_quality,
        "validation_capture_quality": validation_capture_quality,
        "training_worst_patches": training_worst_patches[:8],
        "validation_worst_patches": validation_worst_patches[:8],
        "training_patch_outliers": training_patch_outliers,
        "validation_patch_outliers": validation_patch_outliers,
        "training_neutral_axis_error": training_neutral_axis_error,
        "validation_neutral_axis_error": validation_neutral_axis_error,
        "validation_skipped": validation_skipped,
        "checks": checks,
    }


def _profile_workflow_recommendations(
    *,
    chart_type: str,
    reference: ReferenceCatalog,
    recipe: Recipe,
    chart_files: list[Path],
    validation_files: list[Path],
    validation_payload: dict[str, Any] | None,
    training_neutral_axis_error: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    validation_usable = bool(
        validation_payload
        and int(validation_payload.get("validation_captures_used") or 0) > 0
        and isinstance(validation_payload.get("validation_result"), dict)
    )

    if len(chart_files) < 2:
        recommendations.append(
            {
                "id": "repeat_chart_capture_recommended",
                "severity": "info",
                "blocking": False,
                "message": (
                    "El perfil se ha generado con una sola captura de carta. "
                    "Cuando sea posible, captura otra carta equivalente para validar o promediar la sesion."
                ),
            }
        )
    elif not validation_files or not validation_usable:
        recommendations.append(
            {
                "id": "independent_validation_recommended",
                "severity": "info",
                "blocking": False,
                "message": (
                    "Hay suficientes capturas para trabajar, pero no hay validacion independiente utilizable. "
                    "El estado operativo se decide por la QA contra la referencia colorimetrica de la carta; "
                    "usa otra captura solo como diagnostico adicional cuando sea posible."
                ),
            }
        )

    model_flag = _colprof_profile_model_flag(recipe.argyll_colprof_args)
    if str(chart_type or "").strip().lower() == "colorchecker24" and model_flag in SPARSE_CHART_RISKY_PROFILE_FLAGS:
        recommendations.append(
            {
                "id": "colorchecker24_xyz_clut_sparse_risk",
                "severity": "warning",
                "blocking": False,
                "message": (
                    "Con ColorChecker 24, XYZ cLUT (-ax) puede ser menos robusto si la carta es escasa "
                    "o irregular. Lab cLUT (-al) es el preset recomendado; matriz (-am) queda como "
                    "opcion tecnica para RAW lineal cuando se busca maxima simplicidad."
                ),
            }
        )

    if _reference_is_generic_colorchecker(reference):
        recommendations.append(
            {
                "id": "measured_chart_reference_recommended",
                "severity": "info",
                "blocking": False,
                "message": (
                    "La referencia de carta parece generica. Para trabajos criticos, importa una medicion "
                    "Lab D50 de la carta fisica usada y registra serie, fecha e instrumento."
                ),
            }
        )

    if training_neutral_axis_error:
        max_residual = float(training_neutral_axis_error.get("max_ab_residual", 0.0))
        if max_residual > NEUTRAL_AB_RESIDUAL_WARN:
            recommendations.append(
                {
                    "id": "neutral_axis_review_recommended",
                    "severity": "warning",
                    "blocking": False,
                    "message": (
                        "La fila neutra muestra deriva a*/b*. Revisa iluminacion, exposicion, balance "
                        "y encuadre antes de usar el perfil en trabajo critico."
                    ),
                }
            )

    return recommendations


def _colprof_profile_model_flag(args: list[str] | None) -> str:
    raw_args = list(args or [])
    for arg in raw_args:
        if str(arg) in PROFILE_MODEL_FLAGS:
            return str(arg)
    return "-al"


def _reference_is_generic_colorchecker(reference: ReferenceCatalog) -> bool:
    text = " ".join(
        [
            str(reference.chart_name or ""),
            str(reference.chart_version or ""),
            str(reference.reference_source or ""),
        ]
    ).lower()
    if "colorchecker" not in text:
        return False
    custom_markers = ("personalizada", "medicion personalizada", "medición personalizada", "measured", "spectro")
    return not any(marker in text for marker in custom_markers)


def _neutral_axis_error_summary(errors: Any) -> dict[str, Any] | None:
    records: list[dict[str, Any]] = []
    for item in errors if isinstance(errors, list) else []:
        data = asdict(item) if hasattr(item, "__dataclass_fields__") else item if isinstance(item, dict) else None
        if not isinstance(data, dict):
            continue
        patch_id = str(data.get("patch_id") or "").strip()
        if patch_id not in NEUTRAL_PATCH_IDS:
            continue
        reference_lab = _coerce_lab(data.get("reference_lab"))
        profile_lab = _coerce_lab(data.get("profile_lab"))
        if reference_lab is None or profile_lab is None:
            continue
        delta_l = float(profile_lab[0] - reference_lab[0])
        delta_a = float(profile_lab[1] - reference_lab[1])
        delta_b = float(profile_lab[2] - reference_lab[2])
        records.append(
            {
                "patch_id": patch_id,
                "delta_l": delta_l,
                "delta_a": delta_a,
                "delta_b": delta_b,
                "ab_residual": float((delta_a**2 + delta_b**2) ** 0.5),
            }
        )

    if not records:
        return None

    residuals = np.asarray([float(item["ab_residual"]) for item in records], dtype=np.float64)
    delta_a_values = np.asarray([float(item["delta_a"]) for item in records], dtype=np.float64)
    delta_b_values = np.asarray([float(item["delta_b"]) for item in records], dtype=np.float64)
    return {
        "patch_count": len(records),
        "mean_ab_residual": float(np.mean(residuals)),
        "max_ab_residual": float(np.max(residuals)),
        "mean_delta_a": float(np.mean(delta_a_values)),
        "mean_delta_b": float(np.mean(delta_b_values)),
        "max_abs_delta_a": float(np.max(np.abs(delta_a_values))),
        "max_abs_delta_b": float(np.max(np.abs(delta_b_values))),
        "patches": records,
    }


def _coerce_lab(value: Any) -> np.ndarray | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return np.asarray([float(value[0]), float(value[1]), float(value[2])], dtype=np.float64)
    except (TypeError, ValueError):
        return None


def _rank_patch_errors(errors: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_errors = errors if isinstance(errors, list) else []
    for error in raw_errors:
        if hasattr(error, "__dataclass_fields__"):
            data = asdict(error)
        elif isinstance(error, dict):
            data = error
        else:
            continue

        patch_id = str(data.get("patch_id") or "").strip()
        if not patch_id:
            continue
        try:
            delta_e76 = float(data.get("delta_e76", 0.0))
            delta_e2000 = float(data.get("delta_e2000", 0.0))
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "patch_id": patch_id,
                "delta_e76": delta_e76,
                "delta_e2000": delta_e2000,
            }
        )
    return sorted(records, key=lambda item: item["delta_e2000"], reverse=True)


def _patch_error_outliers(records: list[dict[str, Any]], delta_e2000_limit: float) -> list[dict[str, Any]]:
    limit = float(delta_e2000_limit)
    return [record for record in records if float(record["delta_e2000"]) > limit]


def _capture_quality_summary(sample_sets: list[SampleSet]) -> dict[str, Any]:
    captures = [_single_capture_quality(samples) for samples in sample_sets]
    if not captures:
        return {
            "capture_count": 0,
            "captures": [],
            "min_brightest_neutral_luma": None,
            "min_median_luma": None,
            "max_neutral_density_spread_ev": None,
            "max_neutral_illumination_gradient_ev": None,
        }

    return {
        "capture_count": len(captures),
        "captures": captures,
        "min_brightest_neutral_luma": _min_optional(c.get("brightest_neutral_luma") for c in captures),
        "min_median_luma": _min_optional(c.get("median_luma") for c in captures),
        "max_neutral_density_spread_ev": _max_optional(c.get("neutral_density_spread_ev") for c in captures),
        "max_neutral_illumination_gradient_ev": _max_optional(
            c.get("neutral_illumination_gradient_ev") for c in captures
        ),
    }


def _single_capture_quality(samples: SampleSet) -> dict[str, Any]:
    patch_lumas = [
        {
            "patch_id": sample.patch_id,
            "luma": _sample_luma(sample),
            "reference_y": _reference_y(sample),
            "sample_center": sample.sample_center,
        }
        for sample in samples.samples
    ]
    lumas = np.asarray([p["luma"] for p in patch_lumas], dtype=np.float64)

    neutral = [p for p in patch_lumas if p["patch_id"] in NEUTRAL_PATCH_IDS and p["reference_y"] is not None]
    neutral_lumas = np.asarray([p["luma"] for p in neutral], dtype=np.float64)
    neutral_density = _neutral_density_residuals(neutral)

    return {
        "chart_name": samples.chart_name,
        "patch_count": len(samples.samples),
        "min_luma": float(np.min(lumas)) if lumas.size else 0.0,
        "median_luma": float(np.median(lumas)) if lumas.size else 0.0,
        "max_luma": float(np.max(lumas)) if lumas.size else 0.0,
        "brightest_neutral_luma": float(np.max(neutral_lumas)) if neutral_lumas.size else None,
        "darkest_neutral_luma": float(np.min(neutral_lumas)) if neutral_lumas.size else None,
        "neutral_density_spread_ev": _neutral_density_spread(neutral_density),
        "neutral_illumination_gradient_ev": _neutral_illumination_gradient(neutral_density),
        "neutral_density_residuals_ev": neutral_density,
    }


def _profile_sample_quality_rejection(samples: SampleSet) -> dict[str, Any] | None:
    failures: list[dict[str, Any]] = []
    for sample in samples.samples:
        patch_id = str(sample.patch_id)
        saturated = float(sample.saturated_pixel_ratio)
        is_neutral = patch_id in NEUTRAL_PATCH_IDS
        limit = (
            PROFILE_NEUTRAL_MAX_SATURATED_PIXEL_RATIO
            if is_neutral
            else PROFILE_PATCH_MAX_SATURATED_PIXEL_RATIO
        )
        if saturated <= limit:
            continue
        failures.append(
            {
                "reason": "neutral_patch_saturation" if is_neutral else "patch_saturation",
                "patch_id": patch_id,
                "saturated_pixel_ratio": saturated,
                "limit": float(limit),
                "excluded_pixel_ratio": float(sample.excluded_pixel_ratio),
                "sample_center": sample.sample_center,
                "severity": saturated / max(limit, 1e-6),
            }
        )

    if not failures:
        return None
    failures.sort(key=lambda item: float(item.get("severity") or 0.0), reverse=True)
    failure = dict(failures[0])
    failure.pop("severity", None)
    return failure


def _capture_quality_checks(label: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    bright = quality.get("min_brightest_neutral_luma")
    median_luma = quality.get("min_median_luma")
    low_signal_passed = (
        bright is not None
        and median_luma is not None
        and float(bright) >= LOW_SIGNAL_BRIGHT_NEUTRAL_MIN
        and float(median_luma) >= LOW_SIGNAL_MEDIAN_LUMA_MIN
    )
    checks.append(
        {
            "id": f"{label}_low_signal",
            "severity": "warning",
            "brightest_neutral_luma_min": bright,
            "brightest_neutral_luma_limit": LOW_SIGNAL_BRIGHT_NEUTRAL_MIN,
            "median_luma_min": median_luma,
            "median_luma_limit": LOW_SIGNAL_MEDIAN_LUMA_MIN,
            "passed": low_signal_passed,
        }
    )

    density_spread = quality.get("max_neutral_density_spread_ev")
    if density_spread is not None:
        checks.append(
            {
                "id": f"{label}_neutral_density_spread",
                "severity": "warning",
                "value": float(density_spread),
                "limit": NEUTRAL_DENSITY_SPREAD_EV_MAX,
                "passed": float(density_spread) <= NEUTRAL_DENSITY_SPREAD_EV_MAX,
            }
        )

    gradient = quality.get("max_neutral_illumination_gradient_ev")
    if gradient is not None:
        checks.append(
            {
                "id": f"{label}_neutral_illumination_gradient",
                "severity": "warning",
                "value": float(gradient),
                "limit": NEUTRAL_ILLUMINATION_GRADIENT_EV_MAX,
                "passed": float(gradient) <= NEUTRAL_ILLUMINATION_GRADIENT_EV_MAX,
                "message": "estimacion por fila neutra; no sustituye una medicion flat-field",
            }
        )
    return checks


def _sample_luma(sample: PatchSample) -> float:
    rgb = np.asarray(sample.measured_rgb, dtype=np.float64)
    if rgb.size != 3:
        return 0.0
    return float(np.dot(np.clip(rgb, 0.0, 1.0), LUMA_WEIGHTS))


def _reference_y(sample: PatchSample) -> float | None:
    if not sample.reference_lab or len(sample.reference_lab) < 1:
        return None
    try:
        lstar = float(sample.reference_lab[0])
    except (TypeError, ValueError):
        return None
    return _lstar_to_relative_y(lstar)


def _lstar_to_relative_y(lstar: float) -> float:
    fy = (float(lstar) + 16.0) / 116.0
    if fy > (6.0 / 29.0):
        return float(fy**3)
    return float(float(lstar) / 903.2962962962963)


def _neutral_density_residuals(neutral: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in neutral:
        ref_y = item.get("reference_y")
        if ref_y is None:
            continue
        measured_luma = max(float(item["luma"]), 1e-6)
        reference_y = max(float(ref_y), 1e-6)
        value = float(np.log2(measured_luma / reference_y))
        values.append(
            {
                "patch_id": str(item["patch_id"]),
                "measured_luma": measured_luma,
                "reference_y": reference_y,
                "density_ev": value,
                "sample_center": item.get("sample_center"),
            }
        )

    if not values:
        return []

    median_ev = float(np.median([item["density_ev"] for item in values]))
    for item in values:
        item["residual_ev"] = float(item["density_ev"] - median_ev)
    return values


def _neutral_density_spread(neutral_density: list[dict[str, Any]]) -> float | None:
    residuals = [float(item["residual_ev"]) for item in neutral_density if "residual_ev" in item]
    if len(residuals) < 3:
        return None
    return float(max(residuals) - min(residuals))


def _neutral_illumination_gradient(neutral_density: list[dict[str, Any]]) -> float | None:
    rows: list[list[float]] = []
    residuals: list[float] = []
    for item in neutral_density:
        center = item.get("sample_center")
        if not isinstance(center, list) or len(center) != 2:
            continue
        rows.append([float(center[0]), float(center[1]), 1.0])
        residuals.append(float(item["residual_ev"]))

    if len(rows) < 3:
        return None

    design = np.asarray(rows, dtype=np.float64)
    targets = np.asarray(residuals, dtype=np.float64)
    try:
        coeffs, *_ = np.linalg.lstsq(design, targets, rcond=None)
    except np.linalg.LinAlgError:
        return None
    predicted = design @ coeffs
    return float(np.max(predicted) - np.min(predicted))


def _min_optional(values: Any) -> float | None:
    numeric = [float(v) for v in values if v is not None]
    return min(numeric) if numeric else None


def _max_optional(values: Any) -> float | None:
    numeric = [float(v) for v in values if v is not None]
    return max(numeric) if numeric else None


def _sample_quality(samples: SampleSet) -> dict[str, Any]:
    saturated = np.asarray([s.saturated_pixel_ratio for s in samples.samples], dtype=np.float64)
    excluded = np.asarray([s.excluded_pixel_ratio for s in samples.samples], dtype=np.float64)
    lumas = np.asarray([_sample_luma(s) for s in samples.samples], dtype=np.float64)
    return {
        "patch_count": len(samples.samples),
        "max_saturated_pixel_ratio": float(np.max(saturated)) if saturated.size else 0.0,
        "median_saturated_pixel_ratio": float(np.median(saturated)) if saturated.size else 0.0,
        "max_excluded_pixel_ratio": float(np.max(excluded)) if excluded.size else 0.0,
        "median_excluded_pixel_ratio": float(np.median(excluded)) if excluded.size else 0.0,
        "min_patch_luma": float(np.min(lumas)) if lumas.size else 0.0,
        "median_patch_luma": float(np.median(lumas)) if lumas.size else 0.0,
        "max_patch_luma": float(np.max(lumas)) if lumas.size else 0.0,
    }


def _skipped_capture_summary(skipped: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not skipped:
        return ""
    parts: list[str] = []
    for item in skipped[: max(1, int(limit))]:
        if not isinstance(item, dict):
            continue
        capture = Path(str(item.get("capture") or "?")).name
        reason = str(item.get("reason") or "omitida")
        fields = [reason]
        if item.get("detection_mode"):
            fields.append(f"modo={item.get('detection_mode')}")
        if item.get("confidence") is not None:
            try:
                fields.append(f"confianza={float(item['confidence']):.3f}")
            except Exception:
                fields.append(f"confianza={item.get('confidence')}")
        if item.get("min_confidence") is not None:
            try:
                fields.append(f"min={float(item['min_confidence']):.3f}")
            except Exception:
                fields.append(f"min={item.get('min_confidence')}")
        if item.get("patch_id"):
            fields.append(f"parche={item.get('patch_id')}")
        if item.get("saturated_pixel_ratio") is not None:
            try:
                fields.append(f"saturacion={float(item['saturated_pixel_ratio']):.3f}")
            except Exception:
                fields.append(f"saturacion={item.get('saturated_pixel_ratio')}")
        if item.get("limit") is not None:
            try:
                fields.append(f"limite={float(item['limit']):.3f}")
            except Exception:
                fields.append(f"limite={item.get('limit')}")
        warnings = item.get("warnings") if isinstance(item.get("warnings"), list) else []
        if warnings:
            fields.append(f"aviso={str(warnings[0])}")
        elif item.get("error"):
            fields.append(f"error={item.get('error')}")
        parts.append(f"{capture}: " + ", ".join(fields))
    remaining = len(skipped) - len(parts)
    if remaining > 0:
        parts.append(f"+{remaining} capturas omitidas")
    return " | ".join(parts)


def _aggregate_samples(sample_sets: list[SampleSet], strategy: str) -> SampleSet:
    grouped: dict[str, list[PatchSample]] = defaultdict(list)
    for sset in sample_sets:
        for sample in sset.samples:
            grouped[sample.patch_id].append(sample)

    if not grouped:
        raise RuntimeError("No hay parches para agregar")

    aggregated_samples: list[PatchSample] = []
    for patch_id in sorted(grouped.keys(), key=_patch_sort_key):
        items = grouped[patch_id]
        measured = np.asarray([s.measured_rgb for s in items], dtype=np.float64)
        measured_med = np.median(measured, axis=0)

        excluded = float(np.median([s.excluded_pixel_ratio for s in items]))
        saturated = float(np.median([s.saturated_pixel_ratio for s in items]))

        ref_rgb = next((s.reference_rgb for s in items if s.reference_rgb is not None), None)
        ref_lab = next((s.reference_lab for s in items if s.reference_lab is not None), None)

        aggregated_samples.append(
            PatchSample(
                patch_id=patch_id,
                measured_rgb=[float(v) for v in measured_med.tolist()],
                reference_rgb=ref_rgb,
                reference_lab=ref_lab,
                excluded_pixel_ratio=excluded,
                saturated_pixel_ratio=saturated,
                sample_center=_median_sample_center(items),
            )
        )

    first = sample_sets[0]
    missing = [
        p.patch_id for p in aggregated_samples if p.reference_lab is None
    ]

    return SampleSet(
        chart_name=first.chart_name,
        chart_version=first.chart_version,
        illuminant=first.illuminant,
        strategy=f"aggregate_median({first.strategy or strategy})",
        samples=aggregated_samples,
        missing_reference_patches=missing,
    )


def _median_sample_center(samples: list[PatchSample]) -> list[float] | None:
    centers = [s.sample_center for s in samples if isinstance(s.sample_center, list) and len(s.sample_center) == 2]
    if not centers:
        return None
    values = np.asarray(centers, dtype=np.float64)
    return [float(v) for v in np.median(values, axis=0).tolist()]


def _collect_chart_samples(
    *,
    chart_files: list[Path],
    recipe: Recipe,
    reference: ReferenceCatalog,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    chart_dev_dir: Path,
    detect_dir: Path,
    sample_dir: Path,
    overlay_dir: Path,
    pass_name: str,
    existing_detections: dict[Path, Any] | None = None,
    existing_detection_note: str = "geometria de carta reutilizada desde pasada de perfil de revelado",
    cache_dir: Path | None = None,
    workers: int | None = None,
    artifacts: str = "full",
    progress_callback: Any | None = None,
    progress_start: int = 0,
    progress_end: int = 100,
    progress_phase: str = "Muestreando carta",
) -> dict[str, Any]:
    for d in (chart_dev_dir, detect_dir, sample_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    accepted_samples: list[SampleSet] = []
    skipped: list[dict[str, Any]] = []
    detections: dict[Path, Any] = {}
    artifact_mode = _normalize_profile_artifact_mode(artifacts)
    worker_count = _resolve_profile_workers(len(chart_files), workers=workers)
    jobs: list[tuple[Any, ...]] = []

    for idx, chart_file in enumerate(chart_files, start=1):
        prefix = f"{idx:03d}_{chart_file.stem}"
        developed_tiff = chart_dev_dir / f"{prefix}.tiff"
        detection_path = detect_dir / f"{prefix}.json"
        overlay_path = overlay_dir / f"{prefix}.png"
        sample_path = sample_dir / f"{prefix}.json"
        detection_key = chart_file.expanduser().resolve()
        existing_detection = existing_detections.get(detection_key) if existing_detections else None
        jobs.append(
            (
                idx,
                chart_file,
                recipe,
                reference,
                chart_type,
                min_confidence,
                allow_fallback_detection,
                pass_name,
                existing_detection,
                existing_detection_note,
                cache_dir,
                developed_tiff,
                detection_path,
                overlay_path,
                sample_path,
                artifact_mode,
            )
        )

    result_slots: list[dict[str, Any] | None] = [None] * len(jobs)
    completed_jobs = 0

    def store_result(result: dict[str, Any]) -> None:
        nonlocal completed_jobs
        result_index = int(result["index"])
        result_slots[result_index - 1] = result
        completed_jobs += 1
        capture_name = chart_files[result_index - 1].name if 0 < result_index <= len(chart_files) else ""
        detail = f"{completed_jobs}/{len(jobs)} capturas procesadas"
        if capture_name:
            detail = f"{detail}: {capture_name}"
        span = int(progress_end) - int(progress_start)
        progress = int(progress_start) + (span * completed_jobs / max(1, len(jobs)))
        _emit_workflow_progress(
            progress_callback,
            progress,
            progress_phase,
            detail,
            current=completed_jobs,
            total=len(jobs),
        )

    if worker_count <= 1:
        for job in jobs:
            result = _process_chart_sample_job(job)
            store_result(result)
    else:
        multiprocessing.freeze_support()
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_process_chart_sample_job, job) for job in jobs]
            for future in as_completed(futures):
                result = future.result()
                store_result(result)

    for result in result_slots:
        if result is None:
            continue
        if result.get("accepted_sample") is not None:
            accepted_samples.append(result["accepted_sample"])
        skipped.extend(result.get("skipped", []))
        detection = result.get("detection")
        detection_key = result.get("detection_key")
        if detection is not None and detection_key:
            detections[Path(str(detection_key))] = detection

    return {"accepted_samples": accepted_samples, "skipped": skipped, "detections": detections}


def _process_chart_sample_job(job: tuple[Any, ...]) -> dict[str, Any]:
    (
        idx,
        chart_file,
        recipe,
        reference,
        chart_type,
        min_confidence,
        allow_fallback_detection,
        pass_name,
        existing_detection,
        existing_detection_note,
        cache_dir,
        developed_tiff,
        detection_path,
        overlay_path,
        sample_path,
        artifact_mode,
    ) = job
    detection_key = Path(chart_file).expanduser().resolve()
    try:
        image = develop_image_array(Path(chart_file), recipe, cache_dir=cache_dir)
        if artifact_mode == "full":
            write_tiff16(Path(developed_tiff), image)
        detection = existing_detection
        if detection is None:
            detection = detect_chart_from_array(image, chart_type=chart_type)
        else:
            detection = _coerce_chart_detection(detection)
            detection.warnings = list(detection.warnings) + [
                existing_detection_note
            ]
        write_json(Path(detection_path), detection)
        if artifact_mode == "full":
            draw_detection_overlay_array(image, detection, Path(overlay_path))

        if detection.detection_mode == "fallback" and not allow_fallback_detection:
            return {
                "index": int(idx),
                "detection_key": str(detection_key),
                "detection": detection,
                "accepted_sample": None,
                "skipped": [
                    {
                        "pass": pass_name,
                        "capture": str(chart_file),
                        "reason": "fallback_detection",
                        "confidence": float(detection.confidence_score),
                        "detection_mode": str(detection.detection_mode),
                        "warnings": [str(w) for w in detection.warnings],
                        "detection_json": str(detection_path),
                    }
                ],
            }

        if detection.confidence_score < float(min_confidence):
            return {
                "index": int(idx),
                "detection_key": str(detection_key),
                "detection": detection,
                "accepted_sample": None,
                "skipped": [
                    {
                        "pass": pass_name,
                        "capture": str(chart_file),
                        "reason": "low_confidence",
                        "confidence": float(detection.confidence_score),
                        "min_confidence": float(min_confidence),
                        "detection_mode": str(detection.detection_mode),
                        "warnings": [str(w) for w in detection.warnings],
                        "detection_json": str(detection_path),
                    }
                ],
            }

        samples = sample_chart_from_array(
            image,
            detection,
            reference,
            strategy=recipe.sampling_strategy,
            trim_percent=recipe.sampling_trim_percent,
            reject_saturated=recipe.sampling_reject_saturated,
        )
        write_json(Path(sample_path), samples)
        quality_rejection = _profile_sample_quality_rejection(samples)
        if quality_rejection is not None:
            return {
                "index": int(idx),
                "detection_key": str(detection_key),
                "detection": detection,
                "accepted_sample": None,
                "skipped": [
                    {
                        "pass": pass_name,
                        "capture": str(chart_file),
                        **quality_rejection,
                        "confidence": float(detection.confidence_score),
                        "detection_mode": str(detection.detection_mode),
                        "warnings": [str(w) for w in detection.warnings],
                        "detection_json": str(detection_path),
                        "sample_json": str(sample_path),
                    }
                ],
            }
        return {
            "index": int(idx),
            "detection_key": str(detection_key),
            "detection": detection,
            "accepted_sample": samples,
            "skipped": [],
        }
    except Exception as exc:
        return {
            "index": int(idx),
            "detection_key": str(detection_key),
            "detection": None,
            "accepted_sample": None,
            "skipped": [
                {
                    "pass": pass_name,
                    "capture": str(chart_file),
                    "reason": "processing_error",
                    "error": str(exc),
                }
            ],
        }


def _normalize_profile_artifact_mode(value: str) -> str:
    mode = str(value or "full").strip().lower()
    if mode in {"minimal", "min", "fast"}:
        return "minimal"
    return "full"


def _resolve_profile_workers(total_items: int, *, workers: int | None = None) -> int:
    total = max(1, int(total_items))
    if workers is not None:
        configured = int(workers)
        if configured > 0:
            return max(1, min(total, configured))
        return _auto_profile_worker_count(total)
    raw = os.environ.get("PROBRAW_PROFILE_WORKERS", "").strip()
    if raw:
        if raw.lower() in {"auto", "max", "all"}:
            return _auto_profile_worker_count(total)
        try:
            configured = int(raw)
        except ValueError:
            return _auto_profile_worker_count(total)
        if configured > 0:
            return max(1, min(total, configured))
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 1
    return _auto_profile_worker_count(total)


def _auto_profile_worker_count(total_items: int) -> int:
    cpus = max(1, int(os.cpu_count() or 1))
    return max(1, min(int(total_items), max(1, cpus // 2)))


def _validation_detection_map(
    *,
    validation_files: list[Path],
    manual_detection_map: dict[Path, Any] | None,
    recipe: Recipe,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    work_dir: Path,
    cache_dir: Path | None = None,
) -> dict[Path, Any] | None:
    detection_map: dict[Path, Any] = {}
    if manual_detection_map:
        detection_map.update(manual_detection_map)

    missing = [
        p for p in validation_files
        if p.expanduser().resolve() not in detection_map
    ]
    if not missing:
        return detection_map or None

    geometry = _collect_chart_geometries(
        chart_files=missing,
        recipe=recipe,
        chart_type=chart_type,
        min_confidence=min_confidence,
        allow_fallback_detection=allow_fallback_detection,
        chart_dev_dir=work_dir / "chart_developed_validation_geometry",
        detect_dir=work_dir / "detections_validation_geometry",
        overlay_dir=work_dir / "overlays_validation_geometry",
        cache_dir=cache_dir,
    )
    detection_map.update(geometry["detections"])
    return detection_map or None


def _collect_chart_geometries(
    *,
    chart_files: list[Path],
    recipe: Recipe,
    chart_type: str,
    min_confidence: float,
    allow_fallback_detection: bool,
    chart_dev_dir: Path,
    detect_dir: Path,
    overlay_dir: Path,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    for d in (chart_dev_dir, detect_dir, overlay_dir):
        d.mkdir(parents=True, exist_ok=True)

    detections: dict[Path, Any] = {}
    skipped: list[dict[str, Any]] = []

    for idx, chart_file in enumerate(chart_files, start=1):
        prefix = f"{idx:03d}_{chart_file.stem}"
        developed_tiff = chart_dev_dir / f"{prefix}.tiff"
        detection_path = detect_dir / f"{prefix}.json"
        overlay_path = overlay_dir / f"{prefix}.png"
        detection_key = chart_file.expanduser().resolve()

        try:
            image = develop_image_array(chart_file, recipe, cache_dir=cache_dir)
            write_tiff16(developed_tiff, image)
            detection = detect_chart_from_array(image, chart_type=chart_type)
            write_json(detection_path, detection)
            draw_detection_overlay_array(image, detection, overlay_path)

            if detection.detection_mode == "fallback" and not allow_fallback_detection:
                skipped.append(
                    {
                        "pass": "validation_geometry_source",
                        "capture": str(chart_file),
                        "reason": "fallback_detection",
                        "confidence": float(detection.confidence_score),
                        "detection_mode": str(detection.detection_mode),
                        "warnings": [str(w) for w in detection.warnings],
                        "detection_json": str(detection_path),
                    }
                )
                continue

            if detection.confidence_score < float(min_confidence):
                skipped.append(
                    {
                        "pass": "validation_geometry_source",
                        "capture": str(chart_file),
                        "reason": "low_confidence",
                        "confidence": float(detection.confidence_score),
                        "min_confidence": float(min_confidence),
                        "detection_mode": str(detection.detection_mode),
                        "warnings": [str(w) for w in detection.warnings],
                        "detection_json": str(detection_path),
                    }
                )
                continue

            detections[detection_key] = detection
        except Exception as exc:
            skipped.append(
                {
                    "pass": "validation_geometry_source",
                    "capture": str(chart_file),
                    "reason": "processing_error",
                    "error": str(exc),
                }
            )

    return {"detections": detections, "skipped": skipped}


def _patch_sort_key(patch_id: str) -> tuple[int, str]:
    digits = "".join(ch for ch in patch_id if ch.isdigit())
    if digits:
        return int(digits), patch_id
    return 10_000, patch_id


def _list_chart_capture_files(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        raise RuntimeError(f"Directorio inválido: {folder}")

    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
    ]
    files.sort()
    return files


def _normalize_chart_capture_files(files: list[Path]) -> list[Path]:
    supported = PROFILE_CHART_EXTENSIONS
    normalized: list[Path] = []
    invalid: list[str] = []

    for item in files:
        p = Path(item).expanduser()
        if not p.exists() or not p.is_file() or p.suffix.lower() not in supported:
            invalid.append(str(p))
            continue
        normalized.append(p)

    if invalid:
        preview = ", ".join(invalid[:5])
        suffix = "" if len(invalid) <= 5 else f" (+{len(invalid) - 5} más)"
        raise RuntimeError(
            "Capturas de carta invalidas o incompatibles para perfilado cientifico "
            f"(solo RAW/DNG originales): {preview}{suffix}"
        )

    return sorted(set(normalized), key=lambda p: str(p))


def _normalize_detection_map(detections: dict[Path, Any] | None) -> dict[Path, Any] | None:
    if not detections:
        return None
    return {Path(path).expanduser().resolve(): detection for path, detection in detections.items()}


def _coerce_chart_detection(value: Any) -> ChartDetectionResult:
    if isinstance(value, ChartDetectionResult):
        return value
    if not isinstance(value, dict):
        raise RuntimeError("Deteccion de carta manual no compatible")

    return ChartDetectionResult(
        chart_type=str(value["chart_type"]),
        confidence_score=float(value["confidence_score"]),
        valid_patch_ratio=float(value["valid_patch_ratio"]),
        homography=[float(v) for v in value["homography"]],
        chart_polygon=[_coerce_point(p) for p in value["chart_polygon"]],
        patches=[
            PatchDetection(
                patch_id=str(patch["patch_id"]),
                polygon=[_coerce_point(p) for p in patch["polygon"]],
                sample_region=[_coerce_point(p) for p in patch["sample_region"]],
            )
            for patch in value["patches"]
        ],
        warnings=[str(w) for w in value.get("warnings", [])],
        detection_mode=str(value.get("detection_mode", "manual")),
    )


def _coerce_point(value: Any) -> Point2:
    if isinstance(value, Point2):
        return value
    if isinstance(value, dict):
        return Point2(x=float(value["x"]), y=float(value["y"]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return Point2(x=float(value[0]), y=float(value[1]))
    raise RuntimeError("Punto de deteccion de carta no compatible")
