from __future__ import annotations

import io
from pathlib import Path
import os
import threading
from dataclasses import asdict
from functools import lru_cache

import cv2
import numpy as np
import colour
from colour.adaptation import matrix_chromatic_adaptation_VonKries
from PIL import Image, ImageCms, ImageOps

from ..core.models import Recipe
from ..core.recipe import load_recipe
from ..core.utils import RAW_EXTENSIONS, read_image
from ..profile.export import apply_profile_matrix
from ..profile.generic import generic_output_profile, is_generic_output_space
from .compat import open_rawpy, rawpy
from .pipeline import develop_image_array, develop_standard_output_array, is_standard_output_space


_PROFILE_PREVIEW_LUT_CACHE: dict[tuple[str, int, str], np.ndarray] = {}
_STANDARD_TO_SRGB_MATRIX_CACHE: dict[str, np.ndarray] = {}
_RADIAL_MAP_CACHE: dict[tuple[int, int, float], tuple[np.ndarray, np.ndarray]] = {}
_RADIAL_MAP_CACHE_LOCK = threading.RLock()
_RADIAL_MAP_CACHE_MAX = 4
PREVIEW_HQ_HALF_SIZE_ENV = "PROBRAW_PREVIEW_HQ_HALF_SIZE"


def load_image_for_preview(
    input_path: Path,
    recipe_path: Path | None = None,
    *,
    recipe: Recipe | None = None,
    fast_raw: bool = True,
    max_preview_side: int = 2600,
    input_profile_path: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[np.ndarray, str]:
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")

    if input_path.suffix.lower() not in RAW_EXTENSIONS:
        image = _read_non_raw_image_for_preview(input_path, max_preview_side=max_preview_side)
        return image, f"Imagen cargada: {input_path.name}"

    if recipe is None:
        if recipe_path is None:
            raise RuntimeError("Para previsualizar RAW debes indicar una receta YAML/JSON.")
        if not recipe_path.exists():
            raise FileNotFoundError(f"No existe la receta: {recipe_path}")
        recipe = load_recipe(recipe_path)

    if fast_raw:
        image = _develop_raw_fast_preview(
            input_path,
            recipe,
            max_preview_side=max_preview_side,
            input_profile_path=input_profile_path,
            cache_dir=cache_dir,
        )
        image = _downscale_for_preview(image, max_preview_side=max_preview_side)
        image = _camera_rgb_display_balance_if_needed(
            image,
            recipe,
            input_profile_path=input_profile_path,
        )
        return image, f"RAW previsualizado en modo rapido LibRaw: {input_path.name}"

    # Preview de alta calidad: mismo render que develop_controlled, sin TIFF temporal.
    half_size_hq = _prefer_half_size_high_quality_preview(input_path, max_preview_side=max_preview_side)
    develop_recipe = _recipe_with_preview_cache_enabled(recipe) if cache_dir is not None and not half_size_hq else recipe
    develop_cache_dir = cache_dir if cache_dir is not None and not half_size_hq else None
    image = (
        develop_standard_output_array(input_path, develop_recipe, half_size=half_size_hq, cache_dir=develop_cache_dir)
        if _preview_uses_standard_output_source(recipe, input_profile_path=input_profile_path)
        else develop_image_array(input_path, develop_recipe, half_size=half_size_hq, cache_dir=develop_cache_dir)
    )
    image = _downscale_for_preview(image, max_preview_side=max_preview_side)
    image = _camera_rgb_display_balance_if_needed(
        image,
        recipe,
        input_profile_path=input_profile_path,
    )
    if half_size_hq:
        return image, f"RAW previsualizado HQ optimizado (half-size): {input_path.name}"
    return image, f"RAW revelado completo para preview de alta calidad: {input_path.name}"


def _preview_uses_standard_output_source(recipe: Recipe, *, input_profile_path: Path | None = None) -> bool:
    return input_profile_path is None and is_standard_output_space(recipe.output_space)


def _develop_raw_fast_preview(
    input_path: Path,
    recipe: Recipe,
    *,
    max_preview_side: int = 2600,
    input_profile_path: Path | None = None,
    allow_embedded_preview: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    if allow_embedded_preview and input_profile_path is None:
        embedded = extract_embedded_preview(input_path, max_preview_side=max_preview_side)
        if embedded is not None:
            return embedded

    cached_recipe = _recipe_with_preview_cache_enabled(recipe) if cache_dir is not None else recipe
    if _preview_uses_standard_output_source(recipe, input_profile_path=input_profile_path):
        return develop_standard_output_array(input_path, cached_recipe, half_size=True, cache_dir=cache_dir)
    return develop_image_array(input_path, cached_recipe, half_size=True, cache_dir=cache_dir)


def _recipe_with_preview_cache_enabled(recipe: Recipe) -> Recipe:
    cached = Recipe(**asdict(recipe))
    cached.use_cache = True
    return cached


def _prefer_half_size_high_quality_preview(input_path: Path, *, max_preview_side: int) -> bool:
    enabled = _env_enabled(PREVIEW_HQ_HALF_SIZE_ENV, default=True)
    if not enabled:
        return False
    if max_preview_side <= 0:
        return False
    source_max_side = _raw_preview_source_max_side(input_path)
    if source_max_side is None:
        return False
    # Use half-size only when the decoded side stays at or above the requested
    # preview side, avoiding quality loss from upscaling.
    return (source_max_side // 2) >= int(max_preview_side)


def _raw_preview_source_max_side(input_path: Path) -> int | None:
    try:
        with open_rawpy(input_path) as raw:
            sizes = getattr(raw, "sizes", None)
            if sizes is None:
                return None
            dims: list[int] = []
            for attr in ("raw_width", "raw_height", "width", "height", "iwidth", "iheight"):
                value = getattr(sizes, attr, 0)
                try:
                    parsed = int(value)
                except Exception:
                    continue
                if parsed > 0:
                    dims.append(parsed)
            if len(dims) < 2:
                return None
            return int(max(dims))
    except Exception:
        return None


def _env_enabled(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return bool(default)


def _read_non_raw_image_for_preview(input_path: Path, *, max_preview_side: int) -> np.ndarray:
    if int(max_preview_side) <= 0:
        return read_image(input_path).astype(np.float32)
    try:
        return _read_non_raw_image_scaled_with_pillow(input_path, max_preview_side=int(max_preview_side))
    except Exception:
        image = read_image(input_path)
        return _downscale_for_preview(image, max_preview_side=int(max_preview_side))


def _read_non_raw_image_scaled_with_pillow(input_path: Path, *, max_preview_side: int) -> np.ndarray:
    target = int(max_preview_side)
    if target <= 0:
        raise ValueError("max_preview_side debe ser positivo para lectura escalada.")
    with Image.open(input_path) as img:
        try:
            img.draft("RGB", (target, target))
        except Exception:
            pass
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((target, target), Image.Resampling.LANCZOS)
        rgb = np.asarray(img, dtype=np.uint8).copy()
    return np.ascontiguousarray(rgb.astype(np.float32) / np.float32(255.0))


def extract_embedded_preview(
    input_path: Path,
    *,
    max_preview_side: int = 0,
    apply_orientation: bool = True,
) -> np.ndarray | None:
    try:
        with open_rawpy(input_path) as raw:
            raw_orientation = _rawpy_orientation(raw)
            thumb = raw.extract_thumb()
    except Exception:
        return None

    if thumb.format == rawpy.ThumbFormat.JPEG:
        decoded = _decode_embedded_preview_jpeg(
            bytes(thumb.data),
            max_preview_side=max_preview_side,
            raw_orientation=raw_orientation,
            apply_orientation=apply_orientation,
        )
        if decoded is None:
            return None
    elif thumb.format == rawpy.ThumbFormat.BITMAP:
        decoded = np.asarray(thumb.data)
        if decoded.ndim == 2:
            decoded = np.repeat(decoded[..., None], 3, axis=2)
        elif decoded.ndim == 3 and decoded.shape[2] >= 3:
            decoded = decoded[..., :3]
        else:
            return None
        if apply_orientation:
            decoded = _apply_orientation_array(decoded, raw_orientation)
        decoded = _downscale_uint_preview(decoded, max_preview_side=max_preview_side)
    else:
        return None

    if np.issubdtype(decoded.dtype, np.integer):
        maxv = float(np.iinfo(decoded.dtype).max)
        srgb = np.clip(decoded.astype(np.float32) / maxv, 0.0, 1.0)
    else:
        srgb = np.clip(decoded.astype(np.float32), 0.0, 1.0)

    # Embedded previews are generally display-referred (sRGB-encoded).
    # Convert to linear so the rest of the preview pipeline remains consistent.
    return srgb_to_linear_display(srgb)


def extract_embedded_thumbnail(
    input_path: Path,
    *,
    max_side: int = 220,
    apply_orientation: bool = True,
) -> np.ndarray | None:
    try:
        with open_rawpy(input_path) as raw:
            raw_orientation = _rawpy_orientation(raw)
            thumb = raw.extract_thumb()
    except Exception:
        return None

    if thumb.format == rawpy.ThumbFormat.JPEG:
        decoded = _decode_embedded_preview_jpeg(
            bytes(thumb.data),
            max_preview_side=int(max_side),
            raw_orientation=raw_orientation,
            apply_orientation=apply_orientation,
        )
        if decoded is None:
            return None
    elif thumb.format == rawpy.ThumbFormat.BITMAP:
        decoded = np.asarray(thumb.data)
        if decoded.ndim == 2:
            decoded = np.repeat(decoded[..., None], 3, axis=2)
        elif decoded.ndim == 3 and decoded.shape[2] >= 3:
            decoded = decoded[..., :3]
        else:
            return None
        if apply_orientation:
            decoded = _apply_orientation_array(decoded, raw_orientation)
        decoded = _downscale_uint_preview(decoded, max_preview_side=int(max_side))
    else:
        return None
    return _preview_array_to_u8(decoded)


def _decode_embedded_preview_jpeg(
    data: bytes,
    *,
    max_preview_side: int,
    raw_orientation: int = 0,
    apply_orientation: bool = True,
) -> np.ndarray | None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            target = int(max_preview_side)
            if target > 0:
                try:
                    img.draft("RGB", (target, target))
                except Exception:
                    pass
            embedded_orientation = _pil_orientation(img)
            if apply_orientation:
                img = ImageOps.exif_transpose(img)
                if embedded_orientation in {0, 1, None}:
                    img = _apply_orientation_image(img, raw_orientation)
            img = img.convert("RGB")
            if target > 0:
                img.thumbnail((target, target), Image.Resampling.LANCZOS)
            return np.asarray(img, dtype=np.uint8).copy()
    except Exception:
        return None


def _rawpy_orientation(raw) -> int:
    try:
        return int(getattr(getattr(raw, "sizes", None), "flip", 0) or 0)
    except Exception:
        return 0


def _pil_orientation(img: Image.Image) -> int | None:
    try:
        return int(img.getexif().get(274, 1))
    except Exception:
        return None


def _apply_orientation_image(img: Image.Image, orientation: int) -> Image.Image:
    transpose = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }.get(int(orientation or 0))
    if transpose is None:
        return img
    return img.transpose(transpose)


def _apply_orientation_array(image: np.ndarray, orientation: int) -> np.ndarray:
    value = int(orientation or 0)
    if value == 2:
        return np.fliplr(image)
    if value == 3:
        return np.rot90(image, 2)
    if value == 4:
        return np.flipud(image)
    if value == 5:
        return np.transpose(image, (1, 0, *range(2, image.ndim))) if image.ndim > 2 else image.T
    if value == 6:
        return np.rot90(image, 3)
    if value == 7:
        return np.fliplr(np.rot90(image, 3))
    if value == 8:
        return np.rot90(image, 1)
    return image


def _preview_array_to_u8(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 2:
        array = np.repeat(array[..., None], 3, axis=2)
    elif array.ndim == 3 and array.shape[2] > 3:
        array = array[..., :3]
    if np.issubdtype(array.dtype, np.integer):
        if array.dtype == np.uint8:
            return np.ascontiguousarray(array[..., :3])
        maxv = float(np.iinfo(array.dtype).max)
        scaled = np.clip(array.astype(np.float32) / maxv, 0.0, 1.0)
    else:
        scaled = np.clip(array.astype(np.float32), 0.0, 1.0)
    return np.ascontiguousarray(np.round(scaled[..., :3] * 255.0).astype(np.uint8))


def _downscale_uint_preview(image: np.ndarray, *, max_preview_side: int) -> np.ndarray:
    if max_preview_side <= 0:
        return np.asarray(image).copy()
    array = np.asarray(image)
    if array.ndim < 2:
        return array.copy()
    h, w = int(array.shape[0]), int(array.shape[1])
    if max(h, w) <= int(max_preview_side):
        return array.copy()
    scale = float(max_preview_side) / float(max(h, w))
    resized = cv2.resize(
        array,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return np.asarray(resized).copy()


def _downscale_for_preview(image: np.ndarray, *, max_preview_side: int) -> np.ndarray:
    if max_preview_side <= 0:
        return image.astype(np.float32)

    h, w = int(image.shape[0]), int(image.shape[1])
    max_side = max(h, w)
    if max_side <= max_preview_side:
        return image.astype(np.float32)

    scale = float(max_preview_side) / float(max_side)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(image.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    return np.clip(resized, 0.0, 1.0).astype(np.float32)


def _camera_rgb_display_balance_if_needed(
    image: np.ndarray,
    recipe: Recipe,
    *,
    input_profile_path: Path | None = None,
) -> np.ndarray:
    if input_profile_path is not None:
        return image.astype(np.float32)

    output_space = str(recipe.output_space or "").strip().lower()
    if not recipe.profiling_mode and "camera_rgb" not in output_space:
        return image.astype(np.float32)

    rgb = np.clip(image.astype(np.float32), 0.0, 1.0)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return rgb

    means = np.mean(rgb[..., :3], axis=(0, 1), dtype=np.float64)
    if not np.all(np.isfinite(means)) or float(np.min(means)) <= 1e-6:
        return rgb

    if float(np.max(means) / np.min(means)) < 1.35:
        return rgb

    # Display-only neutralisation for unprofiled camera-native previews. Once an
    # input ICC is active, the preview must preserve the source RGB values
    # exactly because the ICC maps that camera-neutral axis to display neutral.
    target = float(np.median(means))
    gains = np.clip(target / means, 0.35, 2.8).astype(np.float32)
    balanced = rgb.copy()
    balanced[..., :3] *= gains.reshape((1, 1, 3))
    return np.clip(balanced, 0.0, 1.0).astype(np.float32)


def apply_adjustments(
    image_linear_rgb: np.ndarray,
    *,
    denoise_luminance: float = 0.0,
    denoise_color: float = 0.0,
    denoise_strength: float | None = None,
    sharpen_amount: float = 0.0,
    sharpen_radius: float = 1.0,
    lateral_ca_red_scale: float = 1.0,
    lateral_ca_blue_scale: float = 1.0,
) -> np.ndarray:
    img = image_linear_rgb.astype(np.float32, copy=False)

    # Backward compatibility: old API used a single denoise value.
    if denoise_strength is not None and denoise_luminance == 0.0 and denoise_color == 0.0:
        denoise_luminance = float(denoise_strength)
        denoise_color = float(denoise_strength)

    dl = float(np.clip(denoise_luminance, 0.0, 1.0))
    dc = float(np.clip(denoise_color, 0.0, 1.0))
    s = float(max(0.0, sharpen_amount))
    ca_changed = abs(float(lateral_ca_red_scale) - 1.0) > 1e-5 or abs(float(lateral_ca_blue_scale) - 1.0) > 1e-5
    if dl <= 0.0 and dc <= 0.0 and s <= 0.0 and not ca_changed:
        return np.clip(img, 0.0, 1.0).astype(np.float32, copy=False)

    out = np.clip(img, 0.0, 1.0)
    if dl > 0.0 or dc > 0.0:
        ycc = cv2.cvtColor(out, cv2.COLOR_RGB2YCrCb)

        if dl > 0.0:
            sigma_l = 0.2 + dl * 3.2
            y = ycc[..., 0]
            y_blur = cv2.GaussianBlur(y, (0, 0), sigmaX=sigma_l, sigmaY=sigma_l, borderType=cv2.BORDER_REFLECT)
            ycc[..., 0] = (1.0 - dl) * y + dl * y_blur

        if dc > 0.0:
            sigma_c = 0.2 + dc * 3.8
            cc = ycc[..., 1:3]
            cc_blur = cv2.GaussianBlur(cc, (0, 0), sigmaX=sigma_c, sigmaY=sigma_c, borderType=cv2.BORDER_REFLECT)
            ycc[..., 1:3] = (1.0 - dc) * cc + dc * cc_blur

        out = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)

    if ca_changed:
        out = apply_lateral_chromatic_aberration(
            out,
            red_scale=float(lateral_ca_red_scale),
            blue_scale=float(lateral_ca_blue_scale),
        )

    if s > 0.0:
        radius = max(0.1, float(sharpen_radius))
        smooth = cv2.GaussianBlur(out, (0, 0), sigmaX=radius, sigmaY=radius, borderType=cv2.BORDER_REFLECT)
        detail = out - smooth
        out = out + s * detail

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_lateral_chromatic_aberration(
    image_linear_rgb: np.ndarray,
    *,
    red_scale: float = 1.0,
    blue_scale: float = 1.0,
) -> np.ndarray:
    """Apply a simple radial red/blue scale correction around the image centre."""
    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0).copy()
    if out.ndim != 3 or out.shape[2] < 3:
        return out

    if abs(float(red_scale) - 1.0) > 1e-5:
        out[..., 0] = _scale_channel_radially(out[..., 0], float(red_scale))
    if abs(float(blue_scale) - 1.0) > 1e-5:
        out[..., 2] = _scale_channel_radially(out[..., 2], float(blue_scale))
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_render_adjustments(
    image_linear_rgb: np.ndarray,
    *,
    temperature_kelvin: float = 5003.0,
    neutral_kelvin: float = 5003.0,
    tint: float = 0.0,
    brightness_ev: float = 0.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
    contrast: float = 0.0,
    highlights: float = 0.0,
    shadows: float = 0.0,
    whites: float = 0.0,
    blacks: float = 0.0,
    midtone: float = 1.0,
    vibrance: float = 0.0,
    saturation: float = 0.0,
    grade_shadows_hue: float = 240.0,
    grade_shadows_saturation: float = 0.0,
    grade_midtones_hue: float = 45.0,
    grade_midtones_saturation: float = 0.0,
    grade_highlights_hue: float = 50.0,
    grade_highlights_saturation: float = 0.0,
    grade_blending: float = 0.5,
    grade_balance: float = 0.0,
    tone_curve_points: list[tuple[float, float]] | None = None,
    tone_curve_channel_points: dict[str, list[tuple[float, float]]] | None = None,
    tone_curve_black_point: float = 0.0,
    tone_curve_white_point: float = 1.0,
) -> np.ndarray:
    img = image_linear_rgb.astype(np.float32, copy=False)
    temp = float(temperature_kelvin)
    neutral = float(neutral_kelvin)
    tint_value = float(tint)
    brightness = float(brightness_ev)
    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))
    c = float(np.clip(contrast, -0.95, 2.0))
    hi = float(np.clip(highlights, -1.0, 1.0))
    sh = float(np.clip(shadows, -1.0, 1.0))
    wh = float(np.clip(whites, -1.0, 1.0))
    bl = float(np.clip(blacks, -1.0, 1.0))
    m = float(np.clip(midtone, 0.25, 4.0))
    vib = float(np.clip(vibrance, -1.0, 1.0))
    sat = float(np.clip(saturation, -1.0, 1.0))
    grade_values = (
        float(grade_shadows_saturation),
        float(grade_midtones_saturation),
        float(grade_highlights_saturation),
    )
    channel_curves = _normalize_channel_tone_curves(tone_curve_channel_points)
    tone_enabled = bool(tone_curve_points) or bool(channel_curves)
    temperature_identity = abs(temp - neutral) <= 1e-6 and abs(tint_value) <= 1e-6
    grade_enabled = any(abs(v) > 1e-6 for v in grade_values)

    if (
        temperature_identity
        and abs(brightness) <= 1e-6
        and bp <= 1e-6
        and abs(wp - 1.0) <= 1e-6
        and abs(c) <= 1e-6
        and abs(hi) <= 1e-6
        and abs(sh) <= 1e-6
        and abs(wh) <= 1e-6
        and abs(bl) <= 1e-6
        and abs(m - 1.0) <= 1e-6
        and abs(vib) <= 1e-6
        and abs(sat) <= 1e-6
        and not grade_enabled
        and not tone_enabled
    ):
        return np.clip(img, 0.0, 1.0).astype(np.float32, copy=False)

    out = np.array(img, dtype=np.float32, copy=True)
    np.clip(out, 0.0, 1.0, out=out)

    affine_multiplier = np.ones((3,), dtype=np.float32)
    affine_offset = np.float32(0.0)
    affine_enabled = False
    if not temperature_identity:
        affine_multiplier *= temperature_tint_multipliers(
            temperature_kelvin=temp,
            neutral_kelvin=neutral,
            tint=tint_value,
        )
        affine_enabled = True

    if abs(brightness) > 1e-6:
        affine_multiplier *= np.float32(2.0 ** brightness)
        affine_enabled = True

    if bp > 0.0 or wp < 1.0:
        scale = np.float32(1.0 / max(1e-4, wp - bp))
        affine_multiplier *= scale
        affine_offset = (affine_offset - np.float32(bp)) * scale
        affine_enabled = True

    if abs(c) > 1e-6:
        factor = np.float32(1.0 + c)
        affine_multiplier *= factor
        affine_offset = affine_offset * factor + np.float32(0.5 - 0.5 * factor)
        affine_enabled = True

    if affine_enabled:
        out *= affine_multiplier.reshape((1, 1, 3))
        if abs(float(affine_offset)) > 1e-8:
            out += affine_offset

    if any(abs(v) > 1e-6 for v in (hi, sh, wh, bl)):
        out = _apply_tonal_region_adjustments(out, highlights=hi, shadows=sh, whites=wh, blacks=bl)

    if abs(m - 1.0) > 1e-6:
        gamma = 1.0 / m
        np.clip(out, 0.0, 1.0, out=out)
        np.power(out, np.float32(gamma), out=out)

    if abs(vib) > 1e-6 or abs(sat) > 1e-6:
        out = _apply_vibrance_saturation(out, vibrance=vib, saturation=sat)

    if grade_enabled:
        out = _apply_color_grading(
            out,
            shadows_hue=grade_shadows_hue,
            shadows_saturation=grade_shadows_saturation,
            midtones_hue=grade_midtones_hue,
            midtones_saturation=grade_midtones_saturation,
            highlights_hue=grade_highlights_hue,
            highlights_saturation=grade_highlights_saturation,
            blending=grade_blending,
            balance=grade_balance,
        )

    if tone_enabled:
        if tone_curve_points:
            out = apply_tone_curve(
                out,
                tone_curve_points,
                black_point=tone_curve_black_point,
                white_point=tone_curve_white_point,
            )
        if channel_curves:
            out = apply_channel_tone_curves(
                out,
                channel_curves,
                black_point=tone_curve_black_point,
                white_point=tone_curve_white_point,
            )

    np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)


def render_adjustments_affine_u8(
    image_linear_rgb: np.ndarray,
    **kwargs,
) -> np.ndarray | None:
    if not _render_adjustments_are_affine_only(kwargs):
        return None
    img = np.asarray(image_linear_rgb, dtype=np.float32)
    if img.ndim != 3 or img.shape[2] < 3:
        return None

    temp = float(kwargs.get("temperature_kelvin", 5003.0))
    neutral = float(kwargs.get("neutral_kelvin", 5003.0))
    tint_value = float(kwargs.get("tint", 0.0))
    brightness = float(kwargs.get("brightness_ev", 0.0))
    bp = float(np.clip(kwargs.get("black_point", 0.0), 0.0, 0.95))
    wp = float(np.clip(kwargs.get("white_point", 1.0), bp + 1e-4, 1.0))
    contrast = float(np.clip(kwargs.get("contrast", 0.0), -0.95, 2.0))

    multiplier = np.ones((3,), dtype=np.float32)
    offset = np.float32(0.0)
    if abs(temp - neutral) > 1e-6 or abs(tint_value) > 1e-6:
        multiplier *= temperature_tint_multipliers(
            temperature_kelvin=temp,
            neutral_kelvin=neutral,
            tint=tint_value,
        )
    if abs(brightness) > 1e-6:
        multiplier *= np.float32(2.0 ** brightness)
    if bp > 0.0 or wp < 1.0:
        scale = np.float32(1.0 / max(1e-4, wp - bp))
        multiplier *= scale
        offset = (offset - np.float32(bp)) * scale
    if abs(contrast) > 1e-6:
        factor = np.float32(1.0 + contrast)
        multiplier *= factor
        offset = offset * factor + np.float32(0.5 - 0.5 * factor)

    out = np.empty(img.shape[:2] + (3,), dtype=np.float32)
    np.clip(img[..., :3], 0.0, 1.0, out=out)
    out *= multiplier.reshape((1, 1, 3))
    if abs(float(offset)) > 1e-8:
        out += offset
    np.clip(out, 0.0, 1.0, out=out)
    out *= np.float32(255.0)
    np.rint(out, out=out)
    return np.ascontiguousarray(out.astype(np.uint8, copy=False))


def _render_adjustments_are_affine_only(kwargs: dict[str, object]) -> bool:
    for name in ("highlights", "shadows", "whites", "blacks", "vibrance", "saturation"):
        if abs(float(kwargs.get(name, 0.0))) > 1e-6:
            return False
    if abs(float(kwargs.get("midtone", 1.0)) - 1.0) > 1e-6:
        return False
    for name in ("grade_shadows_saturation", "grade_midtones_saturation", "grade_highlights_saturation"):
        if abs(float(kwargs.get(name, 0.0))) > 1e-6:
            return False
    if kwargs.get("tone_curve_points"):
        return False
    if kwargs.get("tone_curve_channel_points"):
        return False
    return True


def _linear_luminance(image: np.ndarray) -> np.ndarray:
    rgb = np.asarray(image, dtype=np.float32)[..., :3]
    return np.clip(
        rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722,
        0.0,
        1.0,
    ).astype(np.float32)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - float(edge0)) / max(1e-6, float(edge1) - float(edge0)), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _apply_signed_region_lift(image: np.ndarray, amount: float, mask: np.ndarray, *, scale: float) -> np.ndarray:
    value = float(amount)
    if abs(value) <= 1e-6:
        return image
    m = mask.astype(np.float32, copy=False)
    if not m.flags.writeable:
        m = m.copy()
    m *= np.float32(value * float(scale))
    if value > 0.0:
        image *= (np.float32(1.0) - m[..., None])
        image += m[..., None]
    else:
        image *= (np.float32(1.0) + m[..., None])
    return image


def _apply_tonal_region_adjustments(
    image: np.ndarray,
    *,
    highlights: float,
    shadows: float,
    whites: float,
    blacks: float,
) -> np.ndarray:
    active = {
        "shadows": abs(float(shadows)) > 1e-6,
        "highlights": abs(float(highlights)) > 1e-6,
        "blacks": abs(float(blacks)) > 1e-6,
        "whites": abs(float(whites)) > 1e-6,
    }
    if not any(active.values()):
        return np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0).astype(np.float32, copy=False)
    out = np.asarray(image, dtype=np.float32)
    if not out.flags.writeable:
        out = out.copy()
    np.clip(out, 0.0, 1.0, out=out)
    y = _linear_luminance(out)
    if active["shadows"]:
        shadow_mask = (1.0 - _smoothstep(0.05, 0.55, y)) ** 1.25
        out = _apply_signed_region_lift(out, shadows, shadow_mask, scale=0.65)
    if active["highlights"]:
        highlight_mask = _smoothstep(0.45, 0.95, y) ** 1.25
        out = _apply_signed_region_lift(out, highlights, highlight_mask, scale=0.55)
    if active["blacks"]:
        black_mask = 1.0 - _smoothstep(0.0, 0.32, y)
        out = _apply_signed_region_lift(out, blacks, black_mask, scale=0.75)
    if active["whites"]:
        white_mask = _smoothstep(0.68, 1.0, y)
        out = _apply_signed_region_lift(out, whites, white_mask, scale=0.75)
    np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)


def _apply_vibrance_saturation(image: np.ndarray, *, vibrance: float, saturation: float) -> np.ndarray:
    out = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    y = _linear_luminance(out)
    chroma = np.max(out, axis=2) - np.min(out, axis=2)
    np.multiply(chroma, -float(vibrance), out=chroma)
    chroma += np.float32(1.0 + float(vibrance))
    np.clip(chroma, 0.0, 2.5, out=chroma)
    chroma *= np.float32(max(0.0, 1.0 + float(saturation)))
    y_view = y[..., np.newaxis]
    out -= y_view
    out *= chroma[..., np.newaxis]
    out += y_view
    np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)


def _hue_color(hue_degrees: float) -> np.ndarray:
    hue = (float(hue_degrees) % 360.0) / 60.0
    x = 1.0 - abs((hue % 2.0) - 1.0)
    if hue < 1.0:
        rgb = (1.0, x, 0.0)
    elif hue < 2.0:
        rgb = (x, 1.0, 0.0)
    elif hue < 3.0:
        rgb = (0.0, 1.0, x)
    elif hue < 4.0:
        rgb = (0.0, x, 1.0)
    elif hue < 5.0:
        rgb = (x, 0.0, 1.0)
    else:
        rgb = (1.0, 0.0, x)
    color = np.asarray(rgb, dtype=np.float32)
    return color / max(1e-6, float(np.mean(color)))


def _apply_color_grading(
    image: np.ndarray,
    *,
    shadows_hue: float,
    shadows_saturation: float,
    midtones_hue: float,
    midtones_saturation: float,
    highlights_hue: float,
    highlights_saturation: float,
    blending: float,
    balance: float,
) -> np.ndarray:
    out = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    y = _linear_luminance(out)
    blend = float(np.clip(blending, 0.0, 1.0))
    bal = float(np.clip(balance, -1.0, 1.0))
    shadow_end = 0.42 + bal * 0.18
    highlight_start = 0.58 + bal * 0.18
    softness = 0.08 + blend * 0.28
    shadow_w = 1.0 - _smoothstep(shadow_end - softness, shadow_end + softness, y)
    highlight_w = _smoothstep(highlight_start - softness, highlight_start + softness, y)
    mid_w = np.clip(1.0 - np.maximum(shadow_w, highlight_w), 0.0, 1.0)
    weights = (
        (shadow_w, shadows_hue, shadows_saturation),
        (mid_w, midtones_hue, midtones_saturation),
        (highlight_w, highlights_hue, highlights_saturation),
    )
    for weight, hue, sat in weights:
        amount = float(np.clip(sat, -1.0, 1.0))
        if abs(amount) <= 1e-6:
            continue
        color = _hue_color(hue).reshape((1, 1, 3))
        if amount > 0.0:
            target = out * color
            out = out * (1.0 - weight[..., None] * amount) + target * (weight[..., None] * amount)
        else:
            gray = _linear_luminance(out)[..., None]
            out = out * (1.0 + weight[..., None] * amount) + gray * (-amount * weight[..., None])
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def normalize_tone_curve_points(points: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for point in points:
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not np.isfinite(x) or not np.isfinite(y):
            continue
        normalized.append((float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))))

    normalized.extend([(0.0, 0.0), (1.0, 1.0)])
    normalized.sort(key=lambda p: (p[0], p[1]))

    deduped: list[tuple[float, float]] = []
    for x, y in normalized:
        if deduped and abs(x - deduped[-1][0]) < 1e-4:
            deduped[-1] = (x, y)
        else:
            deduped.append((x, y))
    deduped[0] = (0.0, 0.0)
    deduped[-1] = (1.0, 1.0)

    monotonic: list[tuple[float, float]] = []
    previous_y = 0.0
    for idx, (x, y) in enumerate(deduped):
        if idx == 0:
            y = 0.0
        elif idx == len(deduped) - 1:
            y = 1.0
        else:
            y = float(np.clip(max(y, previous_y), 0.0, 1.0))
        monotonic.append((x, y))
        previous_y = y
    return monotonic


def tone_curve_lut(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    lut_size: int = 4096,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    curve = normalize_tone_curve_points(points)
    curve_key = tuple((float(x), float(y)) for x, y in curve)
    lut_size = int(np.clip(lut_size, 256, 65536))
    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))
    return _tone_curve_lut_cached(curve_key, lut_size, bp, wp)


@lru_cache(maxsize=512)
def _tone_curve_lut_cached(
    curve_key: tuple[tuple[float, float], ...],
    lut_size: int,
    black_point: float,
    white_point: float,
) -> tuple[np.ndarray, np.ndarray]:
    curve = list(curve_key)
    xs = np.asarray([p[0] for p in curve], dtype=np.float32)
    ys = np.asarray([p[1] for p in curve], dtype=np.float32)
    lut_size = int(np.clip(lut_size, 256, 65536))

    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))
    lut_x = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)
    curve_x = np.clip((lut_x - bp) / max(1e-4, wp - bp), 0.0, 1.0).astype(np.float32)
    lut_y = _monotone_cubic_interpolate(xs, ys, curve_x)
    lut_y = np.maximum.accumulate(np.clip(lut_y, 0.0, 1.0)).astype(np.float32)
    lut_y[-1] = 1.0
    lut_x.setflags(write=False)
    lut_y.setflags(write=False)
    return lut_x, lut_y


def apply_tone_curve(
    image_linear_rgb: np.ndarray,
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    lut_size: int = 4096,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> np.ndarray:
    curve = normalize_tone_curve_points(points)
    xs = np.asarray([p[0] for p in curve], dtype=np.float32)
    ys = np.asarray([p[1] for p in curve], dtype=np.float32)
    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))

    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)
    if (
        len(curve) <= 2
        and np.allclose(xs, [0.0, 1.0], atol=1e-6)
        and np.allclose(ys, [0.0, 1.0], atol=1e-6)
        and abs(bp) <= 1e-6
        and abs(wp - 1.0) <= 1e-6
    ):
        return out.astype(np.float32)

    # Apply the curve to scene luminance and scale RGB by the luminance ratio.
    # This keeps the operation deterministic while reducing hue shifts versus
    # applying an arbitrary display curve independently to each channel.
    luminance = (
        out[..., 0] * np.float32(0.2126)
        + out[..., 1] * np.float32(0.7152)
        + out[..., 2] * np.float32(0.0722)
    )
    np.clip(luminance, 0.0, 1.0, out=luminance)
    _lut_x, lut_y = tone_curve_lut(
        curve,
        lut_size=lut_size,
        black_point=bp,
        white_point=wp,
    )
    lut_size = int(lut_y.size)
    indices = np.clip(np.rint(luminance * (lut_size - 1)), 0, lut_size - 1).astype(np.int32)
    curved_luminance = lut_y[indices]

    mask = luminance > 1e-6
    luminance[mask] = curved_luminance[mask] / luminance[mask]
    luminance[~mask] = np.float32(1.0)
    out[..., :3] *= luminance[..., None]
    np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)


def apply_channel_tone_curves(
    image_linear_rgb: np.ndarray,
    channel_points: dict[str, list[tuple[float, float]]] | None,
    *,
    lut_size: int = 4096,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> np.ndarray:
    curves = _normalize_channel_tone_curves(channel_points)
    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)
    if not curves:
        return out.astype(np.float32)

    adjusted = out.copy()
    channel_indices = {"red": 0, "green": 1, "blue": 2}
    for channel, points in curves.items():
        index = channel_indices.get(channel)
        if index is None:
            continue
        if _tone_curve_is_identity(points, black_point=black_point, white_point=white_point):
            continue
        _lut_x, lut_y = tone_curve_lut(
            points,
            lut_size=lut_size,
            black_point=black_point,
            white_point=white_point,
        )
        lut_size_actual = int(lut_y.size)
        values = np.clip(adjusted[..., index], 0.0, 1.0)
        indices = np.clip(np.rint(values * (lut_size_actual - 1)), 0, lut_size_actual - 1).astype(np.int32)
        adjusted[..., index] = lut_y[indices]
    return np.clip(adjusted, 0.0, 1.0).astype(np.float32)


def _normalize_channel_tone_curves(
    channel_points: dict[str, list[tuple[float, float]]] | None,
) -> dict[str, list[tuple[float, float]]]:
    if not isinstance(channel_points, dict):
        return {}
    out: dict[str, list[tuple[float, float]]] = {}
    for channel in ("red", "green", "blue"):
        points = channel_points.get(channel)
        if not isinstance(points, (list, tuple)):
            continue
        normalized = normalize_tone_curve_points(points)
        if not _tone_curve_is_identity(normalized):
            out[channel] = normalized
    return out


def _tone_curve_is_identity(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> bool:
    curve = normalize_tone_curve_points(points)
    xs = np.asarray([p[0] for p in curve], dtype=np.float32)
    ys = np.asarray([p[1] for p in curve], dtype=np.float32)
    return (
        len(curve) <= 2
        and np.allclose(xs, [0.0, 1.0], atol=1e-6)
        and np.allclose(ys, [0.0, 1.0], atol=1e-6)
        and abs(float(black_point)) <= 1e-6
        and abs(float(white_point) - 1.0) <= 1e-6
    )


def _monotone_cubic_interpolate(x: np.ndarray, y: np.ndarray, x_new: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    x_new = np.asarray(x_new, dtype=np.float32)
    if x.size < 3:
        return np.interp(x_new, x, y).astype(np.float32)

    h = np.diff(x)
    if np.any(h <= 0.0):
        return np.interp(x_new, x, y).astype(np.float32)
    delta = np.diff(y) / h

    slopes = np.zeros_like(y, dtype=np.float32)
    slopes[0] = _pchip_endpoint_slope(h[0], h[1], delta[0], delta[1])
    slopes[-1] = _pchip_endpoint_slope(h[-1], h[-2], delta[-1], delta[-2])
    for idx in range(1, x.size - 1):
        left = float(delta[idx - 1])
        right = float(delta[idx])
        if left <= 0.0 or right <= 0.0:
            slopes[idx] = 0.0
        else:
            w1 = 2.0 * float(h[idx]) + float(h[idx - 1])
            w2 = float(h[idx]) + 2.0 * float(h[idx - 1])
            slopes[idx] = (w1 + w2) / ((w1 / left) + (w2 / right))

    interval = np.searchsorted(x, x_new, side="right") - 1
    interval = np.clip(interval, 0, x.size - 2)
    x0 = x[interval]
    x1 = x[interval + 1]
    y0 = y[interval]
    y1 = y[interval + 1]
    m0 = slopes[interval]
    m1 = slopes[interval + 1]
    width = np.maximum(x1 - x0, 1e-6)
    t = (x_new - x0) / width
    t2 = t * t
    t3 = t2 * t

    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    return (h00 * y0 + h10 * width * m0 + h01 * y1 + h11 * width * m1).astype(np.float32)


def _pchip_endpoint_slope(h0: float, h1: float, delta0: float, delta1: float) -> np.float32:
    d = ((2.0 * h0 + h1) * delta0 - h0 * delta1) / max(1e-6, h0 + h1)
    if d <= 0.0:
        return np.float32(0.0)
    if delta0 <= 0.0:
        return np.float32(0.0)
    if delta1 <= 0.0 and d > 3.0 * delta0:
        return np.float32(3.0 * delta0)
    return np.float32(d)


def _scale_channel_radially(channel: np.ndarray, scale: float) -> np.ndarray:
    if scale <= 0.0 or abs(scale - 1.0) <= 1e-5:
        return channel.astype(np.float32)

    h, w = channel.shape[:2]
    cache_key = (int(h), int(w), round(float(scale), 9))
    with _RADIAL_MAP_CACHE_LOCK:
        maps = _RADIAL_MAP_CACHE.get(cache_key)
        if maps is None:
            y, x = np.indices((h, w), dtype=np.float32)
            cx = (w - 1) / 2.0
            cy = (h - 1) / 2.0
            map_x = ((x - cx) / scale + cx).astype(np.float32)
            map_y = ((y - cy) / scale + cy).astype(np.float32)
            map_x.setflags(write=False)
            map_y.setflags(write=False)
            while len(_RADIAL_MAP_CACHE) >= _RADIAL_MAP_CACHE_MAX:
                _RADIAL_MAP_CACHE.pop(next(iter(_RADIAL_MAP_CACHE)))
            _RADIAL_MAP_CACHE[cache_key] = (map_x, map_y)
            maps = (map_x, map_y)
    return cv2.remap(
        channel.astype(np.float32),
        maps[0],
        maps[1],
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def _apply_temperature_tint(
    image_linear_rgb: np.ndarray,
    *,
    temperature_kelvin: float,
    neutral_kelvin: float,
    tint: float,
) -> np.ndarray:
    multipliers = temperature_tint_multipliers(
        temperature_kelvin=temperature_kelvin,
        neutral_kelvin=neutral_kelvin,
        tint=tint,
    )
    return image_linear_rgb * multipliers.reshape((1, 1, 3))


def temperature_tint_multipliers(
    *,
    temperature_kelvin: float,
    neutral_kelvin: float = 5003.0,
    tint: float = 0.0,
) -> np.ndarray:
    temp = float(np.clip(temperature_kelvin, 2000.0, 12000.0))
    neutral = float(np.clip(neutral_kelvin, 2000.0, 12000.0))
    tint_n = float(np.clip(tint / 100.0, -1.0, 1.0))

    target_white = _cct_linear_srgb_white(temp)
    neutral_white = _cct_linear_srgb_white(neutral)
    multipliers = neutral_white / np.clip(target_white, 1e-4, None)
    multipliers = multipliers / max(float(multipliers[1]), 1e-4)

    tint_multipliers = np.array(
        [1.0 + 0.06 * tint_n, 1.0 - 0.12 * tint_n, 1.0 + 0.06 * tint_n],
        dtype=np.float32,
    )
    return np.clip(multipliers.astype(np.float32) * tint_multipliers, 0.35, 2.85)


@lru_cache(maxsize=256)
def _cct_linear_srgb_white(temperature_kelvin: float) -> np.ndarray:
    cct = float(np.clip(temperature_kelvin, 2000.0, 12000.0))
    xy = np.asarray(colour.temperature.CCT_to_xy_Kang2002(cct), dtype=np.float64)
    xyz = np.asarray(colour.xy_to_XYZ(xy), dtype=np.float64)
    rgb = np.asarray(
        colour.XYZ_to_RGB(
            xyz,
            "sRGB",
            illuminant=None,
            chromatic_adaptation_transform=None,
            apply_cctf_encoding=False,
        ),
        dtype=np.float64,
    )
    rgb = np.clip(rgb, 1e-4, None)
    return (rgb / max(float(rgb[1]), 1e-4)).astype(np.float32)


def estimate_temperature_tint_from_neutral_sample(
    sample_rgb: np.ndarray,
    *,
    neutral_kelvin: float = 5003.0,
) -> tuple[int, float]:
    """Estimate preview temperature/tint controls from a sampled neutral patch."""
    sample = np.asarray(sample_rgb, dtype=np.float64).reshape(-1)
    if sample.size < 3:
        raise ValueError("La muestra neutra no contiene canales RGB suficientes.")
    sample = sample[:3]
    if not np.all(np.isfinite(sample)) or float(np.max(sample)) <= 1e-6:
        raise ValueError("La muestra neutra no es valida.")

    sample = np.clip(sample, 1e-6, 1.0)
    if float(np.max(sample)) < 0.01:
        raise ValueError("La muestra neutra es demasiado oscura.")

    temp, tint = _best_temperature_tint_for_sample(
        sample,
        neutral_kelvin=neutral_kelvin,
        temp_values=np.arange(2000.0, 12000.1, 100.0),
        tint_values=np.arange(-100.0, 100.1, 2.0),
    )
    temp, tint = _best_temperature_tint_for_sample(
        sample,
        neutral_kelvin=neutral_kelvin,
        temp_values=np.arange(max(2000.0, temp - 160.0), min(12000.0, temp + 160.0) + 0.1, 10.0),
        tint_values=np.arange(max(-100.0, tint - 5.0), min(100.0, tint + 5.0) + 0.001, 0.2),
    )
    return int(round(temp)), float(round(tint, 1))


def _best_temperature_tint_for_sample(
    sample_rgb: np.ndarray,
    *,
    neutral_kelvin: float,
    temp_values: np.ndarray,
    tint_values: np.ndarray,
) -> tuple[float, float]:
    temps = np.asarray(temp_values, dtype=np.float64)
    tints = np.asarray(tint_values, dtype=np.float64)
    neutral = float(np.clip(neutral_kelvin, 2000.0, 12000.0))
    tint_n = np.clip(tints[None, :] / 100.0, -1.0, 1.0)

    neutral_white = _cct_linear_srgb_white(neutral).astype(np.float64)
    target_whites = np.asarray([_cct_linear_srgb_white(float(temp)) for temp in temps], dtype=np.float64)
    multipliers = neutral_white.reshape((1, 3)) / np.clip(target_whites, 1e-4, None)
    multipliers = multipliers / np.clip(multipliers[:, 1:2], 1e-4, None)
    tint_multipliers = np.stack(
        (
            1.0 + 0.06 * tint_n,
            1.0 - 0.12 * tint_n,
            1.0 + 0.06 * tint_n,
        ),
        axis=-1,
    )
    multipliers = np.clip(multipliers[:, None, :] * tint_multipliers, 0.35, 2.85)
    corrected = multipliers * sample_rgb.reshape((1, 1, 3))
    mean = np.mean(corrected, axis=-1, keepdims=True)
    log_chroma = np.log(np.clip(corrected / np.clip(mean, 1e-6, None), 1e-6, None))
    cost = np.mean(log_chroma * log_chroma, axis=-1)
    idx = np.unravel_index(int(np.argmin(cost)), cost.shape)
    return float(temps[idx[0]]), float(tints[idx[1]])


def apply_profile_preview(image_linear_rgb: np.ndarray, profile_path: Path) -> np.ndarray:
    if not profile_path.exists():
        raise FileNotFoundError(f"No existe el perfil ICC: {profile_path}")

    lut = _profile_preview_lut(profile_path, grid_size=17)
    return _apply_srgb_lut(image_linear_rgb, lut)


def _profile_preview_lut(profile_path: Path, *, grid_size: int) -> np.ndarray:
    key = (_profile_cache_key(profile_path), int(grid_size), _lcms_cache_key())
    cached = _PROFILE_PREVIEW_LUT_CACHE.get(key)
    if cached is not None:
        return cached

    lut = _build_profile_preview_lut_with_lcms(profile_path, grid_size=grid_size)
    _PROFILE_PREVIEW_LUT_CACHE[key] = lut
    if len(_PROFILE_PREVIEW_LUT_CACHE) > 8:
        oldest = next(iter(_PROFILE_PREVIEW_LUT_CACHE))
        _PROFILE_PREVIEW_LUT_CACHE.pop(oldest, None)
    return lut


def _profile_cache_key(profile_path: Path) -> str:
    try:
        resolved = profile_path.expanduser().resolve()
        st = resolved.stat()
        return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return str(profile_path)


def _lcms_cache_key() -> str:
    return f"lcms2|{getattr(ImageCms.core, 'littlecms_version', 'unknown')}"


def _build_profile_preview_lut_with_lcms(profile_path: Path, *, grid_size: int) -> np.ndarray:
    n = int(np.clip(grid_size, 3, 65))
    axis = np.linspace(0.0, 1.0, n, dtype=np.float64)
    rr, gg, bb = np.meshgrid(axis, axis, axis, indexing="ij")
    grid = np.stack([rr, gg, bb], axis=-1).reshape((-1, 3))

    try:
        source = ImageCms.getOpenProfile(str(profile_path))
        destination = ImageCms.createProfile("sRGB")
        transform = ImageCms.buildTransformFromOpenProfiles(
            source,
            destination,
            "RGB",
            "RGB",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo construir preview ICC con LittleCMS: {profile_path}") from exc

    grid_u8 = np.clip(np.round(grid * 255.0), 0, 255).astype(np.uint8, copy=False)
    image = Image.fromarray(grid_u8.reshape((n * n, n, 3)), "RGB")
    converted = ImageCms.applyTransform(image, transform)
    if converted is None:
        raise RuntimeError("LittleCMS no devolvio imagen para la LUT de preview ICC.")
    srgb = np.asarray(converted, dtype=np.float32).reshape((-1, 3)) / np.float32(255.0)
    return np.clip(srgb.reshape((n, n, n, 3)).astype(np.float32), 0.0, 1.0)


def _apply_srgb_lut(image_linear_rgb: np.ndarray, lut: np.ndarray) -> np.ndarray:
    image = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)
    if image.ndim != 3 or image.shape[2] < 3:
        raise RuntimeError(f"Imagen RGB inesperada para preview ICC: shape={image.shape}")

    n = int(lut.shape[0])
    coords = image[..., :3] * float(n - 1)
    lower = np.floor(coords).astype(np.int32)
    upper = np.clip(lower + 1, 0, n - 1)
    lower = np.clip(lower, 0, n - 1)
    frac = coords - lower.astype(np.float32)

    r0, g0, b0 = lower[..., 0], lower[..., 1], lower[..., 2]
    r1, g1, b1 = upper[..., 0], upper[..., 1], upper[..., 2]
    fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]

    c000 = lut[r0, g0, b0]
    c001 = lut[r0, g0, b1]
    c010 = lut[r0, g1, b0]
    c011 = lut[r0, g1, b1]
    c100 = lut[r1, g0, b0]
    c101 = lut[r1, g0, b1]
    c110 = lut[r1, g1, b0]
    c111 = lut[r1, g1, b1]

    c00 = c000 * (1.0 - fb) + c001 * fb
    c01 = c010 * (1.0 - fb) + c011 * fb
    c10 = c100 * (1.0 - fb) + c101 * fb
    c11 = c110 * (1.0 - fb) + c111 * fb
    c0 = c00 * (1.0 - fg) + c01 * fg
    c1 = c10 * (1.0 - fg) + c11 * fg
    return np.clip(c0 * (1.0 - fr) + c1 * fr, 0.0, 1.0).astype(np.float32)


def linear_to_srgb_display(image_linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)
    a = 0.055
    srgb = np.empty_like(x, dtype=np.float32)
    np.power(x, 1.0 / 2.4, out=srgb)
    srgb *= 1.0 + a
    srgb -= a
    low = x <= 0.0031308
    if np.any(low):
        srgb[low] = 12.92 * x[low]
    return np.clip(srgb, 0.0, 1.0, out=srgb)


def _float_rgb_to_u8(image_rgb: np.ndarray) -> np.ndarray:
    out = np.clip(np.asarray(image_rgb, dtype=np.float32), 0.0, 1.0)
    out = out * np.float32(255.0)
    np.rint(out, out=out)
    return np.ascontiguousarray(out.astype(np.uint8, copy=False))


def linear_to_srgb_display_u8(image_linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)
    a = np.float32(0.055)
    srgb = np.empty_like(x, dtype=np.float32)
    np.power(x, np.float32(1.0 / 2.4), out=srgb)
    srgb *= np.float32(1.0 + a)
    srgb -= a
    low = x <= np.float32(0.0031308)
    if np.any(low):
        srgb[low] = np.float32(12.92) * x[low]
    np.clip(srgb, 0.0, 1.0, out=srgb)
    srgb *= np.float32(255.0)
    np.rint(srgb, out=srgb)
    return np.ascontiguousarray(srgb.astype(np.uint8, copy=False))


def standard_profile_to_srgb_display(image_rgb: np.ndarray, output_space: str) -> np.ndarray:
    """Convert encoded standard RGB preview data to encoded sRGB for display."""
    if not is_generic_output_space(output_space):
        return linear_to_srgb_display(image_rgb)
    profile = generic_output_profile(output_space)
    encoded = np.clip(np.asarray(image_rgb, dtype=np.float32), 0.0, 1.0)
    if profile.key == "srgb":
        return encoded.astype(np.float32, copy=False)

    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    decoder = getattr(rgb_space, "cctf_decoding", None)
    if callable(decoder):
        linear = np.asarray(decoder(encoded), dtype=np.float32)
    else:
        linear = np.power(encoded, float(profile.gamma)).astype(np.float32)

    flat = linear.reshape((-1, 3))
    transform = _standard_rgb_to_srgb_linear_transform(profile.key, profile.colour_space)
    srgb_linear = flat @ transform
    srgb_linear = srgb_linear.reshape(encoded.shape)
    return linear_to_srgb_display(srgb_linear)


def standard_profile_to_srgb_u8_display(image_rgb: np.ndarray, output_space: str) -> np.ndarray:
    """Convert standard RGB preview data to the exact 8-bit sRGB display buffer."""
    if not is_generic_output_space(output_space):
        return linear_to_srgb_display_u8(image_rgb)
    profile = generic_output_profile(output_space)
    encoded = np.clip(np.asarray(image_rgb, dtype=np.float32), 0.0, 1.0)
    if profile.key == "srgb":
        return _float_rgb_to_u8(encoded)

    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    decoder = getattr(rgb_space, "cctf_decoding", None)
    if callable(decoder):
        linear = np.asarray(decoder(encoded), dtype=np.float32)
    else:
        linear = np.power(encoded, float(profile.gamma)).astype(np.float32)

    flat = linear.reshape((-1, 3))
    transform = _standard_rgb_to_srgb_linear_transform(profile.key, profile.colour_space)
    srgb_linear = flat @ transform
    srgb_linear = srgb_linear.reshape(encoded.shape)
    return linear_to_srgb_display_u8(srgb_linear)


def _standard_rgb_to_srgb_linear_transform(profile_key: str, colour_space_name: str) -> np.ndarray:
    key = f"{profile_key}|{colour_space_name}"
    cached = _STANDARD_TO_SRGB_MATRIX_CACHE.get(key)
    if cached is not None:
        return cached

    rgb_space = colour.RGB_COLOURSPACES[colour_space_name]
    source_white = np.asarray(colour.xy_to_XYZ(rgb_space.whitepoint), dtype=np.float32)
    d65_xy = np.asarray(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"], dtype=np.float64)
    d65_xyz = np.asarray(colour.xy_to_XYZ(d65_xy), dtype=np.float32)
    if np.allclose(source_white, d65_xyz, atol=1e-6):
        adaptation = np.eye(3, dtype=np.float32)
    else:
        adaptation = matrix_chromatic_adaptation_VonKries(source_white, d65_xyz, transform="Bradford")
        adaptation = np.asarray(adaptation, dtype=np.float32)

    source_to_xyz = np.asarray(rgb_space.matrix_RGB_to_XYZ, dtype=np.float32)
    srgb_space = colour.RGB_COLOURSPACES["sRGB"]
    xyz_to_srgb = np.asarray(srgb_space.matrix_XYZ_to_RGB, dtype=np.float32)
    transform = (source_to_xyz.T @ adaptation.T @ xyz_to_srgb.T).astype(np.float32)
    _STANDARD_TO_SRGB_MATRIX_CACHE[key] = transform
    return transform


def srgb_to_linear_display(image_srgb: np.ndarray) -> np.ndarray:
    x = np.clip(image_srgb.astype(np.float32), 0.0, 1.0)
    linear = np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))
    return np.clip(linear, 0.0, 1.0)


def preview_analysis_text(
    original_linear: np.ndarray,
    adjusted_linear: np.ndarray,
    *,
    max_pixels: int = 250_000,
) -> str:
    o = _analysis_sample_float(original_linear, max_pixels=max_pixels)
    a = _analysis_sample_float(adjusted_linear, max_pixels=max_pixels)

    lines: list[str] = []
    lines.append("Diagnóstico de imagen (preview lineal 0..1)")
    lines.append("")
    lines.extend(_exposure_stats("Resultado ajustado", a))
    lines.append("")
    lines.extend(_recipe_impact_stats(o, a))
    lines.append("")
    lines.extend(_channel_stats("Canales ajustados", a))
    lines.append("")
    lines.extend(_channel_stats("Canales originales", o))
    return "\n".join(lines)


def _analysis_sample(image: np.ndarray, *, max_pixels: int) -> np.ndarray:
    if max_pixels <= 0 or image.ndim < 2:
        return image
    h, w = int(image.shape[0]), int(image.shape[1])
    pixels = h * w
    if pixels <= int(max_pixels):
        return image
    step = max(1, int(np.ceil(np.sqrt(pixels / float(max_pixels)))))
    return image[::step, ::step]


def _analysis_sample_float(image: np.ndarray, *, max_pixels: int) -> np.ndarray:
    # Sample before dtype conversion/clipping to avoid full-frame copies in the GUI.
    sampled = _analysis_sample(np.asarray(image), max_pixels=max_pixels)
    sampled = sampled.astype(np.float32, copy=False)
    return np.clip(sampled, 0.0, 1.0)


def _channel_stats(label: str, image: np.ndarray) -> list[str]:
    ch_names = ("R", "G", "B")
    lines = [f"{label}:"]
    for idx, ch_name in enumerate(ch_names):
        ch = image[..., idx]
        lines.append(
            (
                f"  {ch_name}: media={float(np.mean(ch)):.6f} "
                f"std={float(np.std(ch)):.6f} "
                f"min={float(np.min(ch)):.6f} "
                f"max={float(np.max(ch)):.6f} "
                f"clip_low={float(np.mean(ch <= 0.001)) * 100.0:.3f}% "
                f"clip_hi={float(np.mean(ch >= 0.999)) * 100.0:.3f}%"
            )
        )
    return lines


def _exposure_stats(label: str, image: np.ndarray) -> list[str]:
    luminance = _analysis_luminance(image)
    p01, p50, p99 = np.percentile(luminance, [1, 50, 99])
    mean_rgb = np.mean(image[..., :3], axis=(0, 1))
    green = max(float(mean_rgb[1]), 1e-6)
    return [
        f"{label}:",
        (
            f"  Luminancia: media={float(np.mean(luminance)):.6f} "
            f"p01={float(p01):.6f} p50={float(p50):.6f} p99={float(p99):.6f}"
        ),
        (
            f"  Clipping global: sombras={float(np.mean(luminance <= 0.001)) * 100.0:.3f}% "
            f"luces={float(np.mean(luminance >= 0.999)) * 100.0:.3f}%"
        ),
        (
            f"  Balance RGB medio: R/G={float(mean_rgb[0]) / green:.3f} "
            f"B/G={float(mean_rgb[2]) / green:.3f}"
        ),
    ]


def _recipe_impact_stats(original: np.ndarray, adjusted: np.ndarray) -> list[str]:
    diff = np.abs(adjusted - original)
    original_luma = _analysis_luminance(original)
    adjusted_luma = _analysis_luminance(adjusted)
    return [
        "Impacto de la receta:",
        f"  Diferencia media absoluta global: {float(np.mean(diff)):.6f}",
        f"  Diferencia máxima absoluta global: {float(np.max(diff)):.6f}",
        (
            "  Desplazamiento de luminancia media: "
            f"{float(np.mean(adjusted_luma) - np.mean(original_luma)):+.6f}"
        ),
    ]


def _analysis_luminance(image: np.ndarray) -> np.ndarray:
    weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return np.sum(image[..., :3] * weights.reshape((1, 1, 3)), axis=2)
