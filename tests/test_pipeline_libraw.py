from pathlib import Path
import hashlib
import os

import numpy as np
import pytest
import rawpy
import tifffile

from probraw.core.models import Recipe
from probraw.raw import pipeline
from probraw.core.utils import read_image
from probraw.raw.pipeline import (
    _build_libraw_postprocess_kwargs,
    _crop_demosaic_border,
    _develop_image,
    _parse_int_mode_value,
    apply_raw_demosaic_postprocess,
    develop_scene_linear_array,
    develop_image_array,
    develop_standard_output_array,
    develop_controlled,
    libraw_demosaic_value,
    suppress_false_color,
    validate_raw_backend_recipe,
)


def test_build_libraw_kwargs_with_amaze_fixed_wb_and_black_level(monkeypatch):
    monkeypatch.setattr(pipeline.rawpy, "flags", {"DEMOSAIC_PACK_GPL3": True})
    recipe = Recipe(
        raw_developer="libraw",
        demosaic_algorithm="amaze",
        white_balance_mode="fixed",
        wb_multipliers=[2.0, 1.0, 1.5],
        black_level_mode="fixed:64",
    )
    kwargs = _build_libraw_postprocess_kwargs(recipe)

    assert kwargs["demosaic_algorithm"] == rawpy.DemosaicAlgorithm.AMAZE
    assert kwargs["user_wb"] == [2.0, 1.0, 1.5, 1.0]
    assert kwargs["user_black"] == 64
    assert kwargs["output_color"] == rawpy.ColorSpace.raw
    assert kwargs["output_bps"] == 16
    assert kwargs["gamma"] == (1.0, 1.0)
    assert kwargs["no_auto_bright"] is True


def test_build_libraw_kwargs_with_camera_wb_and_white_level():
    recipe = Recipe(
        raw_developer="libraw",
        demosaic_algorithm="ahd",
        white_balance_mode="camera_metadata",
        black_level_mode="white:15000",
    )
    kwargs = _build_libraw_postprocess_kwargs(recipe)

    assert kwargs["demosaic_algorithm"] == rawpy.DemosaicAlgorithm.AHD
    assert kwargs["use_camera_wb"] is True
    assert kwargs["user_wb"] is None
    assert kwargs["user_sat"] == 15000


def test_build_libraw_kwargs_exposes_color_render_options():
    recipe = Recipe(
        white_balance_mode="auto",
        libraw_auto_bright=True,
        libraw_auto_bright_thr=0.02,
        libraw_adjust_maximum_thr=0.5,
        libraw_bright=1.25,
        libraw_highlight_mode="blend",
        libraw_exp_shift=1.5,
        libraw_exp_preserve_highlights=0.4,
        libraw_no_auto_scale=True,
        libraw_gamma_power=2.222,
        libraw_gamma_slope=4.5,
        libraw_chromatic_aberration_red=1.001,
        libraw_chromatic_aberration_blue=0.999,
    )

    kwargs = _build_libraw_postprocess_kwargs(recipe)

    assert kwargs["use_auto_wb"] is True
    assert kwargs["use_camera_wb"] is False
    assert kwargs["user_wb"] is None
    assert kwargs["no_auto_bright"] is False
    assert kwargs["auto_bright_thr"] == 0.02
    assert kwargs["adjust_maximum_thr"] == 0.5
    assert kwargs["bright"] == 1.25
    assert kwargs["highlight_mode"] == rawpy.HighlightMode.Blend
    assert kwargs["exp_shift"] == 1.5
    assert kwargs["exp_preserve_highlights"] == 0.4
    assert kwargs["no_auto_scale"] is True
    assert kwargs["gamma"] == (2.222, 4.5)
    assert kwargs["chromatic_aberration"] == (1.001, 0.999)


def test_build_libraw_kwargs_includes_supported_raw_demosaic_options(monkeypatch):
    monkeypatch.setattr(pipeline, "rawpy_postprocess_parameter_supported", lambda name: name in {"dcb_iterations", "median_filter_passes", "four_color_rgb"})
    recipe = Recipe(
        demosaic_algorithm="dcb",
        demosaic_edge_quality=3,
        false_color_suppression_steps=2,
        four_color_rgb=True,
    )
    kwargs = _build_libraw_postprocess_kwargs(recipe)

    assert kwargs["four_color_rgb"] is True
    assert "dcb_iterations" not in kwargs
    assert kwargs["median_filter_passes"] == 2


def test_build_libraw_kwargs_omits_unavailable_raw_demosaic_options(monkeypatch):
    monkeypatch.setattr(pipeline, "rawpy_postprocess_parameter_supported", lambda _name: False)
    recipe = Recipe(
        demosaic_algorithm="dcb",
        demosaic_edge_quality=3,
        false_color_suppression_steps=2,
        four_color_rgb=True,
    )
    kwargs = _build_libraw_postprocess_kwargs(recipe)

    assert "four_color_rgb" not in kwargs
    assert "dcb_iterations" not in kwargs
    assert "median_filter_passes" not in kwargs


def test_crop_demosaic_border_removes_perimeter_pixels():
    image = np.arange(6 * 8 * 3, dtype=np.float32).reshape(6, 8, 3)
    cropped = _crop_demosaic_border(image, 2)

    assert cropped.shape == (2, 4, 3)
    assert np.array_equal(cropped, image[2:-2, 2:-2])


def test_suppress_false_color_reduces_chroma_without_changing_luminance():
    image = np.full((7, 7, 3), 0.5, dtype=np.float32)
    image[3, 3, 0] = 0.9
    image[3, 3, 2] = 0.2
    image[3, 3, 1] = (0.5 - 0.2126 * image[3, 3, 0] - 0.0722 * image[3, 3, 2]) / 0.7152

    filtered = suppress_false_color(image, 1)
    weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    original_y = float(np.dot(image[3, 3], weights))
    filtered_y = float(np.dot(filtered[3, 3], weights))

    assert filtered.dtype == np.float32
    assert abs(filtered_y - original_y) < 1e-5
    assert abs(float(filtered[3, 3, 0]) - 0.5) < abs(float(image[3, 3, 0]) - 0.5)
    assert abs(float(filtered[3, 3, 2]) - 0.5) < abs(float(image[3, 3, 2]) - 0.5)


def test_raw_demosaic_postprocess_uses_local_false_color_fallback(monkeypatch):
    monkeypatch.setattr(pipeline, "rawpy_postprocess_parameter_supported", lambda _name: False)
    image = np.full((7, 7, 3), 0.5, dtype=np.float32)
    image[3, 3, 0] = 0.9
    image[3, 3, 2] = 0.2
    image[3, 3, 1] = (0.5 - 0.2126 * image[3, 3, 0] - 0.0722 * image[3, 3, 2]) / 0.7152

    processed = apply_raw_demosaic_postprocess(
        image,
        Recipe(demosaic_edge_quality=1, false_color_suppression_steps=1),
    )

    assert processed.shape == (5, 5, 3)
    assert abs(float(processed[2, 2, 0]) - 0.5) < abs(float(image[3, 3, 0]) - 0.5)


def test_build_libraw_kwargs_uses_real_standard_output_spaces():
    assert (
        _build_libraw_postprocess_kwargs(
            Recipe(output_space="srgb"),
            output_color_space="srgb",
        )["output_color"]
        == rawpy.ColorSpace.sRGB
    )
    assert (
        _build_libraw_postprocess_kwargs(
            Recipe(output_space="adobe_rgb"),
            output_color_space="Adobe RGB (1998)",
        )["output_color"]
        == rawpy.ColorSpace.Adobe
    )
    assert (
        _build_libraw_postprocess_kwargs(
            Recipe(output_space="prophoto_rgb"),
            output_color_space="prophoto_rgb",
        )["output_color"]
        == rawpy.ColorSpace.ProPhoto
    )


def test_parse_int_mode_value_rejects_invalid():
    with pytest.raises(RuntimeError):
        _parse_int_mode_value("fixed:abc", "fixed")


def test_libraw_demosaic_rejects_unsupported():
    with pytest.raises(RuntimeError, match="demosaic_algorithm no soportado"):
        libraw_demosaic_value("rcd")


def test_libraw_demosaic_rejects_amaze_without_gpl3_pack(monkeypatch):
    monkeypatch.setattr(pipeline.rawpy, "flags", {"DEMOSAIC_PACK_GPL3": False})
    with pytest.raises(RuntimeError, match="GPL3"):
        libraw_demosaic_value("amaze")


def test_develop_image_rejects_unknown_raw_developer():
    recipe = Recipe(raw_developer="other-engine")
    with pytest.raises(RuntimeError, match="raw_developer no soportado"):
        _develop_image(Path("/tmp/capture.nef"), recipe)


def test_raw_sha_cache_can_be_disabled_for_strict_rehash(tmp_path: Path, monkeypatch):
    source = tmp_path / "capture.nef"
    source.write_bytes(b"abc")
    stat = source.stat()
    pipeline._RAW_SHA_CACHE.clear()

    first = pipeline._raw_sha256_cached(source, stat.st_size, stat.st_mtime_ns)
    source.write_bytes(b"xyz")
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    cached = pipeline._raw_sha256_cached(source, stat.st_size, stat.st_mtime_ns)
    monkeypatch.setenv("PROBRAW_RAW_SHA_CACHE", "0")
    strict = pipeline._raw_sha256_cached(source, stat.st_size, stat.st_mtime_ns)

    assert cached == first
    assert strict == hashlib.sha256(b"xyz").hexdigest()


def test_develop_controlled_writes_audit_before_output_adjustments(tmp_path: Path):
    source = tmp_path / "input.tiff"
    out = tmp_path / "out.tiff"
    audit = tmp_path / "audit_linear.tiff"

    image = np.zeros((8, 10, 3), dtype=np.uint16)
    image[..., 0] = 9000
    image[..., 1] = 14000
    image[..., 2] = 22000
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        exposure_compensation=1.0,
        tone_curve="srgb",
        output_linear=False,
    )
    develop_controlled(source, recipe, out, audit)

    source_linear = read_image(source)
    audit_linear = read_image(audit)
    rendered = read_image(out)

    assert np.allclose(audit_linear, source_linear, atol=1 / 65535)
    assert not np.allclose(rendered, audit_linear, atol=1e-3)


def test_develop_controlled_writes_scene_linear_audit_before_standard_raw_conversion(tmp_path: Path, monkeypatch):
    raw = tmp_path / "capture.nef"
    raw.write_bytes(b"fake raw bytes")
    out = tmp_path / "out.tiff"
    audit = tmp_path / "audit_linear.tiff"
    calls: list[str] = []

    def fake_develop_with_libraw(_path, _recipe, *, half_size=False, output_color_space="camera_raw"):
        calls.append(output_color_space)
        value = 0.2 if output_color_space == "camera_raw" else 0.8
        return np.full((4, 5, 3), value, dtype=np.float32)

    monkeypatch.setattr(pipeline, "raw_info", pipeline._fake_metadata)
    monkeypatch.setattr(pipeline, "develop_with_libraw", fake_develop_with_libraw)

    develop_controlled(
        raw,
        Recipe(output_space="srgb", output_linear=False, tone_curve="linear"),
        out,
        audit,
    )

    assert calls == ["camera_raw", "srgb"]
    assert np.allclose(read_image(audit), 0.2, atol=1 / 65535)
    assert np.allclose(read_image(out), 0.8, atol=1 / 65535)


def test_validate_raw_backend_recipe_rejects_declared_unsupported_option(monkeypatch):
    monkeypatch.setattr(pipeline, "rawpy_postprocess_parameter_supported", lambda _name: False)

    with pytest.raises(RuntimeError, match="four_color_rgb"):
        validate_raw_backend_recipe(Recipe(four_color_rgb=True))


def test_develop_image_array_matches_develop_controlled_output(tmp_path: Path):
    source = tmp_path / "input.tiff"
    out = tmp_path / "out.tiff"

    image = np.zeros((8, 10, 3), dtype=np.uint16)
    image[..., 0] = 8000
    image[..., 1] = 16000
    image[..., 2] = 24000
    tifffile.imwrite(str(source), image, photometric="rgb", metadata=None)

    recipe = Recipe(
        exposure_compensation=0.5,
        tone_curve="gamma:2.2",
        output_linear=False,
    )
    develop_controlled(source, recipe, out, None)

    array_first = develop_image_array(source, recipe)
    rendered = read_image(out)

    assert array_first.dtype == np.float32
    assert array_first.shape == rendered.shape
    assert np.allclose(array_first, rendered, atol=1 / 65535)


def test_scene_linear_demosaic_cache_reuses_raw_decode(tmp_path: Path, monkeypatch):
    raw = tmp_path / "capture.nef"
    raw.write_bytes(b"fake-raw-cache-input")
    cache = tmp_path / "cache"
    calls = {"count": 0}

    def fake_develop_with_libraw(_path, _recipe, *, half_size=False, output_color_space="camera_raw"):
        calls["count"] += 1
        assert half_size is False
        assert output_color_space == "camera_raw"
        return np.full((4, 5, 3), 0.25, dtype=np.float32)

    monkeypatch.setattr(pipeline, "develop_with_libraw", fake_develop_with_libraw)
    recipe = Recipe(use_cache=True, exposure_compensation=0.0)

    first = develop_scene_linear_array(raw, recipe, cache_dir=cache)
    second = develop_scene_linear_array(raw, Recipe(use_cache=True, exposure_compensation=1.0), cache_dir=cache)

    assert calls["count"] == 1
    assert np.allclose(first, second)
    assert list((cache / "demosaic").glob("*/*.npy"))


def test_scene_linear_demosaic_cache_key_includes_demosaic_algorithm(tmp_path: Path, monkeypatch):
    raw = tmp_path / "capture.nef"
    raw.write_bytes(b"fake-raw-cache-input")
    cache = tmp_path / "cache"
    calls = {"count": 0}

    def fake_develop_with_libraw(_path, recipe, *, half_size=False, output_color_space="camera_raw"):
        calls["count"] += 1
        assert output_color_space == "camera_raw"
        value = 0.2 if recipe.demosaic_algorithm == "dcb" else 0.4
        return np.full((4, 5, 3), value, dtype=np.float32)

    monkeypatch.setattr(pipeline, "develop_with_libraw", fake_develop_with_libraw)

    first = develop_scene_linear_array(raw, Recipe(use_cache=True, demosaic_algorithm="dcb"), cache_dir=cache)
    second = develop_scene_linear_array(raw, Recipe(use_cache=True, demosaic_algorithm="ahd"), cache_dir=cache)

    assert calls["count"] == 2
    assert not np.allclose(first, second)


def test_demosaic_cache_key_reuses_raw_sha_for_unchanged_file(tmp_path: Path, monkeypatch):
    raw = tmp_path / "capture.nef"
    raw.write_bytes(b"fake-raw-cache-input" * 8)
    recipe = Recipe(use_cache=True, demosaic_algorithm="dcb")
    opens = {"count": 0}
    original_open = Path.open

    pipeline._RAW_SHA_CACHE.clear()

    def counting_open(self, *args, **kwargs):
        if self == raw:
            opens["count"] += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    first = pipeline._demosaic_cache_key(raw, recipe)
    second = pipeline._demosaic_cache_key(raw, recipe)

    assert first == second
    assert opens["count"] == 1


def test_develop_standard_output_array_requests_standard_libraw_space(tmp_path: Path, monkeypatch):
    raw = tmp_path / "capture.nef"
    raw.write_bytes(b"fake-raw")
    captured: dict[str, str] = {}

    def fake_develop_with_libraw(_path, _recipe, *, half_size=False, output_color_space="camera_raw"):
        captured["space"] = output_color_space
        captured["half_size"] = str(bool(half_size))
        return np.full((4, 5, 3), 0.25, dtype=np.float32)

    monkeypatch.setattr(pipeline, "develop_with_libraw", fake_develop_with_libraw)

    out = develop_standard_output_array(
        raw,
        Recipe(output_space="prophoto_rgb", output_linear=False, tone_curve="gamma:1.8"),
    )

    assert captured == {"space": "prophoto_rgb", "half_size": "False"}
    assert out.dtype == np.float32
    assert out.shape == (4, 5, 3)
