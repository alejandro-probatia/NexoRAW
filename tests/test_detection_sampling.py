from pathlib import Path

import numpy as np
import pytest
import tifffile

from probraw.chart.detection import PATCH_SAMPLE_REGION_SCALE, detect_chart, detect_chart_from_corners
from probraw.chart.sampling import ReferenceCatalog, _sample_patch, bundled_reference_catalogs, reference_catalog_template, sample_chart
from probraw.core.models import ChartDetectionResult, PatchDetection, Point2


def test_detect_chart_marks_fallback_as_low_confidence(tmp_path: Path):
    path = tmp_path / "blank.tiff"
    image = np.full((120, 180, 3), 20000, dtype=np.uint16)
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = detect_chart(path, chart_type="colorchecker24")

    assert detection.detection_mode == "fallback"
    assert detection.confidence_score <= 0.05
    assert detection.valid_patch_ratio == 0.0
    assert any("fallback" in warning for warning in detection.warnings)


def test_detect_chart_finds_colorchecker_patch_grid(tmp_path: Path):
    path = tmp_path / "floating_grid.tiff"
    image = np.full((520, 760, 3), 1200, dtype=np.uint16)

    colors = [
        [18000, 12000, 9000],
        [34000, 26000, 19000],
        [12000, 19000, 30000],
        [10000, 22000, 11000],
        [26000, 15000, 30000],
        [9000, 26000, 25000],
        [32000, 32000, 32000],
        [15000, 15000, 15000],
        [31000, 9000, 9000],
        [9000, 11000, 30000],
        [30000, 26000, 9000],
        [9000, 22000, 18000],
        [11000, 9000, 25000],
        [10000, 25000, 12000],
        [25000, 9000, 9000],
        [33000, 33000, 12000],
        [25000, 12000, 28000],
        [9000, 26000, 30000],
        [52000, 52000, 52000],
        [41000, 41000, 41000],
        [30000, 30000, 30000],
        [21000, 21000, 21000],
        [12000, 12000, 12000],
        [5000, 5000, 5000],
    ]

    idx = 0
    for row in range(4):
        for col in range(6):
            x = 190 + col * 76 + row * 4
            y = 120 + row * 70 + col * 2
            image[y : y + 52, x : x + 52] = colors[idx]
            idx += 1

    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = detect_chart(path, chart_type="colorchecker24")

    assert detection.detection_mode == "automatic"
    assert detection.confidence_score >= 0.35
    assert detection.valid_patch_ratio >= 0.9
    assert len(detection.patches) == 24


def test_detect_chart_from_manual_corners_builds_geometry(tmp_path: Path):
    path = tmp_path / "manual.tiff"
    image = np.full((120, 180, 3), 20000, dtype=np.uint16)
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = detect_chart_from_corners(
        path,
        corners=[(20, 20), (160, 24), (150, 100), (25, 105)],
        chart_type="colorchecker24",
    )

    assert detection.detection_mode == "manual"
    assert detection.confidence_score == 1.0
    assert detection.valid_patch_ratio == 1.0
    assert len(detection.patches) == 24
    assert any("manual" in warning for warning in detection.warnings)


def test_chart_sample_regions_are_centered_and_smaller_than_patch_cells(tmp_path: Path):
    path = tmp_path / "manual_sample_size.tiff"
    image = np.full((120, 180, 3), 20000, dtype=np.uint16)
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = detect_chart_from_corners(
        path,
        corners=[(30, 20), (150, 20), (150, 100), (30, 100)],
        chart_type="colorchecker24",
    )
    patch = detection.patches[0]
    patch_poly = np.asarray([[point.x, point.y] for point in patch.polygon], dtype=np.float64)
    sample_poly = np.asarray([[point.x, point.y] for point in patch.sample_region], dtype=np.float64)

    patch_width = float(np.linalg.norm(patch_poly[1] - patch_poly[0]))
    sample_width = float(np.linalg.norm(sample_poly[1] - sample_poly[0]))
    patch_height = float(np.linalg.norm(patch_poly[3] - patch_poly[0]))
    sample_height = float(np.linalg.norm(sample_poly[3] - sample_poly[0]))

    assert sample_width / patch_width == pytest.approx(PATCH_SAMPLE_REGION_SCALE, abs=0.02)
    assert sample_height / patch_height == pytest.approx(PATCH_SAMPLE_REGION_SCALE, abs=0.02)
    assert np.allclose(sample_poly.mean(axis=0), patch_poly.mean(axis=0), atol=1e-6)


def test_sample_chart_honors_trim_percent_and_saturation_rejection(tmp_path: Path):
    path = tmp_path / "patch.tiff"
    image = np.zeros((10, 10, 3), dtype=np.uint16)
    image[:] = [10000, 10000, 10000]
    image[0, 1] = [50000, 50000, 50000]
    image[0, 0] = [65535, 65535, 65535]
    tifffile.imwrite(str(path), image, photometric="rgb", metadata=None)

    detection = ChartDetectionResult(
        chart_type="unit",
        confidence_score=1.0,
        valid_patch_ratio=1.0,
        homography=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        chart_polygon=[],
        patches=[
            PatchDetection(
                patch_id="P01",
                polygon=[],
                sample_region=[
                    Point2(0, 0),
                    Point2(9, 0),
                    Point2(9, 9),
                    Point2(0, 9),
                ],
            )
        ],
        warnings=[],
    )
    reference = ReferenceCatalog(
        {
            "chart_name": "unit",
            "chart_version": "1",
            "illuminant": "D50",
            "patches": [{"patch_id": "P01", "reference_lab": [50, 0, 0]}],
        }
    )

    untrimmed = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.0,
        reject_saturated=True,
    )
    trimmed = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.25,
        reject_saturated=True,
    )
    saturated_kept = sample_chart(
        path,
        detection,
        reference,
        strategy="trimmed_mean",
        trim_percent=0.0,
        reject_saturated=False,
    )

    assert trimmed.samples[0].measured_rgb[0] < untrimmed.samples[0].measured_rgb[0]
    assert saturated_kept.samples[0].measured_rgb[0] > untrimmed.samples[0].measured_rgb[0]
    assert trimmed.samples[0].sample_center == [4.5, 4.5]
    assert trimmed.samples[0].sampling_parameters == {
        "strategy": "trimmed_mean",
        "trim_percent": 0.25,
        "reject_saturated": True,
    }
    assert "trim_percent=0.25" in trimmed.strategy
    assert "reject_saturated=true" in trimmed.strategy


def test_sample_patch_uses_same_pixels_as_full_frame_mask():
    image = np.arange(40 * 50 * 3, dtype=np.float32).reshape(40, 50, 3) / 10000.0
    polygon = np.array([[13.2, 7.7], [34.6, 9.1], [31.4, 24.8], [11.9, 22.2]], dtype=np.float32)

    measured, excluded, saturated = _sample_patch(
        image,
        polygon,
        "trimmed_mean",
        trim_percent=0.1,
        reject_saturated=True,
    )

    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    import cv2

    cv2.fillPoly(mask, [np.round(polygon).astype(np.int32)], 255)
    pixels = image[mask == 255]
    expected = np.array(
        [
            np.mean(np.sort(pixels[:, channel])[int(pixels.shape[0] * 0.1) : pixels.shape[0] - int(pixels.shape[0] * 0.1)])
            for channel in range(3)
        ],
        dtype=np.float32,
    )

    assert np.allclose(measured, expected)
    assert excluded == pytest.approx(0.2)
    assert saturated == 0.0


def test_reference_catalog_from_path_validates_required_metadata(tmp_path: Path):
    path = tmp_path / "bad_reference.json"
    path.write_text(
        """
{
  "chart_name": "ColorChecker 24",
  "chart_version": "dev",
  "illuminant": "D65",
  "observer": "10",
  "patches": [
    {"patch_id": "P01", "reference_lab": [50, 0, 0]}
  ]
}
""",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Referencia de carta invalida"):
        ReferenceCatalog.from_path(path)


def test_reference_catalog_accepts_strict_colorchecker_reference():
    payload = {
        "chart_name": "ColorChecker 24",
        "chart_version": "unit",
        "reference_source": "unit-test",
        "illuminant": "D50",
        "observer": "2",
        "patches": [
            {"patch_id": f"P{i:02d}", "reference_lab": [50.0, 0.0, 0.0]}
            for i in range(1, 25)
        ],
    }

    catalog = ReferenceCatalog(payload, strict=True)

    assert catalog.reference_source == "unit-test"
    assert len(catalog.patch_map) == 24


def test_colorchecker2005_reference_is_strictly_valid():
    reference = ReferenceCatalog.from_path(
        Path("testdata/references/colorchecker24_colorchecker2005_d50.json")
    )

    assert reference.reference_source.startswith("colour-science")
    assert reference.patch_map["P01"]["patch_name"] == "dark skin"
    assert reference.patch_map["P24"]["patch_name"] == "black 2 (1.5 D)"


def test_colorchecker2005_reference_falls_back_to_packaged_resource():
    reference = ReferenceCatalog.from_path(
        Path("/tmp/missing/testdata/references/colorchecker24_colorchecker2005_d50.json")
    )

    assert reference.reference_source.startswith("colour-science")
    assert reference.patch_map["P01"]["patch_name"] == "dark skin"


def test_bundled_reference_catalogs_expose_colorchecker_reference():
    catalogs = bundled_reference_catalogs()

    assert catalogs
    assert catalogs[0]["path"] == "colorchecker24_colorchecker2005_d50.json"
    assert "ColorChecker 24" in catalogs[0]["label"]


def test_reference_catalog_template_is_strictly_valid_for_custom_colorchecker():
    payload = reference_catalog_template(chart_name="ColorChecker personalizada", patch_count=24)

    catalog = ReferenceCatalog(payload, strict=True)

    assert catalog.chart_name == "ColorChecker personalizada"
    assert len(catalog.patches) == 24
