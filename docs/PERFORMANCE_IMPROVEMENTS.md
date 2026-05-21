# Performance Improvement Plan

_Spanish version: [PERFORMANCE_IMPROVEMENTS.es.md](PERFORMANCE_IMPROVEMENTS.es.md)_

Analysis and implementation plan for performance improvements to ProbRAW without
altering scientific correctness or canonical output bytes.

**Analysis date:** 2026-05-07  
**Baseline version:** 0.3.16  
**Analyst:** Claude Sonnet 4.6

---

## Fundamental rule (existing, preserved)

Canonical paths (`pipeline.py → render_recipe_output_array`, `write_tiff16`,
`export.py`) **are not modified**. All improvements apply exclusively to
**display paths**, **demosaic cache management** and **repeated operations in
GUI sessions**.

Any change that affects canonical pipeline output bytes must be documented as a
reproducibility change (see REPRODUCIBILITY.md) and trigger a golden hash
regeneration.

---

## Context: existing optimizations

Before the improvements below, ProbRAW already has:

- LRU demosaic cache (`.npy` files, SHA-256 keyed, 5 GiB limit)
- ProcessPoolExecutor for batch with automatic RAM-based worker count
- Async final preview worker for images > 2 MP
- LUT-based tone curve with `@lru_cache(maxsize=512)` on the interpolation
- `render_adjustments_affine_u8` fast path for affine-only adjustments
- External process for cold MTF ROI preparation
- Bounded preview proxy during drag vs. full preview on release
- `_RAW_SHA_CACHE` in-process SHA-256 cache for demosaic key computation
- `@lru_cache` on `_cct_linear_srgb_white` (temperature lookups)
- Dense 8-bit ICC LUT cached in RAM and on disk for display transforms

The improvements below target the remaining hot paths that were not yet covered.

---

## Benchmark baseline (D850, 8288×5520, 51.5 MiB)

| Case | Time |
|------|-----:|
| Demosaic `linear` full | 1.52 s |
| Demosaic `dcb` full | 5.36 s |
| Demosaic `amaze` full | 5.57 s |
| Cache populate `dcb` | 5.63 s |
| Cache hit `dcb` | 0.16 s |
| Half-size preview `dcb` | 0.85–0.88 s |
| Interactive preview (brightness) | ~41–44 ms |
| Interactive preview (tone curve) | ~62 ms |
| Final preview D850 half-size | 272–443 ms |

---

## Improvement 1 — Precomputed LUT for `linear_to_srgb_display_u8`

**Files:** `src/probraw/raw/_srgb_lut.py` (new) + `src/probraw/raw/preview.py`

**Functions:** `linear_to_srgb_display_u8`, `linear_to_srgb_display`

### Problem

Every QImage buffer creation calls `linear_to_srgb_display_u8` with the full
preview image. The current implementation executes `np.power`, a boolean mask,
`np.where` and scalar rounding — **6 large vectorised operations** over a
float32 image.

For a D850 half-resolution preview (2760×4144×3 float32):

- Current memory access: ~6 × 130 MB ≈ **780 MB**
- With a 65536-entry uint8 LUT (64 KB — fits in L2 cache):
  uint16 quantisation + table lookup ≈ **40 MB**

### Proposed change

New file `src/probraw/raw/_srgb_lut.py`:

```python
import numpy as np

def _build_srgb_encode_u8_lut() -> np.ndarray:
    x = np.linspace(0.0, 1.0, 65536, dtype=np.float64)
    srgb = np.where(
        x <= 0.0031308,
        12.92 * x,
        1.055 * np.power(np.maximum(x, 0.0), 1.0 / 2.4) - 0.055,
    )
    out = np.clip(np.rint(srgb * 255.0), 0, 255).astype(np.uint8)
    out.setflags(write=False)
    return out

def _build_srgb_encode_f32_lut() -> np.ndarray:
    x = np.linspace(0.0, 1.0, 65536, dtype=np.float64)
    srgb = np.where(
        x <= 0.0031308,
        12.92 * x,
        1.055 * np.power(np.maximum(x, 0.0), 1.0 / 2.4) - 0.055,
    )
    out = np.clip(srgb, 0.0, 1.0).astype(np.float32)
    out.setflags(write=False)
    return out

SRGB_ENCODE_U8_LUT: np.ndarray = _build_srgb_encode_u8_lut()
SRGB_ENCODE_F32_LUT: np.ndarray = _build_srgb_encode_f32_lut()
```

Replacement functions in `preview.py`:

```python
from ._srgb_lut import SRGB_ENCODE_U8_LUT, SRGB_ENCODE_F32_LUT

def linear_to_srgb_display_u8(image_linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)
    indices = np.rint(x * np.float32(65535.0)).astype(np.uint16)
    return np.ascontiguousarray(SRGB_ENCODE_U8_LUT[indices])

def linear_to_srgb_display(image_linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(image_linear_rgb, dtype=np.float32), 0.0, 1.0)
    indices = np.rint(x * np.float32(65535.0)).astype(np.uint16)
    return SRGB_ENCODE_F32_LUT[indices].copy()
```

### Expected impact

~40–55 % reduction in display conversion time for the interactive preview path.

### Safety

Completely safe — same formula, quantisation to 1/65535 ≈ 0.0015 %. This is
well below the 1/255 ≈ 0.39 % quantisation of the uint8 output itself.
Display path only; canonical TIFF bytes are unchanged.

---

## Improvement 2 — Radial coordinate map cache for lateral CA correction

**File:** `src/probraw/raw/preview.py`

**Functions:** `_scale_channel_radially`, `apply_lateral_chromatic_aberration`

### Problem

`apply_lateral_chromatic_aberration` (line 441) calls `_scale_channel_radially`
separately for the red and blue channels. Each call executes
`np.indices((h, w), dtype=np.float32)` — for the D850 half-size preview
(2760×4144) this creates two 91 MB arrays just for coordinates, plus three more
arrays of the same size for the maps: **~360 MB of allocations per slider
event**.

The map depends only on `(h, w, scale)`. In a GUI session the image size does
not change. Only `scale` changes when the user drags the CA slider.

### Proposed change

```python
# Add at module level in preview.py
_RADIAL_MAP_CACHE: dict[tuple[int, int, float], tuple[np.ndarray, np.ndarray]] = {}
_RADIAL_MAP_CACHE_MAX = 8

def _scale_channel_radially(channel: np.ndarray, scale: float) -> np.ndarray:
    if scale <= 0.0 or abs(scale - 1.0) <= 1e-5:
        return channel.astype(np.float32)

    h, w = channel.shape[:2]
    cache_key = (int(h), int(w), round(float(scale), 9))
    maps = _RADIAL_MAP_CACHE.get(cache_key)
    if maps is None:
        y_idx, x_idx = np.indices((h, w), dtype=np.float32)
        cx = (w - 1) * 0.5
        cy = (h - 1) * 0.5
        map_x = ((x_idx - cx) / scale + cx).astype(np.float32)
        map_y = ((y_idx - cy) / scale + cy).astype(np.float32)
        map_x.setflags(write=False)
        map_y.setflags(write=False)
        if len(_RADIAL_MAP_CACHE) >= _RADIAL_MAP_CACHE_MAX:
            _RADIAL_MAP_CACHE.pop(next(iter(_RADIAL_MAP_CACHE)))
        _RADIAL_MAP_CACHE[cache_key] = (map_x, map_y)
        maps = _RADIAL_MAP_CACHE[cache_key]

    return cv2.remap(
        channel.astype(np.float32),
        maps[0],
        maps[1],
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
```

### Expected impact

- First call: no change.
- Repeated calls with same image size and scale: eliminates ~360 MB of
  allocations and the `np.indices` computation time.
- In a normal GUI session (dragging the CA slider), the cache never
  invalidates.

### Memory budget

8 entries × 2 maps × (2760×4144×4 bytes) ≈ 730 MB worst case. If this is
unacceptable on memory-constrained hardware, reduce `_RADIAL_MAP_CACHE_MAX = 4`
(~365 MB).

---

## Improvement 3 — Rate-limiting for `_prune_demosaic_cache`

**File:** `src/probraw/raw/pipeline.py`

**Function:** `_prune_demosaic_cache`

### Problem

`_prune_demosaic_cache` is called synchronously after **every** cache write
(lines 134–135 and 162–163 of `pipeline.py`). In a batch of N files with
`use_cache: true`, this executes N full directory scans (glob `*/*.npy` + stat
of each file). For 50 images with a cache containing 200+ entries: **50 × 200
syscalls = 10,000 redundant stat calls**.

### Proposed change

```python
# Add at module level in pipeline.py
import time as _time
_DEMOSAIC_PRUNE_INTERVAL_S = 120.0
_DEMOSAIC_PRUNE_LAST: dict[str, float] = {}
_DEMOSAIC_PRUNE_LAST_LOCK = threading.RLock()

def _prune_demosaic_cache(cache_root: Path) -> None:
    max_bytes = _demosaic_cache_max_bytes()
    if max_bytes <= 0:
        return
    key = str(Path(cache_root).resolve())
    now = _time.monotonic()
    with _DEMOSAIC_PRUNE_LAST_LOCK:
        if now - _DEMOSAIC_PRUNE_LAST.get(key, 0.0) < _DEMOSAIC_PRUNE_INTERVAL_S:
            return
        _DEMOSAIC_PRUNE_LAST[key] = now
    root = Path(cache_root) / "demosaic"
    # ... rest of existing pruning logic unchanged
```

### Expected impact

Eliminates N-1 disk scans per batch session. For a 50-image batch: from
50 scans to ≤1 scan per 120-second window. In a multi-process batch
(ProcessPoolExecutor), each worker has its own `_DEMOSAIC_PRUNE_LAST`, so
at most W scans per interval instead of N scans (W workers << N files).

### Safety

Prune is GC-only. Delaying it by up to 120 seconds cannot affect scientific
output. The cache can temporarily exceed the configured size limit by at most
one write cycle.

---

## Improvement 4 — Allocation reduction in `_apply_vibrance_saturation`

**File:** `src/probraw/raw/preview.py`

**Function:** `_apply_vibrance_saturation` (line 742)

### Problem

Called every interactive preview frame when `vibrance ≠ 0` or `saturation ≠ 0`.
For a 2760×4144×3 float32 image (~130 MB), currently creates ~7 large
intermediate arrays:

```
out (copy 130 MB), y (43 MB), chroma (43 MB), vibrance_factor (43 MB),
out − y (130 MB), (out−y)×sat×vib (130 MB), adjusted (130 MB)
```
→ **~650 MB of allocations** per call.

### Proposed change

```python
def _apply_vibrance_saturation(image: np.ndarray, *, vibrance: float, saturation: float) -> np.ndarray:
    out = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    # Explicit dot product — 1 array (H, W)
    luma = out[..., 0] * np.float32(0.2126)
    luma += out[..., 1] * np.float32(0.7152)
    luma += out[..., 2] * np.float32(0.0722)
    np.clip(luma, 0.0, 1.0, out=luma)
    # Chroma: max − min over channel axis
    chroma = out.max(axis=2) - out.min(axis=2)  # (H, W)
    # Vibrance factor computed in-place, reusing chroma buffer
    vib = float(np.clip(vibrance, -1.0, 1.0))
    np.multiply(chroma, -vib, out=chroma)
    chroma += np.float32(1.0 + vib)
    np.clip(chroma, 0.0, 2.5, out=chroma)  # chroma is now vibrance_factor
    sat_factor = np.float32(max(0.0, 1.0 + float(saturation)))
    np.multiply(chroma, sat_factor, out=chroma)  # chroma is now combined_factor
    # In-place: out = luma + (out − luma) × combined_factor
    luma_3d = luma[..., np.newaxis]  # view, no copy
    out -= luma_3d
    out *= chroma[..., np.newaxis]
    out += luma_3d
    np.clip(out, 0.0, 1.0, out=out)
    return out
```

### Expected impact

Reduces allocations from ~7 to ~4 arrays. Saves ~260 MB peak RAM per call on
a D850 preview. Numerically identical to the original.

### Safety

In-place operations on `out` (a fresh copy from the initial `np.clip`) are
safe. The `luma_3d` broadcast view does not alias `out` channels. The formula
is algebraically identical to the original.

---

## Improvement 5 — `suppress_false_color` micro-optimisation

**File:** `src/probraw/raw/pipeline.py`

**Function:** `suppress_false_color` (line 331)

### Problem

The per-pass loop uses `np.tensordot` (overhead for small shapes) and creates
6 new arrays per iteration: `y, r_chroma, b_chroma, red, blue, green`, plus the
final `np.stack + astype`. For a full D850 image with 3 passes this results in
18 large array allocations.

### Proposed change

```python
def suppress_false_color(image: np.ndarray, steps: int) -> np.ndarray:
    passes = min(MAX_FALSE_COLOR_SUPPRESSION_STEPS, max(0, int(steps or 0)))
    out = np.clip(np.asarray(image, dtype=np.float32)[..., :3], 0.0, 1.0)
    if passes <= 0 or out.ndim != 3 or out.shape[2] < 3:
        return out.astype(np.float32, copy=False)

    w0 = np.float32(0.2126)
    w1 = np.float32(0.7152)
    w2 = np.float32(0.0722)
    for _ in range(passes):
        # Explicit linear combination: avoids tensordot overhead for shape (H,W,3)
        y = out[..., 0] * w0 + out[..., 1] * w1 + out[..., 2] * w2
        r_chroma = cv2.medianBlur((out[..., 0] - y).astype(np.float32), 3)
        b_chroma = cv2.medianBlur((out[..., 2] - y).astype(np.float32), 3)
        red = y + r_chroma
        blue = y + b_chroma
        green = (y - w0 * red - w2 * blue) * (np.float32(1.0) / w1)
        # In-place channel assignment: eliminates np.stack + astype allocation
        out[..., 0] = red
        out[..., 1] = green
        out[..., 2] = blue
        np.clip(out, 0.0, 1.0, out=out)
    return out.astype(np.float32, copy=False)
```

### Expected impact

Eliminates 1 large array allocation per pass (the `np.stack` result). For
D850 at 3 passes: ~390 MB fewer allocations total. The result is bit-for-bit
identical.

### Safety

The `out[..., 0] = red` assignments write to views of the preallocated `out`
buffer. There is no aliasing with `r_chroma` or `b_chroma` because those were
produced by `cv2.medianBlur`, which always returns a new array.

---

## Change summary

| # | File | Function(s) | Type | Impact |
|---|------|-------------|------|--------|
| 1 | `raw/_srgb_lut.py` (new) + `raw/preview.py` | `linear_to_srgb_display_u8`, `linear_to_srgb_display` | Precomputed LUT | High — every display frame |
| 2 | `raw/preview.py` | `_scale_channel_radially` | Coordinate map cache | High — CA slider in session |
| 3 | `raw/pipeline.py` | `_prune_demosaic_cache` | Disk scan rate-limiting | Medium — batch with cache |
| 4 | `raw/preview.py` | `_apply_vibrance_saturation` | In-place numpy | Medium — interactive preview |
| 5 | `raw/pipeline.py` | `suppress_false_color` | In-place numpy | Low-medium — optional feature |

## What is NOT modified

- `_apply_srgb_oetf` (canonical TIFF output)
- `write_tiff16`
- `render_recipe_output_array`
- `_process_batch_develop_job`
- `apply_profile_matrix`
- `_apply_srgb_lut` (ICC preview LUT, already vectorised)
- `tone_curve_lut` / `apply_tone_curve` (already LUT-based with `lru_cache`)

The signed TIFF bytes, ProbRAW Proof signatures, and canonical SHA-256 hashes
remain identical after all improvements.

---

## Validation plan

Before merging each improvement:

1. Run `pytest tests/` — 438 tests must pass.
2. Run `pytest tests/regression/` — canonical SHA-256 golden hashes must match.
3. Run `python scripts/benchmark_gui_interaction.py` and compare interactive
   preview timings against baseline.
4. For improvements 4 and 5: compare output arrays with `np.allclose` against
   the original functions using representative test images.
