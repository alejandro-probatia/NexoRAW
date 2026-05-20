from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from functools import lru_cache
import threading
import time as _time

import cv2
import numpy as np

from ..core.models import DevelopResult, Recipe
from ..core.recipe import scientific_guard
from ..core.utils import read_image, write_tiff16
from .compat import open_rawpy, rawpy
from .metadata import raw_info


LIBRAW_DEMOSAIC_MAP = {
    "linear": "LINEAR",
    "vng": "VNG",
    "ppg": "PPG",
    "ahd": "AHD",
    "modified_ahd": "MODIFIED_AHD",
    "aahd": "AAHD",
    "afd": "AFD",
    "vcd": "VCD",
    "vcd_modified_ahd": "VCD_MODIFIED_AHD",
    "dcb": "DCB",
    "dht": "DHT",
    "lmmse": "LMMSE",
    "amaze": "AMAZE",
}

LIBRAW_HIGHLIGHT_MODE_MAP = {
    "clip": "Clip",
    "ignore": "Ignore",
    "blend": "Blend",
    "reconstruct": "ReconstructDefault",
    "reconstruct_default": "ReconstructDefault",
}

GPL2_DEMOSAIC_ALGORITHMS = {"afd", "lmmse", "modified_ahd", "vcd", "vcd_modified_ahd"}
GPL3_DEMOSAIC_ALGORITHMS = {"amaze"}


RAW_SUFFIXES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}
DEMOSAIC_CACHE_SCHEMA = "probraw-demosaic-cache-v4"
DEMOSAIC_CACHE_MAX_GB_ENV = "PROBRAW_DEMOSAIC_CACHE_MAX_GB"
DEFAULT_DEMOSAIC_CACHE_MAX_GB = 5.0
MAX_FALSE_COLOR_SUPPRESSION_STEPS = 10
RAW_SHA_CACHE_ENV = "PROBRAW_RAW_SHA_CACHE"
_RAW_SHA_CACHE_LOCK = threading.RLock()
_RAW_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_RAW_SHA_CACHE_MAX_ENTRIES = 256
_DEMOSAIC_PRUNE_INTERVAL_S = 120.0
_DEMOSAIC_PRUNE_LAST: dict[str, float] = {}
_DEMOSAIC_PRUNE_LAST_LOCK = threading.RLock()

STANDARD_OUTPUT_ALIASES = {
    "srgb": "srgb",
    "s_rgb": "srgb",
    "s-rgb": "srgb",
    "adobe_rgb": "adobe_rgb",
    "adobergb": "adobe_rgb",
    "adobe-rgb": "adobe_rgb",
    "adobe_rgb_1998": "adobe_rgb",
    "adobe-rgb-1998": "adobe_rgb",
    "adobe rgb (1998)": "adobe_rgb",
    "prophoto": "prophoto_rgb",
    "prophoto_rgb": "prophoto_rgb",
    "prophoto-rgb": "prophoto_rgb",
    "romm_rgb": "prophoto_rgb",
    "romm-rgb": "prophoto_rgb",
}


def develop_controlled(
    input_path: Path,
    recipe: Recipe,
    out_tiff: Path,
    audit_linear_tiff: Path | None = None,
    *,
    cache_dir: Path | None = None,
) -> DevelopResult:
    metadata = raw_info(input_path) if input_path.suffix.lower() in RAW_SUFFIXES else _fake_metadata(input_path)
    guard = scientific_guard(recipe)

    is_raw_input = input_path.suffix.lower() in RAW_SUFFIXES
    uses_standard_output = is_standard_output_space(recipe.output_space)
    if uses_standard_output and is_raw_input:
        audit_linear = develop_scene_linear_array(input_path, recipe, cache_dir=cache_dir)
        render_linear = develop_standard_linear_array(input_path, recipe, cache_dir=cache_dir)
    else:
        render_linear = (
            develop_standard_linear_array(input_path, recipe, cache_dir=cache_dir)
            if uses_standard_output
            else develop_scene_linear_array(input_path, recipe, cache_dir=cache_dir)
        )
        audit_linear = render_linear

    audit_path_str: str | None = None
    if audit_linear_tiff is not None:
        write_tiff16(audit_linear_tiff, audit_linear)
        audit_path_str = str(audit_linear_tiff)

    image = render_recipe_output_array(render_linear, recipe)

    write_tiff16(out_tiff, image)

    return DevelopResult(
        raw_metadata=metadata,
        recipe=recipe,
        scientific_guard=guard,
        output_tiff=str(out_tiff),
        audit_tiff=audit_path_str,
    )


def _develop_image(input_path: Path, recipe: Recipe) -> np.ndarray:
    return develop_scene_linear_array(input_path, recipe)


def develop_scene_linear_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    if input_path.suffix.lower() not in RAW_SUFFIXES:
        return read_image(input_path)

    validate_raw_backend_recipe(recipe)
    developer = recipe.raw_developer.strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'libraw'.")
    if bool(getattr(recipe, "use_cache", False)) and not half_size and cache_dir is not None:
        cached = _read_demosaic_cache(input_path, recipe, cache_dir, output_color_space="camera_raw")
        if cached is not None:
            return cached
        image = develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space="camera_raw")
        _write_demosaic_cache(input_path, recipe, cache_dir, image, output_color_space="camera_raw")
        _maybe_prune_demosaic_cache(cache_dir)
        return image
    return develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space="camera_raw")


def develop_standard_linear_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    output_space = canonical_standard_output_space(recipe.output_space)
    if output_space is None:
        raise RuntimeError(
            f"output_space no es un espacio RGB estandar soportado: {recipe.output_space!r}"
        )
    if input_path.suffix.lower() not in RAW_SUFFIXES:
        return read_image(input_path)

    validate_raw_backend_recipe(recipe, output_color_space=output_space)
    developer = recipe.raw_developer.strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'libraw'.")
    if bool(getattr(recipe, "use_cache", False)) and not half_size and cache_dir is not None:
        cached = _read_demosaic_cache(input_path, recipe, cache_dir, output_color_space=output_space)
        if cached is not None:
            return cached
        image = develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space=output_space)
        _write_demosaic_cache(input_path, recipe, cache_dir, image, output_color_space=output_space)
        _maybe_prune_demosaic_cache(cache_dir)
        return image
    return develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space=output_space)


def render_recipe_output_array(image_linear_rgb: np.ndarray, recipe: Recipe) -> np.ndarray:
    image = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)

    if recipe.exposure_compensation != 0.0:
        image = np.clip(image * (2.0 ** float(recipe.exposure_compensation)), 0.0, 1.0)

    tone_curve = recipe.tone_curve.lower()
    if tone_curve == "srgb":
        image = _apply_srgb_oetf(image)
    elif tone_curve.startswith("gamma:"):
        gamma = float(tone_curve.split(":", 1)[1])
        image = np.clip(np.power(np.clip(image, 0.0, 1.0), 1.0 / gamma), 0.0, 1.0)

    return np.clip(image, 0.0, 1.0).astype(np.float32)


def develop_image_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    image = develop_scene_linear_array(input_path, recipe, half_size=half_size, cache_dir=cache_dir)
    return render_recipe_output_array(image, recipe)


def develop_standard_output_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    image = develop_standard_linear_array(input_path, recipe, half_size=half_size, cache_dir=cache_dir)
    return render_recipe_output_array(image, recipe)


def develop_with_libraw(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    output_color_space: str = "camera_raw",
) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.")

    validate_raw_backend_recipe(recipe, output_color_space=output_color_space)
    kwargs = _build_libraw_postprocess_kwargs(recipe, half_size=half_size, output_color_space=output_color_space)
    try:
        with open_rawpy(input_path, unpack=True) as raw:
            image = raw.postprocess(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Fallo de decodificacion RAW con LibRaw/rawpy: {exc}") from exc
    image_float = _postprocess_output_to_float(image)
    return apply_raw_demosaic_postprocess(image_float, recipe)


def validate_raw_backend_recipe(recipe: Recipe, *, output_color_space: str = "camera_raw") -> None:
    errors = unsupported_raw_backend_options(recipe, output_color_space=output_color_space)
    if errors:
        raise RuntimeError("Receta no ejecutable fielmente por LibRaw/rawpy: " + "; ".join(errors))


def unsupported_raw_backend_options(recipe: Recipe, *, output_color_space: str = "camera_raw") -> list[str]:
    errors: list[str] = []
    developer = str(recipe.raw_developer or "").strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        errors.append(f"raw_developer no soportado: {recipe.raw_developer!r}")
        return errors

    if rawpy is None:
        errors.append("dependencia 'rawpy'/'LibRaw' no disponible")
        return errors

    demosaic_reason = unavailable_demosaic_reason(recipe.demosaic_algorithm)
    if demosaic_reason is not None:
        errors.append(demosaic_reason)

    try:
        _libraw_output_color_value(output_color_space)
    except Exception as exc:
        errors.append(str(exc))

    try:
        _libraw_highlight_mode_value(getattr(recipe, "libraw_highlight_mode", "clip"))
    except Exception as exc:
        errors.append(str(exc))

    if bool(getattr(recipe, "four_color_rgb", False)) and not rawpy_postprocess_parameter_supported("four_color_rgb"):
        errors.append("four_color_rgb requiere soporte rawpy.Params(four_color_rgb=...)")

    optional_checks = [
        ("libraw_auto_bright_thr", 0.01, "auto_bright_thr"),
        ("libraw_adjust_maximum_thr", 0.75, "adjust_maximum_thr"),
        ("libraw_exp_shift", 1.0, "exp_shift"),
        ("libraw_exp_preserve_highlights", 0.0, "exp_preserve_highlights"),
    ]
    for field_name, default, parameter in optional_checks:
        if _float_recipe_option_changed(getattr(recipe, field_name, default), default) and not rawpy_postprocess_parameter_supported(parameter):
            errors.append(f"{field_name} requiere soporte rawpy.Params({parameter}=...)")

    if bool(getattr(recipe, "libraw_no_auto_scale", False)) and not rawpy_postprocess_parameter_supported("no_auto_scale"):
        errors.append("libraw_no_auto_scale requiere soporte rawpy.Params(no_auto_scale=...)")

    ca_red = getattr(recipe, "libraw_chromatic_aberration_red", 1.0)
    ca_blue = getattr(recipe, "libraw_chromatic_aberration_blue", 1.0)
    if (
        _float_recipe_option_changed(ca_red, 1.0)
        or _float_recipe_option_changed(ca_blue, 1.0)
    ) and not rawpy_postprocess_parameter_supported("chromatic_aberration"):
        errors.append("libraw_chromatic_aberration_* requiere soporte rawpy.Params(chromatic_aberration=...)")

    return errors


def effective_raw_processing_settings(
    recipe: Recipe,
    *,
    output_color_space: str = "camera_raw",
    half_size: bool = False,
) -> dict[str, object]:
    validate_raw_backend_recipe(recipe, output_color_space=output_color_space)
    kwargs = _build_libraw_postprocess_kwargs(
        recipe,
        half_size=half_size,
        output_color_space=output_color_space,
    )
    false_color_steps = max(0, int(getattr(recipe, "false_color_suppression_steps", 0) or 0))
    if false_color_steps <= 0:
        false_color_implementation = "none"
    elif "median_filter_passes" in kwargs:
        false_color_implementation = "libraw_median_filter_passes"
    else:
        false_color_implementation = "probraw_chroma_median"
    return {
        "backend": "LibRaw/rawpy",
        "raw_developer": str(recipe.raw_developer or "libraw"),
        "output_color_space": str(output_color_space),
        "half_size": bool(half_size),
        "postprocess_kwargs": {
            key: _jsonable_libraw_value(value)
            for key, value in sorted(kwargs.items(), key=lambda item: item[0])
        },
        "local_postprocess": {
            "demosaic_edge_crop_pixels": max(0, int(getattr(recipe, "demosaic_edge_quality", 0) or 0)),
            "false_color_suppression_steps": false_color_steps,
            "false_color_suppression_implementation": false_color_implementation,
        },
        "rawpy": {
            "version": str(getattr(rawpy, "__version__", "")) if rawpy is not None else "missing",
            "libraw_version": str(getattr(rawpy, "libraw_version", "")) if rawpy is not None else "missing",
            "feature_flags": rawpy_feature_flags(),
        },
    }


def _float_recipe_option_changed(value: object, default: float) -> bool:
    try:
        parsed = float(value)
    except Exception:
        return False
    return bool(np.isfinite(parsed) and abs(parsed - float(default)) > 1e-9)


def _jsonable_libraw_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable_libraw_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable_libraw_value(item) for key, item in value.items()}
    name = getattr(value, "name", None)
    if name is not None:
        return str(name)
    return str(value)


def _build_libraw_postprocess_kwargs(
    recipe: Recipe,
    *,
    half_size: bool = False,
    output_color_space: str = "camera_raw",
) -> dict:
    if rawpy is None:
        raise RuntimeError("No se puede configurar LibRaw: dependencia 'rawpy' no disponible.")

    wb_mode = recipe.white_balance_mode.strip().lower()
    use_camera_wb = wb_mode == "camera_metadata"
    use_auto_wb = wb_mode in {"auto", "auto_wb", "libraw_auto"}
    user_wb = _libraw_wb(recipe.wb_multipliers) if wb_mode == "fixed" else None

    kwargs = {
        "demosaic_algorithm": libraw_demosaic_value(recipe.demosaic_algorithm),
        "half_size": bool(half_size),
        "use_camera_wb": use_camera_wb,
        "use_auto_wb": use_auto_wb,
        "user_wb": user_wb,
        "output_color": _libraw_output_color_value(output_color_space),
        "output_bps": 16,
        "user_flip": 0,
        "no_auto_bright": not bool(getattr(recipe, "libraw_auto_bright", False)),
        "bright": _positive_float(getattr(recipe, "libraw_bright", 1.0), 1.0),
        "highlight_mode": _libraw_highlight_mode_value(getattr(recipe, "libraw_highlight_mode", "clip")),
        "gamma": (
            _positive_float(getattr(recipe, "libraw_gamma_power", 1.0), 1.0),
            _positive_float(getattr(recipe, "libraw_gamma_slope", 1.0), 1.0),
        ),
    }

    optional_kwargs = {
        "auto_bright_thr": float(np.clip(float(getattr(recipe, "libraw_auto_bright_thr", 0.01)), 0.0, 1.0)),
        "adjust_maximum_thr": float(np.clip(float(getattr(recipe, "libraw_adjust_maximum_thr", 0.75)), 0.0, 1.0)),
        "exp_shift": float(np.clip(float(getattr(recipe, "libraw_exp_shift", 1.0)), 0.25, 8.0)),
        "exp_preserve_highlights": float(np.clip(float(getattr(recipe, "libraw_exp_preserve_highlights", 0.0)), 0.0, 1.0)),
        "no_auto_scale": bool(getattr(recipe, "libraw_no_auto_scale", False)),
        "chromatic_aberration": (
            _positive_float(getattr(recipe, "libraw_chromatic_aberration_red", 1.0), 1.0),
            _positive_float(getattr(recipe, "libraw_chromatic_aberration_blue", 1.0), 1.0),
        ),
    }
    for key, value in optional_kwargs.items():
        if rawpy_postprocess_parameter_supported(key):
            kwargs[key] = value

    if rawpy_postprocess_parameter_supported("four_color_rgb"):
        kwargs["four_color_rgb"] = bool(getattr(recipe, "four_color_rgb", False))

    black_mode = recipe.black_level_mode.strip().lower()
    if black_mode.startswith("fixed:"):
        kwargs["user_black"] = _parse_int_mode_value(black_mode, "fixed")
    elif black_mode.startswith("white:"):
        kwargs["user_sat"] = _parse_int_mode_value(black_mode, "white")

    false_color_steps = max(0, int(getattr(recipe, "false_color_suppression_steps", 0) or 0))
    if false_color_steps > 0 and rawpy_postprocess_parameter_supported("median_filter_passes"):
        kwargs["median_filter_passes"] = false_color_steps

    return kwargs


def _libraw_highlight_mode_value(mode: str):
    if rawpy is None:
        raise RuntimeError("No se puede configurar altas luces: dependencia 'rawpy' no disponible.")
    key = str(mode or "clip").strip().lower()
    enum_name = LIBRAW_HIGHLIGHT_MODE_MAP.get(key)
    if enum_name is None:
        supported = ", ".join(sorted(LIBRAW_HIGHLIGHT_MODE_MAP))
        raise RuntimeError(f"libraw_highlight_mode no soportado: {mode!r}. Valores soportados: {supported}.")
    return getattr(rawpy.HighlightMode, enum_name)


def _positive_float(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return float(default)
    if not np.isfinite(parsed) or parsed <= 0.0:
        return float(default)
    return float(parsed)


def apply_raw_demosaic_postprocess(image: np.ndarray, recipe: Recipe) -> np.ndarray:
    out = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    out = _crop_demosaic_border(out, int(getattr(recipe, "demosaic_edge_quality", 0) or 0))

    false_color_steps = max(0, int(getattr(recipe, "false_color_suppression_steps", 0) or 0))
    if false_color_steps > 0 and not rawpy_postprocess_parameter_supported("median_filter_passes"):
        out = suppress_false_color(out, false_color_steps)
    return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)


def _crop_demosaic_border(image: np.ndarray, border: int) -> np.ndarray:
    amount = max(0, int(border or 0))
    if amount <= 0:
        return np.asarray(image, dtype=np.float32)
    h, w = int(image.shape[0]), int(image.shape[1])
    if h <= amount * 2 or w <= amount * 2:
        return np.asarray(image, dtype=np.float32)
    return np.ascontiguousarray(image[amount : h - amount, amount : w - amount, :3])


def suppress_false_color(image: np.ndarray, steps: int) -> np.ndarray:
    passes = min(MAX_FALSE_COLOR_SUPPRESSION_STEPS, max(0, int(steps or 0)))
    out = np.clip(np.asarray(image, dtype=np.float32)[..., :3], 0.0, 1.0)
    if passes <= 0 or out.ndim != 3 or out.shape[2] < 3:
        return out.astype(np.float32, copy=False)

    # RawTherapee describes this control as median passes on chroma while
    # preserving luminance. We use Rec.709 linear luminance and filter two
    # opponent channels, then solve green back from the unchanged luminance.
    y_weights = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    for _ in range(passes):
        y = np.tensordot(out, y_weights, axes=([-1], [0])).astype(np.float32)
        r_chroma = cv2.medianBlur((out[..., 0] - y).astype(np.float32), 3)
        b_chroma = cv2.medianBlur((out[..., 2] - y).astype(np.float32), 3)
        red = y + r_chroma
        blue = y + b_chroma
        green = (y - y_weights[0] * red - y_weights[2] * blue) / y_weights[1]
        out[..., 0] = red
        out[..., 1] = green
        out[..., 2] = blue
        np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)


def canonical_standard_output_space(output_space: str | None) -> str | None:
    key = str(output_space or "").strip().lower()
    return STANDARD_OUTPUT_ALIASES.get(key)


def is_standard_output_space(output_space: str | None) -> bool:
    return canonical_standard_output_space(output_space) is not None


def _libraw_output_color_value(output_color_space: str):
    if rawpy is None:
        raise RuntimeError("No se puede configurar LibRaw: dependencia 'rawpy' no disponible.")
    key = str(output_color_space or "camera_raw").strip().lower()
    if key in {"camera_raw", "raw", "camera", "camera_rgb", "scene_linear_camera_rgb"}:
        return rawpy.ColorSpace.raw
    key = canonical_standard_output_space(key)
    if key == "srgb":
        return rawpy.ColorSpace.sRGB
    if key == "adobe_rgb":
        return rawpy.ColorSpace.Adobe
    if key == "prophoto_rgb":
        return rawpy.ColorSpace.ProPhoto
    raise RuntimeError(f"output_color_space no soportado por LibRaw/rawpy: {output_color_space!r}")


def libraw_demosaic_value(demosaic_algorithm: str):
    if rawpy is None:
        raise RuntimeError("No se puede configurar demosaicing: dependencia 'rawpy' no disponible.")

    name = str(demosaic_algorithm or "").strip().lower()
    if name not in LIBRAW_DEMOSAIC_MAP:
        supported = ", ".join(sorted(LIBRAW_DEMOSAIC_MAP))
        raise RuntimeError(
            "demosaic_algorithm no soportado por LibRaw/rawpy: "
            f"{demosaic_algorithm!r}. Valores soportados: {supported}."
        )
    reason = unavailable_demosaic_reason(name)
    if reason is not None:
        raise RuntimeError(reason)
    enum_name = LIBRAW_DEMOSAIC_MAP[name]
    return getattr(rawpy.DemosaicAlgorithm, enum_name)


def rawpy_feature_flags() -> dict[str, bool]:
    if rawpy is None:
        return {}
    flags = getattr(rawpy, "flags", None)
    if not isinstance(flags, dict):
        return {}
    return {str(key): bool(value) for key, value in flags.items()}


@lru_cache(maxsize=None)
def rawpy_postprocess_parameter_supported(parameter: str) -> bool:
    if rawpy is None:
        return False
    name = str(parameter or "").strip()
    if not name:
        return False
    test_values = {
        "four_color_rgb": True,
        "dcb_iterations": 1,
        "dcb_enhance": True,
        "median_filter_passes": 1,
        "fbdd_noise_reduction": 0,
        "auto_bright_thr": 0.01,
        "adjust_maximum_thr": 0.75,
        "exp_shift": 1.0,
        "exp_preserve_highlights": 0.0,
        "no_auto_scale": False,
        "chromatic_aberration": (1.0, 1.0),
    }
    if name not in test_values:
        return False
    try:
        rawpy.Params(**{name: test_values[name]})
    except TypeError:
        return False
    except Exception:
        return False
    return True


def is_libraw_demosaic_supported(demosaic_algorithm: str) -> bool:
    return unavailable_demosaic_reason(demosaic_algorithm) is None


def unavailable_demosaic_reason(demosaic_algorithm: str) -> str | None:
    if rawpy is None:
        return "No se puede configurar demosaicing: dependencia 'rawpy' no disponible."

    name = str(demosaic_algorithm or "").strip().lower()
    if name not in LIBRAW_DEMOSAIC_MAP:
        supported = ", ".join(sorted(LIBRAW_DEMOSAIC_MAP))
        return (
            "demosaic_algorithm no soportado por LibRaw/rawpy: "
            f"{demosaic_algorithm!r}. Valores soportados: {supported}."
        )

    flags = rawpy_feature_flags()
    if not flags:
        return None
    if name in GPL3_DEMOSAIC_ALGORITHMS and not flags.get("DEMOSAIC_PACK_GPL3", False):
        return (
            "El algoritmo AMaZE requiere el demosaic pack GPL3 de LibRaw. "
            "Instala rawpy-demosaic o compila rawpy/LibRaw con "
            "LIBRAW_DEMOSAIC_PACK_GPL3; la build actual informa "
            "DEMOSAIC_PACK_GPL3=False."
        )
    if name in GPL2_DEMOSAIC_ALGORITHMS and not flags.get("DEMOSAIC_PACK_GPL2", False):
        return (
            f"El algoritmo {demosaic_algorithm} requiere el demosaic pack GPL2 de LibRaw. "
            "Instala rawpy-demosaic o compila rawpy/LibRaw con "
            "LIBRAW_DEMOSAIC_PACK_GPL2; la build actual informa "
            "DEMOSAIC_PACK_GPL2=False."
        )
    return None


def _libraw_wb(values: list[float] | None) -> list[float] | None:
    if not values:
        return None
    wb = [float(v) for v in values]
    if len(wb) >= 4:
        return [wb[0], wb[1], wb[2], wb[3]]
    if len(wb) == 3:
        return [wb[0], wb[1], wb[2], wb[1]]
    return None


def _parse_int_mode_value(mode: str, prefix: str) -> int:
    raw = mode.split(":", 1)[1]
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Valor invalido para {prefix} level: {raw}") from exc
    if value < 0:
        raise RuntimeError(f"Valor invalido para {prefix} level: {raw}")
    return value


def _postprocess_output_to_float(image: np.ndarray) -> np.ndarray:
    out = np.asarray(image)
    if out.ndim == 2:
        out = np.repeat(out[..., None], 3, axis=2)
    if out.ndim != 3 or out.shape[2] < 3:
        raise RuntimeError(f"Salida LibRaw inesperada: shape={out.shape}")
    out = out[..., :3]

    if np.issubdtype(out.dtype, np.integer):
        maxv = float(np.iinfo(out.dtype).max)
        return np.clip(out.astype(np.float32) / maxv, 0.0, 1.0)
    return np.clip(out.astype(np.float32), 0.0, 1.0)


def _demosaic_cache_key(raw_path: Path, recipe: Recipe, *, output_color_space: str = "camera_raw") -> str:
    path = Path(raw_path)
    st = path.stat()
    h = hashlib.sha256()
    payload = {
        "schema": DEMOSAIC_CACHE_SCHEMA,
        "name": path.name,
        "size": int(st.st_size),
        "sha256": _raw_sha256_cached(path, st.st_size, st.st_mtime_ns),
        "raw_developer": str(recipe.raw_developer),
        "demosaic_algorithm": str(recipe.demosaic_algorithm),
        "demosaic_edge_quality": int(getattr(recipe, "demosaic_edge_quality", 0) or 0),
        "false_color_suppression_steps": int(getattr(recipe, "false_color_suppression_steps", 0) or 0),
        "four_color_rgb": bool(getattr(recipe, "four_color_rgb", False)),
        "libraw_auto_bright": bool(getattr(recipe, "libraw_auto_bright", False)),
        "libraw_auto_bright_thr": float(getattr(recipe, "libraw_auto_bright_thr", 0.01)),
        "libraw_adjust_maximum_thr": float(getattr(recipe, "libraw_adjust_maximum_thr", 0.75)),
        "libraw_bright": float(getattr(recipe, "libraw_bright", 1.0)),
        "libraw_highlight_mode": str(getattr(recipe, "libraw_highlight_mode", "clip")),
        "libraw_exp_shift": float(getattr(recipe, "libraw_exp_shift", 1.0)),
        "libraw_exp_preserve_highlights": float(getattr(recipe, "libraw_exp_preserve_highlights", 0.0)),
        "libraw_no_auto_scale": bool(getattr(recipe, "libraw_no_auto_scale", False)),
        "libraw_gamma_power": float(getattr(recipe, "libraw_gamma_power", 1.0)),
        "libraw_gamma_slope": float(getattr(recipe, "libraw_gamma_slope", 1.0)),
        "libraw_chromatic_aberration_red": float(getattr(recipe, "libraw_chromatic_aberration_red", 1.0)),
        "libraw_chromatic_aberration_blue": float(getattr(recipe, "libraw_chromatic_aberration_blue", 1.0)),
        "white_balance_mode": str(recipe.white_balance_mode),
        "wb_multipliers": [float(v) for v in (recipe.wb_multipliers or [])],
        "black_level_mode": str(recipe.black_level_mode),
        "output_color_space": str(output_color_space),
        "rawpy": str(getattr(rawpy, "__version__", "")) if rawpy is not None else "missing",
        "libraw": str(getattr(rawpy, "libraw_version", "")) if rawpy is not None else "missing",
        "flags": rawpy_feature_flags(),
    }
    h.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def _raw_sha256_cached(path: Path, size: int, mtime_ns: int) -> str:
    cache_enabled = _read_env_bool(RAW_SHA_CACHE_ENV, default=True)
    try:
        resolved = str(path.expanduser().resolve())
    except Exception:
        resolved = str(path)
    key = (resolved, int(size), int(mtime_ns))
    if cache_enabled:
        with _RAW_SHA_CACHE_LOCK:
            cached = _RAW_SHA_CACHE.get(key)
            if cached is not None:
                return cached
    raw_sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            raw_sha.update(chunk)
    digest = raw_sha.hexdigest()
    if cache_enabled:
        with _RAW_SHA_CACHE_LOCK:
            _RAW_SHA_CACHE[key] = digest
            while len(_RAW_SHA_CACHE) > _RAW_SHA_CACHE_MAX_ENTRIES:
                _RAW_SHA_CACHE.pop(next(iter(_RAW_SHA_CACHE)))
    return digest


def _read_env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _demosaic_cache_path(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    *,
    output_color_space: str = "camera_raw",
) -> Path:
    key = _demosaic_cache_key(raw_path, recipe, output_color_space=output_color_space)
    return Path(cache_root) / "demosaic" / key[:2] / f"{key}.npy"


def _read_demosaic_cache(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    *,
    output_color_space: str = "camera_raw",
) -> np.ndarray | None:
    path = _demosaic_cache_path(raw_path, recipe, cache_root, output_color_space=output_color_space)
    try:
        if not path.is_file():
            return None
        image = np.load(str(path), mmap_mode="r", allow_pickle=False)
        image = np.asarray(image, dtype=np.float32)
        if image.ndim != 3 or image.shape[-1] < 3:
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return image[..., :3]
    except Exception:
        return None


def _write_demosaic_cache(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    image: np.ndarray,
    *,
    output_color_space: str = "camera_raw",
) -> None:
    path = _demosaic_cache_path(raw_path, recipe, cache_root, output_color_space=output_color_space)
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        array = np.ascontiguousarray(np.asarray(image, dtype=np.float32)[..., :3])
        with tempfile.NamedTemporaryFile(prefix=path.name, suffix=".tmp", dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            np.save(handle, array, allow_pickle=False)
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _demosaic_cache_max_bytes() -> int:
    raw = os.environ.get(DEMOSAIC_CACHE_MAX_GB_ENV, "").strip()
    try:
        gb = float(raw) if raw else DEFAULT_DEMOSAIC_CACHE_MAX_GB
    except ValueError:
        gb = DEFAULT_DEMOSAIC_CACHE_MAX_GB
    return max(0, int(gb * 1024 * 1024 * 1024))


def _maybe_prune_demosaic_cache(cache_root: Path) -> None:
    key = str(Path(cache_root).resolve())
    now = _time.monotonic()
    with _DEMOSAIC_PRUNE_LAST_LOCK:
        if now - _DEMOSAIC_PRUNE_LAST.get(key, 0.0) < _DEMOSAIC_PRUNE_INTERVAL_S:
            return
        _DEMOSAIC_PRUNE_LAST[key] = now
    _prune_demosaic_cache(cache_root)


def _prune_demosaic_cache(cache_root: Path) -> None:
    max_bytes = _demosaic_cache_max_bytes()
    if max_bytes <= 0:
        return
    root = Path(cache_root) / "demosaic"
    try:
        files = [p for p in root.glob("*/*.npy") if p.is_file()]
    except Exception:
        return
    entries: list[tuple[float, int, Path]] = []
    total = 0
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        size = int(st.st_size)
        total += size
        entries.append((float(st.st_atime), size, path))
    if total <= max_bytes:
        return
    for _atime, size, path in sorted(entries, key=lambda item: item[0]):
        try:
            path.unlink()
            total -= size
        except OSError:
            pass
        if total <= max_bytes:
            break


def _apply_srgb_oetf(x: np.ndarray) -> np.ndarray:
    # Encoding transfer curve for an explicit `tone_curve: srgb` recipe.
    # This is not the GUI display path: managed previews must remain
    # `source ICC -> monitor ICC`, never `source ICC -> sRGB -> screen`.
    x = np.asarray(x, dtype=np.float32)
    out = np.empty_like(x, dtype=np.float32)
    np.clip(x, 0.0, 1.0, out=out)
    np.power(out, np.float32(1.0 / 2.4), out=out)
    out *= np.float32(1.055)
    out -= np.float32(0.055)
    low = x <= np.float32(0.0031308)
    if np.any(low):
        out[low] = np.float32(12.92) * x[low]
    np.clip(out, 0.0, 1.0, out=out)
    return out


def _fake_metadata(path: Path):
    from ..core.models import RawMetadata
    from ..core.utils import sha256_file

    return RawMetadata(
        source_file=str(path),
        input_sha256=sha256_file(path),
        camera_model="non-raw-input",
        cfa_pattern="none",
        available_white_balance="unknown",
        wb_multipliers=None,
        black_level=None,
        white_level=None,
        color_matrix_hint=None,
        iso=None,
        exposure_time_seconds=None,
        lens_model=None,
        capture_datetime=None,
        dimensions=None,
        intermediate_working_space="scene_linear_camera_rgb",
        embedded_profile_description=None,
        embedded_profile_source=None,
    )
