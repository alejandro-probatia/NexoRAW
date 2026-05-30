from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import numpy as np
import cv2

from ..core.models import ChartDetectionResult, PatchDetection, Point2
from ..core.utils import read_image

# Use a conservative central read area. Users can drag individual regions in
# the GUI when a central sample hits dust, scratches, glare, or stains.
PATCH_SAMPLE_REGION_SCALE = 0.52


@dataclass(frozen=True)
class _PatchCandidate:
    center: tuple[float, float]
    bbox: tuple[int, int, int, int]
    area: float
    side: float


def detect_chart(image_path: Path, chart_type: str = "colorchecker24") -> ChartDetectionResult:
    image = read_image(image_path)
    return detect_chart_from_array(image, chart_type=chart_type)


def detect_chart_from_array(image: np.ndarray, chart_type: str = "colorchecker24") -> ChartDetectionResult:
    image = np.asarray(image, dtype=np.float32)
    h, w = image.shape[:2]
    bgr8 = np.clip(_to_display(image)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)

    chart_type, cols, rows = _chart_dimensions(chart_type)

    if chart_type == "colorchecker24":
        grid_result = _detect_colorchecker_by_patch_grid(image, bgr8, chart_type, cols, rows)
        if grid_result is not None:
            return grid_result

    quad = _find_chart_quad(bgr8)
    warnings: list[str] = []
    detection_mode = "automatic"

    if quad is None:
        quad = np.array(
            [[0.05 * w, 0.05 * h], [0.95 * w, 0.05 * h], [0.95 * w, 0.95 * h], [0.05 * w, 0.95 * h]],
            dtype=np.float32,
        )
        detection_mode = "fallback"
        warnings.append("no se detecto contorno de carta; usando bbox de fallback")

    return _build_detection_from_quad(
        image=image,
        bgr8=bgr8,
        quad=quad,
        chart_type=chart_type,
        cols=cols,
        rows=rows,
        detection_mode=detection_mode,
        warnings=warnings,
    )


def detect_chart_from_corners(
    image_path: Path,
    corners: list[tuple[float, float]],
    chart_type: str = "colorchecker24",
) -> ChartDetectionResult:
    if len(corners) != 4:
        raise ValueError("Se necesitan exactamente 4 esquinas para la deteccion manual")

    image = read_image(image_path)
    return detect_chart_from_corners_array(image, corners=corners, chart_type=chart_type)


def detect_chart_from_corners_array(
    image: np.ndarray,
    corners: list[tuple[float, float]],
    chart_type: str = "colorchecker24",
) -> ChartDetectionResult:
    if len(corners) != 4:
        raise ValueError("Se necesitan exactamente 4 esquinas para la deteccion manual")

    image = np.asarray(image, dtype=np.float32)
    bgr8 = np.clip(_to_display(image)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)
    chart_type, cols, rows = _chart_dimensions(chart_type)
    quad = np.array(corners, dtype=np.float32)
    return _build_detection_from_quad(
        image=image,
        bgr8=bgr8,
        quad=quad,
        chart_type=chart_type,
        cols=cols,
        rows=rows,
        detection_mode="manual",
        warnings=["deteccion manual por esquinas; revisar overlay antes del muestreo"],
        confidence_override=1.0,
        valid_patch_ratio_override=1.0,
    )


def _chart_dimensions(chart_type: str) -> tuple[str, int, int]:
    chart_type = chart_type.lower()
    if chart_type == "it8":
        return "it8", 12, 10
    return "colorchecker24", 6, 4


def _build_detection_from_quad(
    *,
    image: np.ndarray,
    bgr8: np.ndarray,
    quad: np.ndarray,
    chart_type: str,
    cols: int,
    rows: int,
    detection_mode: str,
    warnings: list[str],
    confidence_override: float | None = None,
    valid_patch_ratio_override: float | None = None,
) -> ChartDetectionResult:
    h, w = image.shape[:2]
    quad = _order_points_clockwise(quad)
    dst = np.array([[0, 0], [cols * 100, 0], [cols * 100, rows * 100], [0, rows * 100]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    H_inv = np.linalg.inv(H)

    return _build_detection_from_homography(
        image=image,
        bgr8=bgr8,
        H=H,
        H_inv=H_inv,
        chart_type=chart_type,
        cols=cols,
        rows=rows,
        detection_mode=detection_mode,
        warnings=warnings,
        confidence=confidence_override
        if confidence_override is not None
        else _confidence_score(quad, w, h, cols / rows),
        valid_patch_ratio=valid_patch_ratio_override if valid_patch_ratio_override is not None else 1.0,
    )


def _build_detection_from_homography(
    *,
    image: np.ndarray,
    bgr8: np.ndarray,
    H: np.ndarray,
    H_inv: np.ndarray,
    chart_type: str,
    cols: int,
    rows: int,
    detection_mode: str,
    warnings: list[str],
    confidence: float,
    valid_patch_ratio: float,
) -> ChartDetectionResult:
    warped = cv2.warpPerspective(bgr8, H, (cols * 100, rows * 100), flags=cv2.INTER_LINEAR)

    # Try to orient ColorChecker: lowest saturation row should be bottom row.
    if chart_type == "colorchecker24" and os.environ.get("ICC_ENABLE_ROTATION", "0") == "1":
        k = _estimate_rotation_colorchecker(warped)
        if k != 0:
            warnings.append(f"rotacion corregida automaticamente: {k * 90} grados")
        warped = np.rot90(warped, k)
        H_inv = _compose_inverse_rotation(H_inv, cols * 100, rows * 100, k)

    patches = _build_patch_geometry(H_inv, cols, rows)

    clipped_ratio = float(np.mean(np.any(image >= 0.999, axis=2)))
    if clipped_ratio > 0.01:
        warnings.append(f"clipping detectado: {clipped_ratio * 100:.2f}% pixeles")

    if detection_mode == "fallback":
        confidence = min(confidence, 0.05)
        valid_patch_ratio = 0.0

    chart_polygon_pts = _canonical_to_img(
        np.array([[0, 0], [cols * 100, 0], [cols * 100, rows * 100], [0, rows * 100]], dtype=np.float32),
        H_inv,
    )
    chart_polygon = [Point2(float(x), float(y)) for x, y in chart_polygon_pts]
    result = ChartDetectionResult(
        chart_type=chart_type,
        confidence_score=confidence,
        valid_patch_ratio=valid_patch_ratio,
        homography=[float(v) for v in H.flatten().tolist()],
        chart_polygon=chart_polygon,
        patches=patches,
        warnings=warnings,
        detection_mode=detection_mode,
    )
    return result


def draw_detection_overlay(image_path: Path, detection: ChartDetectionResult, out_preview: Path) -> None:
    image = read_image(image_path)
    draw_detection_overlay_array(image, detection, out_preview)


def draw_detection_overlay_array(image: np.ndarray, detection: ChartDetectionResult, out_preview: Path) -> None:
    image = np.asarray(image, dtype=np.float32)
    bgr8 = np.clip(_to_display(image)[:, :, ::-1] * 255.0, 0, 255).astype(np.uint8)

    chart = np.array([[p.x, p.y] for p in detection.chart_polygon], dtype=np.int32)
    cv2.polylines(bgr8, [chart], isClosed=True, color=(0, 255, 0), thickness=2)

    for patch in detection.patches:
        poly = np.array([[p.x, p.y] for p in patch.sample_region], dtype=np.int32)
        cv2.polylines(bgr8, [poly], isClosed=True, color=(0, 128, 255), thickness=1)

    out_preview.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_preview), bgr8)


def _detect_colorchecker_by_patch_grid(
    image: np.ndarray,
    bgr8: np.ndarray,
    chart_type: str,
    cols: int,
    rows: int,
) -> ChartDetectionResult | None:
    candidates = _find_colorchecker_patch_candidates(bgr8)
    if len(candidates) < 12:
        return None

    best: dict[str, object] | None = None
    for component in _candidate_components(candidates):
        fit = _fit_patch_grid_homography(component, cols, rows)
        if fit is None:
            continue
        if best is None or float(fit["confidence"]) > float(best["confidence"]):
            best = fit

    if best is None or float(best["confidence"]) < 0.35:
        return None

    warnings: list[str] = []
    valid_patch_ratio = float(best["valid_patch_ratio"])
    if valid_patch_ratio < 0.9:
        warnings.append(
            "deteccion automatica por patron de parches parcial: "
            f"{int(best['inlier_count'])}/{cols * rows} parches"
        )

    return _build_detection_from_homography(
        image=image,
        bgr8=bgr8,
        H=np.asarray(best["H"], dtype=np.float32),
        H_inv=np.asarray(best["H_inv"], dtype=np.float32),
        chart_type=chart_type,
        cols=cols,
        rows=rows,
        detection_mode="automatic",
        warnings=warnings,
        confidence=float(best["confidence"]),
        valid_patch_ratio=valid_patch_ratio,
    )


def _find_colorchecker_patch_candidates(bgr8: np.ndarray) -> list[_PatchCandidate]:
    h, w = bgr8.shape[:2]
    gray = cv2.cvtColor(bgr8, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr8, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]

    colored = (gray > 45) & (sat > 20)
    neutral = (gray > 50) & (gray < 240) & (sat <= 24)
    mask = np.where(colored | neutral, 255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_side = max(12.0, min(h, w) * 0.013)
    max_side = min(h, w) * 0.13
    candidates: list[_PatchCandidate] = []

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw <= 0 or bh <= 0:
            continue
        side = float((bw + bh) / 2.0)
        if side < min_side or side > max_side:
            continue
        ratio = max(bw, bh) / float(min(bw, bh))
        if ratio > 1.65:
            continue
        area = float(cv2.contourArea(cnt))
        fill_ratio = area / float(bw * bh)
        if fill_ratio < 0.35:
            continue
        candidates.append(
            _PatchCandidate(
                center=(float(x + bw / 2.0), float(y + bh / 2.0)),
                bbox=(int(x), int(y), int(bw), int(bh)),
                area=area,
                side=side,
            )
        )

    return candidates


def _candidate_components(candidates: list[_PatchCandidate]) -> list[list[_PatchCandidate]]:
    visited: set[int] = set()
    components: list[list[_PatchCandidate]] = []
    centers = np.array([c.center for c in candidates], dtype=np.float32)

    for start in range(len(candidates)):
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        component: list[_PatchCandidate] = []
        while stack:
            i = stack.pop()
            component.append(candidates[i])
            ci = centers[i]
            for j, candidate in enumerate(candidates):
                if j in visited:
                    continue
                threshold = max(45.0, 2.45 * max(candidates[i].side, candidate.side))
                if float(np.linalg.norm(ci - centers[j])) <= threshold:
                    visited.add(j)
                    stack.append(j)
        if len(component) >= 12:
            components.append(component)

    components.sort(key=len, reverse=True)
    return components


def _fit_patch_grid_homography(
    candidates: list[_PatchCandidate],
    cols: int,
    rows: int,
) -> dict[str, object] | None:
    if len(candidates) < max(12, int(cols * rows * 0.5)):
        return None

    pts = np.array([c.center for c in candidates], dtype=np.float32)
    row_labels, _row_centers = _cluster_1d(pts[:, 1], rows)
    col_labels, _col_centers = _cluster_1d(pts[:, 0], cols)
    if row_labels is None or col_labels is None:
        return None

    median_side = float(np.median([c.side for c in candidates]))
    cells: dict[tuple[int, int], _PatchCandidate] = {}
    for candidate, row, col in zip(candidates, row_labels, col_labels, strict=True):
        key = (int(row), int(col))
        current = cells.get(key)
        if current is None or abs(candidate.side - median_side) < abs(current.side - median_side):
            cells[key] = candidate

    if len(cells) < max(12, int(cols * rows * 0.6)):
        return None
    if min(sum(1 for row, _col in cells if row == r) for r in range(rows)) < 2:
        return None
    if min(sum(1 for _row, col in cells if col == c) for c in range(cols)) < 2:
        return None

    src: list[tuple[float, float]] = []
    dst: list[tuple[float, float]] = []
    for (row, col), candidate in sorted(cells.items()):
        src.append(candidate.center)
        dst.append(((col + 0.5) * 100.0, (row + 0.5) * 100.0))

    src_arr = np.array(src, dtype=np.float32)
    dst_arr = np.array(dst, dtype=np.float32)
    H, inliers = cv2.findHomography(src_arr, dst_arr, cv2.RANSAC, 22.0)
    if H is None or inliers is None:
        return None

    inlier_mask = inliers.reshape(-1).astype(bool)
    inlier_count = int(np.count_nonzero(inlier_mask))
    if inlier_count < max(12, int(cols * rows * 0.55)):
        return None

    projected = cv2.perspectiveTransform(src_arr.reshape(-1, 1, 2), H).reshape(-1, 2)
    errors = np.linalg.norm(projected - dst_arr, axis=1)
    rms = float(np.sqrt(np.mean(np.square(errors[inlier_mask]))))
    if not np.isfinite(rms) or rms > 25.0:
        return None

    coverage = len(cells) / float(cols * rows)
    inlier_ratio = inlier_count / float(len(cells))
    rms_score = max(0.0, 1.0 - rms / 25.0)
    confidence = float(np.clip(0.45 * coverage + 0.35 * inlier_ratio + 0.20 * rms_score, 0.0, 1.0))

    try:
        H_inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return None

    return {
        "H": H,
        "H_inv": H_inv,
        "confidence": confidence,
        "valid_patch_ratio": inlier_count / float(cols * rows),
        "inlier_count": inlier_count,
        "rms": rms,
    }


def _cluster_1d(values: np.ndarray, k: int) -> tuple[np.ndarray | None, np.ndarray | None]:
    values = np.asarray(values, dtype=np.float32)
    if values.size < k:
        return None, None

    quantiles = np.linspace(0.05, 0.95, k, dtype=np.float32)
    centers = np.quantile(values, quantiles).astype(np.float32)

    labels = np.zeros(values.shape[0], dtype=np.int32)
    for _ in range(40):
        distances = np.abs(values[:, None] - centers[None, :])
        new_labels = np.argmin(distances, axis=1).astype(np.int32)
        new_centers = centers.copy()
        for idx in range(k):
            cluster = values[new_labels == idx]
            if cluster.size:
                new_centers[idx] = float(np.mean(cluster))
        if np.array_equal(labels, new_labels) and np.allclose(centers, new_centers):
            break
        labels = new_labels
        centers = new_centers

    order = np.argsort(centers)
    relabel = np.zeros(k, dtype=np.int32)
    for new_idx, old_idx in enumerate(order):
        relabel[old_idx] = new_idx
    sorted_centers = centers[order]
    return relabel[labels], sorted_centers


def _find_chart_quad(bgr8: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(bgr8, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 130)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = None
    best_score = -1e9

    area_img = bgr8.shape[0] * bgr8.shape[1]

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        if not cv2.isContourConvex(approx):
            continue

        pts = approx[:, 0, :].astype(np.float32)
        area = cv2.contourArea(pts)
        if area < 0.02 * area_img:
            continue

        rect = cv2.minAreaRect(pts)
        rw, rh = rect[1]
        if rw <= 0 or rh <= 0:
            continue
        ratio = max(rw, rh) / min(rw, rh)
        ratio_penalty = abs(ratio - 1.5)

        score = area / area_img - 0.2 * ratio_penalty
        if score > best_score:
            best_score = score
            best = pts

    return best


def _order_points_clockwise(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _build_patch_geometry(H_inv: np.ndarray, cols: int, rows: int) -> list[PatchDetection]:
    patches: list[PatchDetection] = []

    for r in range(rows):
        for c in range(cols):
            patch_id = f"P{(r * cols + c + 1):02d}"
            x0 = c / cols
            y0 = r / rows
            x1 = (c + 1) / cols
            y1 = (r + 1) / rows

            poly_norm = np.array(
                [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                dtype=np.float32,
            )
            sample_norm = _shrink_poly_norm(poly_norm, 1.0 - PATCH_SAMPLE_REGION_SCALE)

            poly = _norm_to_img(poly_norm, H_inv, cols * 100, rows * 100)
            sample = _norm_to_img(sample_norm, H_inv, cols * 100, rows * 100)

            patches.append(
                PatchDetection(
                    patch_id=patch_id,
                    polygon=[Point2(float(x), float(y)) for x, y in poly],
                    sample_region=[Point2(float(x), float(y)) for x, y in sample],
                )
            )

    return patches


def _norm_to_img(poly_norm: np.ndarray, H_inv: np.ndarray, width: int, height: int) -> np.ndarray:
    pts = np.array([[x * width, y * height] for x, y in poly_norm], dtype=np.float32)
    return _canonical_to_img(pts, H_inv)


def _canonical_to_img(pts: np.ndarray, H_inv: np.ndarray) -> np.ndarray:
    pts_h = np.concatenate([pts, np.ones((pts.shape[0], 1), dtype=np.float32)], axis=1)
    out = (H_inv @ pts_h.T).T
    out = out[:, :2] / out[:, 2:3]
    return out


def _shrink_poly_norm(poly: np.ndarray, margin_ratio: float) -> np.ndarray:
    center = np.mean(poly, axis=0)
    return center + (poly - center) * (1.0 - margin_ratio)


def _estimate_rotation_colorchecker(warped_bgr: np.ndarray) -> int:
    best_k = 0
    best_score = -1e9
    for k in range(4):
        img = np.rot90(warped_bgr, k)
        # Ensure horizontal board for scoring (rows=4, cols=6)
        if img.shape[0] > img.shape[1]:
            img = np.rot90(img, 1)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1].astype(np.float32) / 255.0
        lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

        patch_sat = _grid_patch_means(sat, rows=4, cols=6)
        patch_lum = _grid_patch_means(lum, rows=4, cols=6)

        row_sat = patch_sat.mean(axis=1)
        row_lum = patch_lum[3]
        monotonic = -np.maximum(0.0, np.diff(row_lum)).sum()
        score = (row_sat.mean() - row_sat[3]) * 3.0 + monotonic
        if score > best_score:
            best_score = score
            best_k = k
    return best_k


def _grid_patch_means(image: np.ndarray, rows: int, cols: int) -> np.ndarray:
    h, w = image.shape[:2]
    out = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            y0 = int((r + 0.2) * h / rows)
            y1 = int((r + 0.8) * h / rows)
            x0 = int((c + 0.2) * w / cols)
            x1 = int((c + 0.8) * w / cols)
            patch = image[y0:y1, x0:x1]
            out[r, c] = float(np.mean(patch)) if patch.size else 0.0
    return out


def _compose_inverse_rotation(H_inv: np.ndarray, width: int, height: int, k: int) -> np.ndarray:
    # Map oriented canonical coordinates back to original canonical orientation.
    if k == 0:
        T = np.eye(3, dtype=np.float32)
    elif k == 1:
        T = np.array([[0, -1, width], [1, 0, 0], [0, 0, 1]], dtype=np.float32)
    elif k == 2:
        T = np.array([[-1, 0, width], [0, -1, height], [0, 0, 1]], dtype=np.float32)
    else:
        T = np.array([[0, 1, 0], [-1, 0, height], [0, 0, 1]], dtype=np.float32)
    return H_inv @ T


def _confidence_score(quad: np.ndarray, width: int, height: int, expected_ratio: float) -> float:
    area = cv2.contourArea(quad)
    area_ratio = area / float(width * height)
    rect = cv2.minAreaRect(quad.astype(np.float32))
    rw, rh = rect[1]
    if rw <= 0 or rh <= 0:
        return 0.0
    ratio = max(rw, rh) / min(rw, rh)
    ratio_error = abs(ratio - expected_ratio)
    score = 0.5 * min(1.0, area_ratio / 0.3) + 0.5 * max(0.0, 1.0 - ratio_error)
    return float(np.clip(score, 0.0, 1.0))


def _to_display(image_linear: np.ndarray) -> np.ndarray:
    a = 0.055
    out = np.where(
        image_linear <= 0.0031308,
        12.92 * image_linear,
        (1 + a) * np.power(np.clip(image_linear, 0.0, 1.0), 1 / 2.4) - a,
    )
    return np.clip(out, 0.0, 1.0)
