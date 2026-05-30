from __future__ import annotations

import pytest

from probraw.core.models import PatchSample, Recipe, SampleSet
from probraw.profile.development import build_development_profile


def test_build_development_profile_balances_neutral_row_and_exposure():
    samples = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="unit",
        illuminant="D50",
        strategy="unit",
        samples=[
            _neutral("P19", [0.30, 0.60, 0.20], 96.0),
            _neutral("P20", [0.20, 0.40, 0.133], 81.0),
            _neutral("P21", [0.14, 0.28, 0.093], 67.0),
            _neutral("P22", [0.09, 0.18, 0.060], 51.0),
            _neutral("P23", [0.045, 0.09, 0.030], 36.0),
            _neutral("P24", [0.020, 0.040, 0.013], 20.0),
        ],
        missing_reference_patches=[],
    )

    profile = build_development_profile(samples, Recipe())

    assert profile.model == "neutral_row_wb_density_v1"
    assert profile.calibrated_recipe.white_balance_mode == "fixed"
    assert profile.white_balance_multipliers[0] > 1.0
    assert profile.white_balance_multipliers[2] > profile.white_balance_multipliers[0]
    assert profile.calibrated_recipe.tone_curve == "linear"
    assert profile.calibrated_recipe.output_linear is True
    assert len(profile.neutral_patches) == 6


def test_build_development_profile_ignores_saturated_neutral_for_calibration():
    samples = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="unit",
        illuminant="D50",
        strategy="unit",
        samples=[
            _neutral("P19", [0.03, 0.03, 0.03], 96.0, saturated=0.85),
            _neutral("P20", [0.60, 0.60, 0.60], 81.0),
            _neutral("P21", [0.36, 0.36, 0.36], 67.0),
            _neutral("P22", [0.19, 0.19, 0.19], 51.0),
            _neutral("P23", [0.09, 0.09, 0.09], 36.0),
            _neutral("P24", [0.03, 0.03, 0.03], 20.0),
        ],
        missing_reference_patches=[],
    )

    profile = build_development_profile(samples, Recipe())

    assert "P19" not in profile.neutral_patch_ids
    assert all(p.patch_id != "P19" for p in profile.neutral_patches)
    assert any("P19" in warning for warning in profile.warnings)
    assert profile.density_error_ev_max_abs < 1.0


def test_build_development_profile_requires_neutral_references():
    samples = SampleSet(
        chart_name="ColorChecker 24",
        chart_version="unit",
        illuminant="D50",
        strategy="unit",
        samples=[_neutral("P19", [0.2, 0.2, 0.2], 96.0)],
        missing_reference_patches=[],
    )

    with pytest.raises(RuntimeError, match="al menos 3 parches neutros"):
        build_development_profile(samples, Recipe())


def _neutral(patch_id: str, rgb: list[float], l_value: float, *, saturated: float = 0.0) -> PatchSample:
    return PatchSample(
        patch_id=patch_id,
        measured_rgb=rgb,
        reference_rgb=None,
        reference_lab=[l_value, 0.0, 0.0],
        excluded_pixel_ratio=0.0,
        saturated_pixel_ratio=saturated,
    )
