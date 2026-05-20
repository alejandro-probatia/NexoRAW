from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def to_json_dict(obj: Any) -> dict[str, Any]:
    return _normalize(asdict(obj))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "__dataclass_fields__"):
        data = to_json_dict(payload)
    else:
        data = _normalize(payload)
    path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class RawMetadata:
    source_file: str
    input_sha256: str
    camera_model: str | None
    cfa_pattern: str
    available_white_balance: str
    wb_multipliers: list[float] | None
    black_level: int | None
    white_level: int | None
    color_matrix_hint: list[list[float]] | None
    iso: int | None
    exposure_time_seconds: float | None
    lens_model: str | None
    capture_datetime: str | None
    dimensions: list[int] | None
    intermediate_working_space: str
    black_level_per_channel: list[int] | None = None
    embedded_profile_description: str | None = None
    embedded_profile_source: str | None = None


@dataclass
class Recipe:
    raw_developer: str = "libraw"
    demosaic_algorithm: str = "dcb"
    demosaic_edge_quality: int = 0
    false_color_suppression_steps: int = 0
    four_color_rgb: bool = False
    libraw_auto_bright: bool = False
    libraw_auto_bright_thr: float = 0.01
    libraw_adjust_maximum_thr: float = 0.75
    libraw_bright: float = 1.0
    libraw_highlight_mode: str = "clip"
    libraw_exp_shift: float = 1.0
    libraw_exp_preserve_highlights: float = 0.0
    libraw_no_auto_scale: bool = False
    libraw_gamma_power: float = 1.0
    libraw_gamma_slope: float = 1.0
    libraw_chromatic_aberration_red: float = 1.0
    libraw_chromatic_aberration_blue: float = 1.0
    black_level_mode: str = "metadata"
    white_balance_mode: str = "fixed"
    wb_multipliers: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    exposure_compensation: float = 0.0
    tone_curve: str = "linear"
    output_linear: bool = True
    denoise: str = "off"
    sharpen: str = "off"
    input_color_assumption: str = "camera_native"
    working_space: str = "scene_linear_camera_rgb"
    output_space: str = "scene_linear_camera_rgb"
    chart_reference: str | None = None
    illuminant_metadata: str | None = None
    sampling_strategy: str = "trimmed_mean"
    sampling_trim_percent: float = 0.1
    sampling_reject_saturated: bool = True
    profiling_mode: bool = True
    profile_engine: str = "argyll"
    argyll_colprof_args: list[str] | None = None
    use_cache: bool = False


@dataclass
class ScientificGuard:
    is_scientific_safe: bool
    warnings: list[str]


@dataclass
class DevelopResult:
    raw_metadata: RawMetadata
    recipe: Recipe
    scientific_guard: ScientificGuard
    output_tiff: str
    audit_tiff: str | None


@dataclass
class Point2:
    x: float
    y: float


@dataclass
class PatchDetection:
    patch_id: str
    polygon: list[Point2]
    sample_region: list[Point2]


@dataclass
class ChartDetectionResult:
    chart_type: str
    confidence_score: float
    valid_patch_ratio: float
    homography: list[float]
    chart_polygon: list[Point2]
    patches: list[PatchDetection]
    warnings: list[str]
    detection_mode: str = "automatic"


@dataclass
class PatchSample:
    patch_id: str
    measured_rgb: list[float]
    reference_rgb: list[float] | None
    reference_lab: list[float] | None
    excluded_pixel_ratio: float
    saturated_pixel_ratio: float
    sample_center: list[float] | None = None
    sampling_parameters: dict[str, Any] | None = None


@dataclass
class SampleSet:
    chart_name: str
    chart_version: str
    illuminant: str
    strategy: str
    samples: list[PatchSample]
    missing_reference_patches: list[str]


@dataclass
class NeutralPatchCalibration:
    patch_id: str
    measured_rgb: list[float]
    balanced_rgb: list[float]
    reference_lab: list[float]
    reference_y: float
    measured_luma: float
    ev_correction: float
    density_error_log10: float


@dataclass
class DevelopmentProfile:
    model: str
    chart_name: str
    chart_version: str
    illuminant: str
    neutral_patch_ids: list[str]
    white_balance_multipliers: list[float]
    exposure_compensation: float
    density_error_ev_mean: float
    density_error_ev_max_abs: float
    warnings: list[str]
    calibrated_recipe: Recipe
    neutral_patches: list[NeutralPatchCalibration]


@dataclass
class PatchError:
    patch_id: str
    delta_e76: float
    delta_e2000: float
    reference_lab: list[float] | None = None
    profile_lab: list[float] | None = None


@dataclass
class ErrorSummary:
    mean_delta_e76: float
    median_delta_e76: float
    p95_delta_e76: float
    max_delta_e76: float
    mean_delta_e2000: float
    median_delta_e2000: float
    p95_delta_e2000: float
    max_delta_e2000: float


@dataclass
class ProfileBuildResult:
    output_icc: str
    output_profile_json: str
    model: str
    matrix_camera_to_xyz: list[list[float]]
    trc_gamma: float
    error_summary: ErrorSummary
    patch_errors: list[PatchError]
    metadata: dict[str, Any]


@dataclass
class ValidationResult:
    profile_path: str
    error_summary: ErrorSummary
    patch_errors: list[PatchError]


@dataclass
class BatchManifestEntry:
    source_raw: str
    source_sha256: str
    output_tiff: str
    output_sha256: str
    profile_path: str
    color_management_mode: str
    output_color_space: str
    linear_audit_tiff: str | None = None
    proof_path: str | None = None
    proof_sha256: str | None = None
    c2pa_embedded: bool = False


@dataclass
class BatchManifest:
    recipe_sha256: str
    profile_path: str
    color_management_mode: str
    output_color_space: str
    software_version: str
    entries: list[BatchManifestEntry]
