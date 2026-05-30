from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from probraw.core.color import delta_e76, delta_e2000
from probraw.core.models import PatchSample, SampleSet
from probraw.profile import builder


def _sample_set(samples: list[PatchSample]) -> SampleSet:
    return SampleSet(
        chart_name="test-chart",
        chart_version="v1",
        illuminant="D50",
        strategy="mean",
        samples=samples,
        missing_reference_patches=[],
    )


def test_delta_e_calculations_match_canonical_values():
    lab_a = np.asarray([[50.0, 2.6772, -79.7751], [0.0, 0.0, 0.0]], dtype=np.float64)
    lab_b = np.asarray([[50.0, 0.0, -82.7485], [3.0, 4.0, 12.0]], dtype=np.float64)

    assert float(delta_e2000(lab_a[:1], lab_b[:1])[0]) == pytest.approx(2.0425, abs=5e-4)
    assert float(delta_e76(lab_a[1:], lab_b[1:])[0]) == pytest.approx(13.0)


def test_samples_to_arrays_uses_lab_d50_and_preserves_patch_order():
    samples = _sample_set(
        [
            PatchSample(
                patch_id="P02",
                measured_rgb=[0.25, 0.5, 0.75],
                reference_rgb=None,
                reference_lab=[100.0, 0.0, 0.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            ),
            PatchSample(
                patch_id="P01",
                measured_rgb=[0.0, 0.0, 0.0],
                reference_rgb=None,
                reference_lab=[0.0, 0.0, 0.0],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            ),
        ]
    )

    measured_rgb, reference_xyz, reference_lab, patch_ids = builder._samples_to_arrays(samples)

    assert patch_ids == ["P02", "P01"]
    assert measured_rgb.tolist() == [[0.25, 0.5, 0.75], [0.0, 0.0, 0.0]]
    assert reference_lab.tolist() == [[100.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    assert reference_xyz[0] == pytest.approx(builder.D50_XYZ, abs=1e-10)
    assert reference_xyz[1] == pytest.approx([0.0, 0.0, 0.0], abs=1e-10)


def test_write_samples_cgats_uses_input_device_xyz_rgb_and_rgb_percent_scale(tmp_path: Path):
    samples = _sample_set(
        [
            PatchSample(
                patch_id="P01",
                measured_rgb=[0.1, 0.2, 0.3],
                reference_rgb=None,
                reference_lab=[50.1234567, -1.2, 3.4],
                excluded_pixel_ratio=0.0,
                saturated_pixel_ratio=0.0,
            )
        ]
    )
    output = tmp_path / "samples.ti3"

    builder.write_samples_cgats(samples, output)

    text = output.read_text(encoding="ascii")
    assert 'DEVICE_CLASS "INPUT"' in text
    assert 'COLOR_REP "XYZ_RGB"' in text
    assert "SAMPLE_ID XYZ_X XYZ_Y XYZ_Z RGB_R RGB_G RGB_B" in text
    assert "P01 17.636231 18.522205 13.955796 10.000000 20.000000 30.000000" in text
