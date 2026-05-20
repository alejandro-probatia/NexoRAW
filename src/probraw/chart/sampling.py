from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
import numpy as np
import cv2

from ..core.models import ChartDetectionResult, PatchDetection, PatchSample, Point2, SampleSet, read_json
from ..core.utils import read_image, robust_trimmed_mean


class ReferenceCatalog:
    def __init__(self, payload: dict, *, strict: bool = False):
        self.chart_name: str = payload.get("chart_name", "unknown")
        self.chart_version: str = payload.get("chart_version", "unknown")
        self.illuminant: str = payload.get("illuminant", "unknown")
        self.observer: str = payload.get("observer", "2")
        self.reference_source: str | None = payload.get("reference_source") or payload.get("source")
        self.patches: list[dict] = payload.get("patches", [])
        self.patch_map = {p["patch_id"]: p for p in self.patches if "patch_id" in p}
        if strict:
            self.validate()

    @classmethod
    def from_path(cls, path: Path, *, strict: bool = True) -> "ReferenceCatalog":
        return cls(_read_reference_payload(path), strict=strict)

    def validate(self) -> None:
        errors: list[str] = []
        if self.chart_name == "unknown":
            errors.append("chart_name ausente")
        if self.chart_version == "unknown":
            errors.append("chart_version ausente")
        if self.illuminant.strip().upper() != "D50":
            errors.append(f"illuminant debe ser D50 para el pipeline ICC actual: {self.illuminant!r}")
        if _normalize_observer(self.observer) != "2":
            errors.append(f"observer debe ser 2 grados para el pipeline actual: {self.observer!r}")
        if not self.reference_source:
            errors.append("reference_source/source ausente")

        patch_ids = [str(p.get("patch_id")) for p in self.patches if "patch_id" in p]
        if len(patch_ids) != len(set(patch_ids)):
            errors.append("patch_id duplicado")
        if len(patch_ids) != len(self.patches):
            errors.append("todos los parches deben incluir patch_id")
        if "colorchecker" in self.chart_name.lower() and len(self.patches) != 24:
            errors.append(f"ColorChecker requiere 24 parches de referencia, encontrados {len(self.patches)}")

        for patch_id, patch in self.patch_map.items():
            lab = patch.get("reference_lab")
            if lab is None:
                errors.append(f"{patch_id}: reference_lab ausente")
                continue
            if not isinstance(lab, list) or len(lab) != 3:
                errors.append(f"{patch_id}: reference_lab debe tener 3 valores")
                continue
            try:
                l_val, a_val, b_val = [float(v) for v in lab]
            except Exception:
                errors.append(f"{patch_id}: reference_lab contiene valores no numericos")
                continue
            if not (0.0 <= l_val <= 100.0):
                errors.append(f"{patch_id}: L* fuera de rango 0..100")
            if not (-160.0 <= a_val <= 160.0 and -160.0 <= b_val <= 160.0):
                errors.append(f"{patch_id}: a*/b* fuera de rango esperado")

        if errors:
            raise RuntimeError("Referencia de carta invalida: " + "; ".join(errors))


def _normalize_observer(observer: str) -> str:
    raw = str(observer or "").strip().lower().replace(" ", "")
    if raw in {"2", "2deg", "2degree", "2degrees", "2°"}:
        return "2"
    if raw in {"10", "10deg", "10degree", "10degrees", "10°"}:
        return "10"
    return raw


_BUNDLED_REFERENCE_ALIASES = {
    "colorchecker24_colorchecker2005_d50.json": "colorchecker24_colorchecker2005_d50.json",
    "colorchecker2005_d50.json": "colorchecker24_colorchecker2005_d50.json",
}


def bundled_reference_catalogs() -> list[dict[str, str]]:
    seen: set[str] = set()
    catalogs: list[dict[str, str]] = []
    for bundled_name in sorted(set(_BUNDLED_REFERENCE_ALIASES.values())):
        if bundled_name in seen:
            continue
        seen.add(bundled_name)
        ref = resources.files("probraw.resources").joinpath("references", bundled_name)
        payload = json.loads(ref.read_text(encoding="utf-8"))
        catalog = ReferenceCatalog(payload, strict=False)
        catalogs.append(
            {
                "name": bundled_name,
                "path": bundled_name,
                "label": reference_catalog_label(catalog),
                "chart_name": catalog.chart_name,
                "chart_version": catalog.chart_version,
                "illuminant": catalog.illuminant,
            }
        )
    return catalogs


def reference_catalog_label(catalog: ReferenceCatalog) -> str:
    parts = [
        str(catalog.chart_name or "Carta").strip(),
        str(catalog.chart_version or "").strip(),
        str(catalog.illuminant or "").strip(),
    ]
    return " / ".join(part for part in parts if part and part != "unknown")


def reference_catalog_template(*, chart_name: str = "Carta personalizada", patch_count: int = 24) -> dict:
    count = max(1, int(patch_count))
    return {
        "chart_name": chart_name,
        "chart_version": "personalizada",
        "reference_source": "Medición personalizada introducida en ProbRAW",
        "illuminant": "D50",
        "observer": "2",
        "patch_order": "row-major, top-left to bottom-right",
        "patches": [
            {
                "patch_id": f"P{index:02d}",
                "patch_name": f"Patch {index:02d}",
                "reference_lab": [50.0, 0.0, 0.0],
            }
            for index in range(1, count + 1)
        ],
    }


def _read_reference_payload(path: Path) -> dict:
    candidate = Path(path)
    if candidate.exists():
        return read_json(candidate)

    bundled_name = _bundled_reference_name(candidate)
    if bundled_name is not None:
        ref = resources.files("probraw.resources").joinpath("references", bundled_name)
        return json.loads(ref.read_text(encoding="utf-8"))

    return read_json(candidate)


def _bundled_reference_name(path: Path) -> str | None:
    name = path.name
    if name in _BUNDLED_REFERENCE_ALIASES:
        return _BUNDLED_REFERENCE_ALIASES[name]

    normalized = path.as_posix()
    for suffix, bundled_name in _BUNDLED_REFERENCE_ALIASES.items():
        if normalized.endswith(f"testdata/references/{suffix}"):
            return bundled_name
    return None


def sample_chart(
    image_path: Path,
    detection: ChartDetectionResult,
    reference: ReferenceCatalog,
    strategy: str = "trimmed_mean",
    trim_percent: float = 0.1,
    reject_saturated: bool = True,
) -> SampleSet:
    image = read_image(image_path)
    return sample_chart_from_array(
        image,
        detection,
        reference,
        strategy=strategy,
        trim_percent=trim_percent,
        reject_saturated=reject_saturated,
    )


def sample_chart_from_array(
    image: np.ndarray,
    detection: ChartDetectionResult,
    reference: ReferenceCatalog,
    strategy: str = "trimmed_mean",
    trim_percent: float = 0.1,
    reject_saturated: bool = True,
) -> SampleSet:
    image = np.asarray(image, dtype=np.float32)

    samples: list[PatchSample] = []
    missing: list[str] = []

    for patch in detection.patches:
        ref = reference.patch_map.get(patch.patch_id)
        if ref is None:
            missing.append(patch.patch_id)
            continue

        poly = np.array([[p.x, p.y] for p in patch.sample_region], dtype=np.float32)
        center = np.mean(poly, axis=0)
        rgb, excluded_ratio, sat_ratio = _sample_patch(
            image,
            poly,
            strategy,
            trim_percent=trim_percent,
            reject_saturated=reject_saturated,
        )

        samples.append(
            PatchSample(
                patch_id=patch.patch_id,
                measured_rgb=[float(v) for v in rgb],
                reference_rgb=[float(v) for v in ref.get("reference_rgb", [])] if ref.get("reference_rgb") is not None else None,
                reference_lab=[float(v) for v in ref.get("reference_lab", [])] if ref.get("reference_lab") is not None else None,
                excluded_pixel_ratio=float(excluded_ratio),
                saturated_pixel_ratio=float(sat_ratio),
                sample_center=[float(center[0]), float(center[1])],
                sampling_parameters=_sampling_parameters(strategy, trim_percent, reject_saturated),
            )
        )

    if not samples:
        raise RuntimeError("no se pudo muestrear ningun parche")

    return SampleSet(
        chart_name=reference.chart_name,
        chart_version=reference.chart_version,
        illuminant=reference.illuminant,
        strategy=_strategy_label(strategy, trim_percent, reject_saturated),
        samples=samples,
        missing_reference_patches=missing,
    )


def _sample_patch(
    image: np.ndarray,
    polygon: np.ndarray,
    strategy: str,
    *,
    trim_percent: float = 0.1,
    reject_saturated: bool = True,
) -> tuple[np.ndarray, float, float]:
    h, w = image.shape[:2]
    poly_int = np.round(polygon).astype(np.int32)
    x0 = int(np.clip(np.min(poly_int[:, 0]), 0, max(0, w - 1)))
    y0 = int(np.clip(np.min(poly_int[:, 1]), 0, max(0, h - 1)))
    x1 = int(np.clip(np.max(poly_int[:, 0]) + 1, x0 + 1, w))
    y1 = int(np.clip(np.max(poly_int[:, 1]) + 1, y0 + 1, h))
    local = image[y0:y1, x0:x1]
    if local.size == 0:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32), 1.0, 0.0

    mask = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    cv2.fillPoly(mask, [poly_int - np.array([x0, y0], dtype=np.int32)], 255)

    pixels = local[mask == 255]
    if pixels.size == 0:
        return np.array([0.0, 0.0, 0.0], dtype=np.float32), 1.0, 0.0

    saturated = np.any(pixels >= 0.999, axis=1)
    sat_ratio = float(np.mean(saturated))

    valid = pixels[~saturated] if reject_saturated else pixels
    if valid.size == 0:
        valid = pixels

    if strategy == "median":
        measured = np.median(valid, axis=0)
        excluded_ratio = float(np.mean(saturated)) if reject_saturated else 0.0
    else:
        trim = float(np.clip(trim_percent, 0.0, 0.49))
        measured = np.array(
            [robust_trimmed_mean(valid[:, c], trim) for c in range(3)],
            dtype=np.float32,
        )
        trimmed_ratio = min(1.0, 2.0 * trim) if valid.shape[0] > 0 else 0.0
        rejected_ratio = float(np.mean(saturated)) if reject_saturated else 0.0
        excluded_ratio = float(min(1.0, rejected_ratio + (1.0 - rejected_ratio) * trimmed_ratio))

    return measured, excluded_ratio, sat_ratio


def _strategy_label(strategy: str, trim_percent: float, reject_saturated: bool) -> str:
    mode = str(strategy or "trimmed_mean")
    if mode == "median":
        return f"median(reject_saturated={str(bool(reject_saturated)).lower()})"
    trim = float(np.clip(trim_percent, 0.0, 0.49))
    return f"{mode}(trim_percent={trim:.6g},reject_saturated={str(bool(reject_saturated)).lower()})"


def _sampling_parameters(strategy: str, trim_percent: float, reject_saturated: bool) -> dict[str, object]:
    mode = str(strategy or "trimmed_mean")
    return {
        "strategy": mode,
        "trim_percent": float(np.clip(trim_percent, 0.0, 0.49)),
        "reject_saturated": bool(reject_saturated),
    }


def chart_detection_from_json(path: Path) -> ChartDetectionResult:
    payload = read_json(path)

    chart_polygon = [Point2(**p) for p in payload["chart_polygon"]]
    patches = []
    for p in payload["patches"]:
        patches.append(
            PatchDetection(
                patch_id=p["patch_id"],
                polygon=[Point2(**q) for q in p["polygon"]],
                sample_region=[Point2(**q) for q in p["sample_region"]],
            )
        )

    return ChartDetectionResult(
        chart_type=payload["chart_type"],
        confidence_score=float(payload["confidence_score"]),
        valid_patch_ratio=float(payload["valid_patch_ratio"]),
        homography=[float(v) for v in payload["homography"]],
        chart_polygon=chart_polygon,
        patches=patches,
        warnings=[str(v) for v in payload.get("warnings", [])],
        detection_mode=str(payload.get("detection_mode", "automatic")),
    )


def sampleset_from_json(path: Path) -> SampleSet:
    payload = read_json(path)
    samples = [PatchSample(**s) for s in payload["samples"]]
    return SampleSet(
        chart_name=payload["chart_name"],
        chart_version=payload["chart_version"],
        illuminant=payload["illuminant"],
        strategy=payload.get("strategy", "trimmed_mean"),
        samples=samples,
        missing_reference_patches=payload.get("missing_reference_patches", []),
    )
