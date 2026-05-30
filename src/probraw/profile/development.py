from __future__ import annotations

from dataclasses import replace
import math

import numpy as np

from ..core.models import DevelopmentProfile, NeutralPatchCalibration, Recipe, SampleSet


DEFAULT_NEUTRAL_PATCH_IDS = ("P19", "P20", "P21", "P22", "P23", "P24")


def build_development_profile(
    samples: SampleSet,
    base_recipe: Recipe,
    *,
    neutral_patch_ids: tuple[str, ...] = DEFAULT_NEUTRAL_PATCH_IDS,
    max_abs_ev: float = 4.0,
    highlight_headroom: float = 0.92,
    max_neutral_saturated_pixel_ratio: float = 0.02,
) -> DevelopmentProfile:
    sample_map = {sample.patch_id: sample for sample in samples.samples}
    neutral = [
        sample_map[patch_id]
        for patch_id in neutral_patch_ids
        if patch_id in sample_map and sample_map[patch_id].reference_lab is not None
    ]
    if len(neutral) < 3:
        raise RuntimeError("Se necesitan al menos 3 parches neutros con referencia Lab para calibrar revelado")

    saturated_neutral = [
        sample
        for sample in neutral
        if float(sample.saturated_pixel_ratio) > float(max_neutral_saturated_pixel_ratio)
    ]
    calibration_neutral = [
        sample
        for sample in neutral
        if float(sample.saturated_pixel_ratio) <= float(max_neutral_saturated_pixel_ratio)
    ]
    if len(calibration_neutral) < 3:
        raise RuntimeError(
            "Los parches neutros validos estan saturados; repite la captura con menos exposicion"
        )

    measured = np.asarray([sample.measured_rgb for sample in calibration_neutral], dtype=np.float64)
    reference_lab = np.asarray([sample.reference_lab for sample in calibration_neutral], dtype=np.float64)
    reference_y = np.asarray([_lab_l_to_y(lab[0]) for lab in reference_lab], dtype=np.float64)

    valid_signal = np.all(np.isfinite(measured), axis=1) & (np.max(measured, axis=1) > 1e-5)
    valid_density = valid_signal & (reference_y > 0.03)
    if np.count_nonzero(valid_density) < 3:
        raise RuntimeError("Los parches neutros no tienen señal suficiente para calibrar densidad")

    # Use mid/high neutral patches for chromatic neutrality; the black patch is
    # often too noisy for a stable white-balance estimate.
    balance_mask = valid_signal & (reference_lab[:, 0] >= 35.0)
    if np.count_nonzero(balance_mask) < 3:
        balance_mask = valid_density

    channel_medians = np.median(measured[balance_mask], axis=0)
    if np.any(channel_medians <= 1e-6):
        raise RuntimeError("No se puede estimar balance de blancos: canal neutro sin señal")

    gray_reference = float(np.mean(channel_medians))
    relative_gains = gray_reference / channel_medians

    base_wb = _recipe_wb3(base_recipe)
    calibrated_wb3 = base_wb * relative_gains
    calibrated_wb3 = calibrated_wb3 / max(calibrated_wb3[1], 1e-6)
    effective_gains = calibrated_wb3 / np.clip(base_wb, 1e-6, None)
    wb_multipliers = [
        float(calibrated_wb3[0]),
        float(calibrated_wb3[1]),
        float(calibrated_wb3[2]),
        float(calibrated_wb3[1]),
    ]

    balanced = measured * effective_gains[None, :]
    measured_luma = np.mean(balanced, axis=1)
    ev_values = np.log2(np.clip(reference_y[valid_density], 1e-6, None) / np.clip(measured_luma[valid_density], 1e-6, None))
    ev_correction = float(np.median(ev_values))
    ev_correction = float(np.clip(ev_correction, -abs(max_abs_ev), abs(max_abs_ev)))

    neutral_reports: list[NeutralPatchCalibration] = []
    density_errors: list[float] = []
    for sample, lab, ref_y, balanced_rgb, luma in zip(
        calibration_neutral,
        reference_lab,
        reference_y,
        balanced,
        measured_luma,
        strict=True,
    ):
        ev = float(math.log2(max(ref_y, 1e-6) / max(float(luma), 1e-6)))
        density_error = float(math.log10(max(float(luma), 1e-6) / max(float(ref_y), 1e-6)))
        density_errors.append(ev)
        neutral_reports.append(
            NeutralPatchCalibration(
                patch_id=sample.patch_id,
                measured_rgb=[float(v) for v in sample.measured_rgb],
                balanced_rgb=[float(v) for v in balanced_rgb.tolist()],
                reference_lab=[float(v) for v in lab.tolist()],
                reference_y=float(ref_y),
                measured_luma=float(luma),
                ev_correction=ev,
                density_error_log10=density_error,
            )
        )

    warnings: list[str] = []
    if saturated_neutral:
        warnings.append(
            "parches neutros saturados excluidos de la calibracion: "
            + ", ".join(sample.patch_id for sample in saturated_neutral)
        )
    if abs(ev_correction) >= abs(max_abs_ev):
        warnings.append(f"correccion EV limitada a +/-{max_abs_ev}; revisar exposicion de captura")

    all_measured = np.asarray([sample.measured_rgb for sample in samples.samples], dtype=np.float64)
    all_balanced = all_measured * effective_gains[None, :]
    max_balanced = float(np.nanmax(all_balanced)) if all_balanced.size else 0.0
    if max_balanced > 1e-6:
        max_ev_without_clipping = float(math.log2(float(highlight_headroom) / max_balanced))
        if ev_correction > max_ev_without_clipping:
            warnings.append(
                "correccion EV limitada por preservacion de altas luces de carta: "
                f"{ev_correction:.3f} -> {max_ev_without_clipping:.3f}"
            )
            ev_correction = max_ev_without_clipping

    calibrated_exposure = float(base_recipe.exposure_compensation + ev_correction)

    if np.max([sample.saturated_pixel_ratio for sample in neutral]) > 0.001:
        warnings.append("hay saturacion en parches neutros; la calibracion densitometrica puede degradarse")
    if base_recipe.white_balance_mode.strip().lower() != "fixed":
        warnings.append("la receta base no usaba WB fijo; el perfil de revelado fija multiplicadores reproducibles")

    calibrated_recipe = replace(
        base_recipe,
        white_balance_mode="fixed",
        wb_multipliers=wb_multipliers,
        exposure_compensation=calibrated_exposure,
        tone_curve="linear",
        output_linear=True,
        denoise="off" if base_recipe.profiling_mode else base_recipe.denoise,
        sharpen="off" if base_recipe.profiling_mode else base_recipe.sharpen,
    )

    density_arr = np.asarray(density_errors, dtype=np.float64)
    return DevelopmentProfile(
        model="neutral_row_wb_density_v1",
        chart_name=samples.chart_name,
        chart_version=samples.chart_version,
        illuminant=samples.illuminant,
        neutral_patch_ids=[sample.patch_id for sample in calibration_neutral],
        white_balance_multipliers=wb_multipliers,
        exposure_compensation=calibrated_exposure,
        density_error_ev_mean=float(np.mean(density_arr)),
        density_error_ev_max_abs=float(np.max(np.abs(density_arr))),
        warnings=warnings,
        calibrated_recipe=calibrated_recipe,
        neutral_patches=neutral_reports,
    )


def _recipe_wb3(recipe: Recipe) -> np.ndarray:
    values = [float(v) for v in (recipe.wb_multipliers or [1.0, 1.0, 1.0, 1.0])]
    if len(values) >= 3:
        return np.asarray([values[0], values[1], values[2]], dtype=np.float64)
    return np.ones(3, dtype=np.float64)


def _lab_l_to_y(l_value: float) -> float:
    l_value = float(l_value)
    if l_value > 8.0:
        return ((l_value + 16.0) / 116.0) ** 3.0
    return l_value / 903.3
