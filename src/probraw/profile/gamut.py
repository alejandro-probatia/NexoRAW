from __future__ import annotations

from pathlib import Path
from typing import Any

import colour
from colour.adaptation import matrix_chromatic_adaptation_VonKries
import numpy as np
from scipy.spatial import Delaunay, QhullError

from .builder import D50_XY, D50_XYZ, _lookup_lab_with_icc
from .generic import GENERIC_RGB_PROFILES


GAMUT_GRID_SIZE = 11
STANDARD_GAMUT_KEYS = ("srgb", "adobe_rgb", "prophoto_rgb")
STANDARD_GAMUT_COLORS = {
    "srgb": "#f97316",
    "adobe_rgb": "#22c55e",
    "prophoto_rgb": "#a855f7",
}
GENERATED_GAMUT_COLOR = "#f8fafc"
MONITOR_GAMUT_COLOR = "#60a5fa"

_GAMUT_CACHE: dict[tuple[str, str, int], dict[str, Any]] = {}


def build_gamut_pair_diagnostics(
    *,
    profile_a: dict[str, Any] | None,
    profile_b: dict[str, Any] | None,
    grid_size: int = GAMUT_GRID_SIZE,
) -> dict[str, Any]:
    n = int(np.clip(grid_size, 5, 21))
    series: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for role, spec in (("wire", profile_a), ("solid", profile_b)):
        if not isinstance(spec, dict):
            skipped.append({"role": role, "label": "sin perfil", "reason": "perfil_no_configurado"})
            continue
        try:
            item = build_gamut_series_from_spec(spec, grid_size=n)
            item = dict(item)
            item["role"] = role
            series.append(item)
        except Exception as exc:
            skipped.append(
                {
                    "role": role,
                    "label": str(spec.get("label") or spec.get("key") or spec.get("path") or "?"),
                    "reason": str(exc),
                }
            )

    comparisons = _pair_containment_comparisons(series)
    return {
        "series": series,
        "comparisons": comparisons,
        "skipped": skipped,
        "grid_size": n,
        "comparison_basis": "superficie RGB de perfil A/B muestreada en Lab D50",
    }


def build_gamut_diagnostics(
    *,
    generated_profile: Path | None,
    monitor_profile: Path | None,
    grid_size: int = GAMUT_GRID_SIZE,
) -> dict[str, Any]:
    n = int(np.clip(grid_size, 5, 21))
    series: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    generated_series: dict[str, Any] | None = None

    if generated_profile is not None:
        path = Path(generated_profile).expanduser()
        if path.exists():
            try:
                generated_series = build_icc_gamut_series(
                    label="ICC generado",
                    profile_path=path,
                    color=GENERATED_GAMUT_COLOR,
                    grid_size=n,
                )
                series.append(generated_series)
            except Exception as exc:
                skipped.append({"label": "ICC generado", "path": str(path), "reason": str(exc)})

    for key in STANDARD_GAMUT_KEYS:
        try:
            series.append(build_standard_gamut_series(key, grid_size=n))
        except Exception as exc:
            skipped.append({"label": key, "reason": str(exc)})

    if monitor_profile is not None:
        path = Path(monitor_profile).expanduser()
        if path.exists():
            try:
                series.append(
                    build_icc_gamut_series(
                        label="Monitor",
                        profile_path=path,
                        color=MONITOR_GAMUT_COLOR,
                        grid_size=n,
                    )
                )
            except Exception as exc:
                skipped.append({"label": "Monitor", "path": str(path), "reason": str(exc)})

    comparisons = (
        _standard_containment_comparisons(generated_series["points_lab"])
        if generated_series is not None
        else []
    )
    return {
        "series": series,
        "comparisons": comparisons,
        "skipped": skipped,
        "grid_size": n,
        "comparison_basis": "superficie RGB del ICC generado muestreada en Lab D50",
    }


def build_gamut_series_from_spec(spec: dict[str, Any], *, grid_size: int) -> dict[str, Any]:
    kind = str(spec.get("kind") or "").strip().lower()
    if kind == "standard":
        return build_standard_gamut_series(str(spec.get("key") or ""), grid_size=grid_size)
    if kind == "icc":
        path = Path(str(spec.get("path") or "")).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"No existe perfil ICC: {path}")
        return build_icc_gamut_series(
            label=str(spec.get("label") or path.name),
            profile_path=path,
            color=str(spec.get("color") or "#f8fafc"),
            grid_size=grid_size,
        )
    raise RuntimeError(f"Tipo de perfil gamut no soportado: {kind or '<vacio>'}")


def evaluate_lab_gamut_membership(
    lab_points: np.ndarray,
    *,
    profile_a: dict[str, Any] | None,
    profile_b: dict[str, Any] | None,
    grid_size: int = GAMUT_GRID_SIZE,
) -> dict[str, Any]:
    points = _finite_lab_points(np.asarray(lab_points, dtype=np.float64))
    if points.size == 0:
        return {
            "points_lab": points,
            "inside_a": np.zeros(0, dtype=bool),
            "inside_b": np.zeros(0, dtype=bool),
            "inside_common": np.zeros(0, dtype=bool),
            "label_a": "sin perfil",
            "label_b": "sin perfil",
            "method_a": "",
            "method_b": "",
        }
    series_a = build_gamut_series_from_spec(profile_a, grid_size=grid_size) if isinstance(profile_a, dict) else None
    series_b = build_gamut_series_from_spec(profile_b, grid_size=grid_size) if isinstance(profile_b, dict) else None
    inside_a, method_a = (
        _lab_inside_profile(points, series_a)
        if isinstance(series_a, dict)
        else (np.zeros(points.shape[0], dtype=bool), "")
    )
    inside_b, method_b = (
        _lab_inside_profile(points, series_b)
        if isinstance(series_b, dict)
        else (np.zeros(points.shape[0], dtype=bool), "")
    )
    return {
        "points_lab": points,
        "inside_a": inside_a,
        "inside_b": inside_b,
        "inside_common": np.logical_and(inside_a, inside_b),
        "label_a": str(series_a.get("label") if isinstance(series_a, dict) else "sin perfil"),
        "label_b": str(series_b.get("label") if isinstance(series_b, dict) else "sin perfil"),
        "method_a": method_a,
        "method_b": method_b,
    }


def build_icc_gamut_series(
    *,
    label: str,
    profile_path: Path,
    color: str,
    grid_size: int,
) -> dict[str, Any]:
    path = Path(profile_path).expanduser()
    key = ("icc", _profile_cache_key(path), int(grid_size))
    cached = _GAMUT_CACHE.get(key)
    if cached is not None:
        return cached

    rgb, quads = rgb_surface_mesh(grid_size)
    lab = _lookup_lab_with_icc(path, rgb)
    finite_lab = _finite_lab_points(lab)
    series = {
        "label": label,
        "kind": "icc",
        "path": str(path),
        "color": color,
        "surface_rgb": rgb,
        "quads": quads,
        "points_lab": finite_lab,
        "health": _lab_gamut_health(finite_lab),
    }
    _GAMUT_CACHE[key] = series
    _trim_cache()
    return series


def build_standard_gamut_series(output_space: str, *, grid_size: int) -> dict[str, Any]:
    profile = GENERIC_RGB_PROFILES[output_space]
    key = ("standard", output_space, int(grid_size))
    cached = _GAMUT_CACHE.get(key)
    if cached is not None:
        return cached

    rgb, quads = rgb_surface_mesh(grid_size)
    lab = _standard_rgb_to_lab(rgb, output_space)
    finite_lab = _finite_lab_points(lab)
    series = {
        "label": profile.label,
        "kind": "standard",
        "profile_key": profile.key,
        "color": STANDARD_GAMUT_COLORS.get(profile.key, "#94a3b8"),
        "surface_rgb": rgb,
        "quads": quads,
        "points_lab": finite_lab,
        "health": _lab_gamut_health(finite_lab),
    }
    _GAMUT_CACHE[key] = series
    _trim_cache()
    return series


def rgb_surface_samples(grid_size: int) -> np.ndarray:
    rgb, _quads = rgb_surface_mesh(grid_size)
    return rgb


def rgb_surface_mesh(grid_size: int) -> tuple[np.ndarray, list[list[int]]]:
    n = int(np.clip(grid_size, 3, 65))
    axis = np.linspace(0.0, 1.0, n, dtype=np.float64)
    index_by_coord: dict[tuple[int, int, int], int] = {}
    coords: list[tuple[int, int, int]] = []
    quads: list[list[int]] = []

    def vertex(coord: tuple[int, int, int]) -> int:
        existing = index_by_coord.get(coord)
        if existing is not None:
            return existing
        index = len(coords)
        index_by_coord[coord] = index
        coords.append(coord)
        return index

    def face(axis_index: int, fixed: int, u_axis: int, v_axis: int) -> None:
        for u in range(n - 1):
            for v in range(n - 1):
                corners = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    coord = [0, 0, 0]
                    coord[axis_index] = fixed
                    coord[u_axis] = u + du
                    coord[v_axis] = v + dv
                    corners.append(vertex(tuple(coord)))
                quads.append(corners)

    face(0, 0, 1, 2)
    face(0, n - 1, 1, 2)
    face(1, 0, 0, 2)
    face(1, n - 1, 0, 2)
    face(2, 0, 0, 1)
    face(2, n - 1, 0, 1)

    rgb = np.asarray([[axis[i], axis[j], axis[k]] for i, j, k in coords], dtype=np.float64)
    return np.ascontiguousarray(rgb), quads


def _standard_rgb_to_lab(rgb: np.ndarray, output_space: str) -> np.ndarray:
    profile = GENERIC_RGB_PROFILES[output_space]
    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    matrix = np.asarray(rgb_space.matrix_RGB_to_XYZ, dtype=np.float64)
    xyz_native = np.asarray(rgb, dtype=np.float64) @ matrix.T
    source_white = np.asarray(colour.xy_to_XYZ(rgb_space.whitepoint), dtype=np.float64)
    if np.allclose(source_white, D50_XYZ, atol=1e-6):
        xyz_d50 = xyz_native
    else:
        adaptation = matrix_chromatic_adaptation_VonKries(source_white, D50_XYZ, transform="Bradford")
        xyz_d50 = xyz_native @ np.asarray(adaptation, dtype=np.float64).T
    return np.asarray(colour.XYZ_to_Lab(xyz_d50, illuminant=D50_XY), dtype=np.float64)


def _standard_containment_comparisons(lab_points: np.ndarray) -> list[dict[str, Any]]:
    points = _finite_lab_points(lab_points)
    if points.size == 0:
        return []

    comparisons: list[dict[str, Any]] = []
    for key in STANDARD_GAMUT_KEYS:
        inside = _lab_inside_standard_rgb(points, key)
        inside_count = int(np.count_nonzero(inside))
        total = int(inside.size)
        comparisons.append(
            {
                "target": GENERIC_RGB_PROFILES[key].label,
                "profile_key": key,
                "inside_samples": inside_count,
                "outside_samples": int(total - inside_count),
                "inside_ratio": float(inside_count / total) if total else 0.0,
            }
        )
    return comparisons


def _pair_containment_comparisons(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(series) != 2:
        return []
    a, b = series
    comparisons = [
        _containment_record(source=a, target=b, marker_color="#f43f5e"),
        _containment_record(source=b, target=a, marker_color="#38bdf8"),
    ]
    return [record for record in comparisons if record is not None]


def _containment_record(
    *,
    source: dict[str, Any],
    target: dict[str, Any],
    marker_color: str,
) -> dict[str, Any] | None:
    source_points = _finite_lab_points(np.asarray(source.get("points_lab"), dtype=np.float64))
    if source_points.size == 0:
        return None
    inside, method = _lab_inside_profile(source_points, target)
    inside_count = int(np.count_nonzero(inside))
    total = int(inside.size)
    _attach_out_of_gamut_samples(source, target, source_points, inside, marker_color=marker_color)
    record = {
        "source": str(source.get("label") or "Perfil"),
        "target": str(target.get("label") or target.get("profile_key") or "Perfil"),
        "target_profile_key": str(target.get("profile_key") or ""),
        "inside_samples": inside_count,
        "outside_samples": int(total - inside_count),
        "inside_ratio": float(inside_count / total) if total else 0.0,
    }
    if method:
        record["method"] = method
    return record


def _lab_inside_profile(lab_points: np.ndarray, target: dict[str, Any]) -> tuple[np.ndarray, str]:
    points = _finite_lab_points(lab_points)
    if points.size == 0:
        return np.zeros(0, dtype=bool), ""
    key = str(target.get("profile_key") or "")
    if target.get("kind") == "standard" and key:
        return _lab_inside_standard_rgb(points, key), "rgb_primaries"
    target_points = _finite_lab_points(np.asarray(target.get("points_lab"), dtype=np.float64))
    return _lab_inside_lab_convex_hull(points, target_points), "lab_convex_hull"


def _attach_out_of_gamut_samples(
    source: dict[str, Any],
    target: dict[str, Any],
    source_points: np.ndarray,
    inside: np.ndarray,
    *,
    marker_color: str,
) -> None:
    total = int(len(source_points))
    if total == 0 or inside.shape[0] != total:
        return
    outside = np.logical_not(inside)
    outside_count = int(np.count_nonzero(outside))
    rgb = np.asarray(source.get("surface_rgb"), dtype=np.float64)
    if rgb.ndim != 2 or rgb.shape[0] != total or rgb.shape[1] < 3:
        rgb = np.zeros((total, 3), dtype=np.float64)
    source["out_of_gamut_lab"] = np.ascontiguousarray(source_points[outside], dtype=np.float64)
    source["out_of_gamut_rgb"] = np.ascontiguousarray(np.clip(rgb[outside, :3], 0.0, 1.0), dtype=np.float64)
    source["out_of_gamut_samples"] = outside_count
    source["out_of_gamut_ratio"] = float(outside_count / total) if total else 0.0
    source["out_of_gamut_target"] = str(target.get("label") or target.get("profile_key") or "Perfil")
    source["out_of_gamut_color"] = marker_color


def _lab_inside_standard_rgb(lab_points: np.ndarray, output_space: str, *, tolerance: float = 1e-4) -> np.ndarray:
    profile = GENERIC_RGB_PROFILES[output_space]
    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    xyz_d50 = np.asarray(colour.Lab_to_XYZ(lab_points, illuminant=D50_XY), dtype=np.float64)
    source_white = np.asarray(colour.xy_to_XYZ(rgb_space.whitepoint), dtype=np.float64)
    if np.allclose(source_white, D50_XYZ, atol=1e-6):
        xyz_native = xyz_d50
    else:
        adaptation = matrix_chromatic_adaptation_VonKries(D50_XYZ, source_white, transform="Bradford")
        xyz_native = xyz_d50 @ np.asarray(adaptation, dtype=np.float64).T

    matrix = np.asarray(rgb_space.matrix_RGB_to_XYZ, dtype=np.float64)
    rgb_linear = xyz_native @ np.linalg.inv(matrix).T
    return np.all((rgb_linear >= -tolerance) & (rgb_linear <= 1.0 + tolerance), axis=1)


def _lab_inside_lab_convex_hull(
    lab_points: np.ndarray,
    target_points: np.ndarray,
    *,
    tolerance: float = 1e-8,
) -> np.ndarray:
    points = _finite_lab_points(lab_points)
    if points.size == 0:
        return np.zeros(0, dtype=bool)
    target = _finite_lab_points(target_points)
    if target.shape[0] < 4:
        return np.zeros(points.shape[0], dtype=bool)
    target = np.unique(np.round(target, decimals=8), axis=0)
    if target.shape[0] < 4:
        return np.zeros(points.shape[0], dtype=bool)
    try:
        hull = Delaunay(target)
        return hull.find_simplex(points, tol=tolerance) >= 0
    except QhullError:
        mins = np.min(target, axis=0) - tolerance
        maxs = np.max(target, axis=0) + tolerance
        return np.all((points >= mins) & (points <= maxs), axis=1)


def _finite_lab_points(points: np.ndarray) -> np.ndarray:
    lab = np.asarray(points, dtype=np.float64)
    if lab.ndim != 2 or lab.shape[1] < 3:
        return np.zeros((0, 3), dtype=np.float64)
    lab = lab[:, :3]
    return np.ascontiguousarray(lab[np.all(np.isfinite(lab), axis=1)], dtype=np.float64)


def _lab_gamut_health(points: np.ndarray) -> dict[str, Any]:
    lab = _finite_lab_points(points)
    if lab.size == 0:
        return {
            "finite_samples": 0,
            "l_min": 0.0,
            "l_max": 0.0,
            "chroma_max": 0.0,
            "pcs_out_of_range_samples": 0,
            "extreme_chroma_samples": 0,
            "status": "empty",
        }
    chroma = np.linalg.norm(lab[:, 1:3], axis=1)
    pcs_out = (lab[:, 0] < -1e-3) | (lab[:, 0] > 100.0 + 1e-3)
    extreme = chroma > 220.0
    status = "ok"
    if np.any(pcs_out) or np.any(extreme):
        status = "extreme"
    return {
        "finite_samples": int(lab.shape[0]),
        "l_min": float(np.min(lab[:, 0])),
        "l_max": float(np.max(lab[:, 0])),
        "chroma_max": float(np.max(chroma)),
        "pcs_out_of_range_samples": int(np.count_nonzero(pcs_out)),
        "extreme_chroma_samples": int(np.count_nonzero(extreme)),
        "status": status,
    }


def _profile_cache_key(profile_path: Path) -> str:
    try:
        resolved = profile_path.expanduser().resolve()
        st = resolved.stat()
        return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return str(profile_path)


def _trim_cache() -> None:
    while len(_GAMUT_CACHE) > 12:
        oldest = next(iter(_GAMUT_CACHE))
        _GAMUT_CACHE.pop(oldest, None)
