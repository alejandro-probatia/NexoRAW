from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict
import multiprocessing
from pathlib import Path
import hashlib
import json
import os
import subprocess
import shutil
import tempfile
from typing import Any
import numpy as np
import colour

from ..core.models import BatchManifest, BatchManifestEntry, Recipe
from ..core.external import external_tool_path, run_external
from ..core.utils import (
    RAW_EXTENSIONS,
    list_raw_files,
    resolve_tiff_maxworkers,
    rewrite_tiff_compression,
    sha256_file,
    tiff_compression_for_metadata,
    write_tiff16,
)
from ..performance import available_cpu_count as _runtime_available_cpu_count
from ..performance import batch_worker_cap as _runtime_batch_worker_cap
from .generic import (
    canonical_generic_output_space,
    ensure_generic_output_profile,
    generic_output_profile,
    is_generic_output_space,
)
from ..provenance.c2pa import (
    C2PASignConfig,
    C2PASigningError,
    build_render_settings,
    sign_tiff_with_c2pa,
)
from ..provenance.probraw_proof import (
    ProbRawProofConfig,
    ProbRawProofResult,
    proof_config_from_environment,
    sign_probraw_proof,
)
from ..raw.pipeline import (
    develop_scene_linear_array,
    develop_standard_linear_array,
    effective_raw_processing_settings,
    render_recipe_output_array,
)
from ..session import cache_dir as session_cache_dir
from ..sidecar import write_raw_sidecar
from ..version import __version__


D50_XY = np.asarray(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"], dtype=np.float64)
BATCH_WORKERS_ENV = "PROBRAW_BATCH_WORKERS"
BATCH_MEMORY_RESERVE_MB_ENV = "PROBRAW_BATCH_MEMORY_RESERVE_MB"
BATCH_WORKER_RAM_MB_ENV = "PROBRAW_BATCH_WORKER_RAM_MB"
DEFAULT_BATCH_MEMORY_RESERVE_MB = 1024
DEFAULT_BATCH_WORKER_RAM_MB = 2800


def batch_develop(
    raws_dir: Path,
    recipe: Recipe,
    profile_path: Path | None,
    out_dir: Path,
    *,
    workers: int | None = None,
    cache_dir: Path | None = None,
    c2pa_config: C2PASignConfig | None = None,
    proof_config: ProbRawProofConfig | None = None,
    tiff_compression: str | None = None,
    tiff_maxworkers: int | None = None,
) -> BatchManifest:
    out_dir.mkdir(parents=True, exist_ok=True)
    linear_audit_dir = out_dir / "_linear_audit"
    linear_audit_dir.mkdir(parents=True, exist_ok=True)
    files = list_raw_files(raws_dir)
    if not files:
        files = sorted(
            [
                p
                for p in raws_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
            ]
        )
    if not files:
        raise RuntimeError(f"No se encontraron RAWs ni imagenes compatibles en: {raws_dir}")

    if profile_path is not None and not profile_path.exists():
        raise FileNotFoundError(f"No existe perfil ICC: {profile_path}")
    if profile_path is None and not is_generic_output_space(recipe.output_space):
        raise RuntimeError(
            "batch-develop sin --profile solo es valido con output_space estandar "
            "(srgb, adobe_rgb o prophoto_rgb)."
        )

    color_mode = color_management_mode_for_render(recipe, profile_path=profile_path)
    proof_sign_config = proof_config or proof_config_from_environment()

    recipe_sha = hashlib.sha256(json.dumps(asdict(recipe), sort_keys=True).encode("utf-8")).hexdigest()
    worker_count = _resolve_batch_workers(len(files), workers=workers, files=files, recipe=recipe)
    resolved_tiff_maxworkers = _resolve_batch_tiff_maxworkers(
        worker_count,
        tiff_compression=tiff_compression,
        configured=tiff_maxworkers,
    )
    demosaic_cache_dir = _resolve_demosaic_cache_dir(
        raws_dir=raws_dir,
        out_dir=out_dir,
        configured=cache_dir,
        recipe=recipe,
    )
    planned_jobs: list[tuple[int, Path, Path, Path]] = []
    reserved_outputs: set[str] = set()
    reserved_audits: set[str] = set()
    for idx, raw in enumerate(files):
        out_final, out_linear = _versioned_batch_paths(
            out_dir,
            linear_audit_dir,
            raw.stem,
            reserved_outputs=reserved_outputs,
            reserved_audits=reserved_audits,
        )
        planned_jobs.append((idx, raw, out_final, out_linear))

    jobs = [
        (
            idx,
            raw,
            out_final,
            out_linear,
            recipe,
            profile_path,
            c2pa_config,
            proof_sign_config,
            color_mode,
            demosaic_cache_dir,
            tiff_compression_for_metadata(tiff_compression),
            resolved_tiff_maxworkers,
        )
        for idx, raw, out_final, out_linear in planned_jobs
    ]
    entries_slots: list[BatchManifestEntry | None] = [None] * len(jobs)

    if worker_count <= 1:
        for job in jobs:
            position, entry = _process_batch_develop_job(job)
            entries_slots[position] = entry
    else:
        multiprocessing.freeze_support()
        executor_cls = ThreadPoolExecutor if _requires_thread_batch_executor(c2pa_config) else ProcessPoolExecutor
        executor_kwargs: dict[str, Any] = {"max_workers": worker_count}
        if executor_cls is ThreadPoolExecutor:
            executor_kwargs["thread_name_prefix"] = "probraw-batch"
        with executor_cls(**executor_kwargs) as executor:
            futures = [executor.submit(_process_batch_develop_job, job) for job in jobs]
            for future in as_completed(futures):
                position, entry = future.result()
                entries_slots[position] = entry

    entries: list[BatchManifestEntry] = [entry for entry in entries_slots if entry is not None]

    return BatchManifest(
        recipe_sha256=recipe_sha,
        profile_path=str(profile_path) if profile_path is not None else "",
        color_management_mode=color_mode,
        output_color_space=recipe.output_space,
        software_version=__version__,
        entries=entries,
    )


def _resolve_batch_workers(
    total_items: int,
    workers: int | None = None,
    *,
    files: list[Path] | None = None,
    recipe: Recipe | None = None,
) -> int:
    total = max(1, int(total_items))
    if workers is not None:
        configured = int(workers)
        if configured > 0:
            return max(1, min(total, configured))
        available_cpus = _available_cpu_count()
        return _resolve_auto_batch_workers(total, available_cpus, files=files, recipe=recipe)
    available_cpus = _available_cpu_count()
    auto_workers = _resolve_auto_batch_workers(total, available_cpus, files=files, recipe=recipe)
    raw_value = os.environ.get(BATCH_WORKERS_ENV, "").strip()
    if not raw_value:
        return auto_workers
    if raw_value.lower() in {"auto", "max", "all"}:
        return auto_workers
    try:
        configured = int(raw_value)
    except ValueError:
        return auto_workers
    if configured <= 0:
        return auto_workers
    return max(1, min(total, configured))


def _resolve_auto_batch_workers(
    total_items: int,
    available_cpus: int,
    *,
    files: list[Path] | None = None,
    recipe: Recipe | None = None,
) -> int:
    cpu_bound = max(1, min(total_items, max(1, int(available_cpus))))
    memory_bound = _memory_limited_batch_workers(total_items, files=files, recipe=recipe)
    native_bound = max(1, min(total_items, _runtime_batch_worker_cap(available_cpus)))
    return max(1, min(cpu_bound, memory_bound, native_bound))


def _available_cpu_count() -> int:
    return _runtime_available_cpu_count()


def _resolve_batch_tiff_maxworkers(
    batch_workers: int,
    *,
    tiff_compression: str | None,
    configured: int | None = None,
) -> int | None:
    resolved = resolve_tiff_maxworkers(configured, compression=tiff_compression)
    if resolved is not None:
        return resolved
    if tiff_compression_for_metadata(tiff_compression) == "none":
        return None
    return max(1, _available_cpu_count() // max(1, int(batch_workers)))


def _memory_limited_batch_workers(
    total_items: int,
    *,
    files: list[Path] | None = None,
    recipe: Recipe | None = None,
) -> int:
    available_bytes = _available_physical_memory_bytes()
    if available_bytes is None or available_bytes <= 0:
        return max(1, int(total_items))

    reserve_mb = _read_positive_env_value(
        BATCH_MEMORY_RESERVE_MB_ENV,
        default=DEFAULT_BATCH_MEMORY_RESERVE_MB,
    )
    per_worker_mb = _estimated_worker_ram_mb(files=files, recipe=recipe)
    reserve_bytes = int(reserve_mb) * 1024 * 1024
    per_worker_bytes = max(1, int(per_worker_mb) * 1024 * 1024)
    budget_bytes = max(0, int(available_bytes) - reserve_bytes)
    if budget_bytes <= 0:
        return 1
    workers = max(1, budget_bytes // per_worker_bytes)
    return max(1, min(int(total_items), int(workers)))


def _estimated_worker_ram_mb(*, files: list[Path] | None = None, recipe: Recipe | None = None) -> int:
    raw = os.environ.get(BATCH_WORKER_RAM_MB_ENV, "").strip()
    if raw:
        return _read_positive_env_value(BATCH_WORKER_RAM_MB_ENV, default=DEFAULT_BATCH_WORKER_RAM_MB)

    max_size_mb = 0.0
    has_raw_input = False
    for path in files or []:
        candidate = Path(path)
        if candidate.suffix.lower() in RAW_EXTENSIONS:
            has_raw_input = True
        try:
            max_size_mb = max(max_size_mb, float(candidate.stat().st_size) / (1024.0 * 1024.0))
        except OSError:
            continue

    if max_size_mb <= 0.0:
        base = float(DEFAULT_BATCH_WORKER_RAM_MB)
    elif max_size_mb <= 18.0:
        base = 1200.0
    elif max_size_mb <= 45.0:
        base = 2000.0
    elif max_size_mb <= 75.0:
        base = 2800.0
    else:
        base = 3600.0

    algorithm = str(getattr(recipe, "demosaic_algorithm", "") if recipe is not None else "").strip().lower()
    if algorithm in {"linear", "vng", "ppg"}:
        base *= 0.75
    elif algorithm in {"amaze", "dcb", "lmmse", "afd"}:
        base *= 1.10
    if bool(getattr(recipe, "use_cache", False) if recipe is not None else False):
        base *= 1.05
    if has_raw_input:
        base = max(base, 1800.0)
    return max(512, int(round(base)))


def _process_batch_develop_job(
    job: tuple[
        int,
        Path,
        Path,
        Path,
        Recipe,
        Path | None,
        C2PASignConfig | None,
        ProbRawProofConfig,
        str,
        Path | None,
        str,
        int | None,
    ],
) -> tuple[int, BatchManifestEntry]:
    (
        index,
        raw,
        out_final,
        out_linear,
        recipe,
        profile_path,
        c2pa_config,
        proof_sign_config,
        color_mode,
        demosaic_cache_dir,
        tiff_compression,
        tiff_maxworkers,
    ) = job
    standard_without_input_profile = profile_path is None and is_generic_output_space(recipe.output_space)
    raw_decode_output_space = "camera_raw"
    if standard_without_input_profile and raw.suffix.lower() in RAW_EXTENSIONS:
        linear_audit = develop_scene_linear_array(raw, recipe, cache_dir=demosaic_cache_dir)
        render_linear = develop_standard_linear_array(raw, recipe, cache_dir=demosaic_cache_dir)
        raw_decode_output_space = canonical_generic_output_space(recipe.output_space) or str(recipe.output_space)
    else:
        render_linear = (
            develop_standard_linear_array(raw, recipe, cache_dir=demosaic_cache_dir)
            if standard_without_input_profile
            else develop_scene_linear_array(raw, recipe, cache_dir=demosaic_cache_dir)
        )
        linear_audit = render_linear
        if standard_without_input_profile:
            raw_decode_output_space = canonical_generic_output_space(recipe.output_space) or str(recipe.output_space)
    write_tiff16(out_linear, linear_audit)
    generic_profile_dir = out_final.parent / "_profiles"
    # Render final output from the in-memory array to avoid a second TIFF
    # quantization/read cycle. The audit TIFF is still written and hashed in
    # the manifest, preserving the forensic artifact.
    image = render_recipe_output_array(render_linear, recipe)
    write_mode, proof_result = write_signed_profiled_tiff(
        out_final,
        image,
        source_raw=raw,
        recipe=recipe,
        profile_path=profile_path,
        c2pa_config=c2pa_config,
        proof_config=proof_sign_config,
        render_context={"entrypoint": "batch_develop", "linear_audit_tiff": str(out_linear)},
        generic_profile_dir=generic_profile_dir,
        tiff_compression=tiff_compression,
        tiff_maxworkers=tiff_maxworkers,
    )
    rendered_profile_path = profile_path_for_render_settings(
        recipe,
        input_profile_path=profile_path,
        color_management_mode=write_mode,
        generic_profile_dir=generic_profile_dir,
    )
    raw_processing = None
    if raw.suffix.lower() in RAW_EXTENSIONS:
        raw_processing = effective_raw_processing_settings(
            recipe,
            output_color_space=raw_decode_output_space,
        )
    if raw.suffix.lower() in RAW_EXTENSIONS:
        write_raw_sidecar(
            raw,
            recipe=recipe,
            development_profile=None,
            detail_adjustments={},
            render_adjustments={},
            icc_profile_path=rendered_profile_path,
            color_management_mode=write_mode,
            output_tiff=out_final,
            proof_path=Path(proof_result.proof_path),
            source_sha256=proof_result.raw_sha256,
            raw_processing=raw_processing,
            status="rendered",
        )
    entry = BatchManifestEntry(
        source_raw=str(raw),
        source_sha256=proof_result.raw_sha256,
        output_tiff=str(out_final),
        output_sha256=proof_result.output_tiff_sha256,
        profile_path=str(rendered_profile_path or profile_path or ""),
        color_management_mode=color_mode,
        output_color_space=recipe.output_space,
        linear_audit_tiff=str(out_linear),
        proof_path=proof_result.proof_path,
        proof_sha256=proof_result.proof_sha256,
        c2pa_embedded=proof_result.c2pa_embedded,
    )
    return index, entry


def _requires_thread_batch_executor(c2pa_config: C2PASignConfig | None) -> bool:
    return bool(c2pa_config is not None and c2pa_config.client is not None)


def _resolve_demosaic_cache_dir(
    *,
    raws_dir: Path,
    out_dir: Path,
    configured: Path | None,
    recipe: Recipe,
) -> Path | None:
    if not bool(getattr(recipe, "use_cache", False)):
        return None
    if configured is not None:
        path = Path(configured).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    inferred = _infer_session_root(raws_dir) or _infer_session_root(out_dir)
    if inferred is not None:
        return session_cache_dir(inferred)
    path = Path.home() / ".probraw" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _infer_session_root(path: Path) -> Path | None:
    current = Path(path).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "00_configuraciones").exists() and (
            (candidate / "01_ORG").exists() or (candidate / "02_DRV").exists()
        ):
            return candidate
        if candidate.name in {"01_ORG", "02_DRV"} and candidate.parent.exists():
            return candidate.parent
    return None


def _read_positive_env_value(name: str, *, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError:
        return int(default)
    if value <= 0:
        return int(default)
    return int(value)


def _available_physical_memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:
            return None
        return None

    # Unix-like systems: prefer sysconf values when available.
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        avail_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        if page_size > 0 and avail_pages > 0:
            return int(page_size * avail_pages)
    except Exception:
        pass

    # Linux fallback.
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) * 1024
    except Exception:
        return None
    return None


def _versioned_batch_paths(
    out_dir: Path,
    linear_audit_dir: Path,
    stem: str,
    *,
    reserved_outputs: set[str] | None = None,
    reserved_audits: set[str] | None = None,
) -> tuple[Path, Path]:
    outputs = reserved_outputs if reserved_outputs is not None else set()
    audits = reserved_audits if reserved_audits is not None else set()
    for index in range(1, 10000):
        version = "" if index == 1 else f"_v{index:03d}"
        out_final = out_dir / f"{stem}{version}.tiff"
        out_linear = linear_audit_dir / f"{stem}{version}.scene_linear.tiff"
        key_final = str(out_final)
        key_linear = str(out_linear)
        if (
            not out_final.exists()
            and not out_linear.exists()
            and key_final not in outputs
            and key_linear not in audits
        ):
            outputs.add(key_final)
            audits.add(key_linear)
            return out_final, out_linear
    raise RuntimeError(f"No se pudo generar una version de salida libre para: {stem}")


def color_management_mode(recipe: Recipe) -> str:
    space = recipe.output_space.strip().lower()
    if space in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        return "camera_rgb_with_input_icc"
    generic_space = canonical_generic_output_space(space)
    if generic_space is not None:
        if recipe.output_linear:
            raise RuntimeError(
                f"output_space={recipe.output_space} requiere output_linear=false para usar "
                "un perfil ICC estandar de salida."
            )
        if generic_space == "srgb":
            return "converted_srgb"
        return f"converted_{generic_space}"
    raise RuntimeError(
        f"output_space no soportado para export ICC: {recipe.output_space!r}. "
        "Valores soportados: scene_linear_camera_rgb, camera_rgb, camera, srgb, adobe_rgb, prophoto_rgb."
    )


def color_management_mode_for_render(recipe: Recipe, *, profile_path: Path | None) -> str:
    if profile_path is not None:
        return color_management_mode(recipe)
    generic_space = canonical_generic_output_space(recipe.output_space)
    if generic_space is None:
        return "no_profile"
    if recipe.output_linear:
        raise RuntimeError(
            f"output_space={recipe.output_space} requiere output_linear=false para usar "
            "un perfil ICC estandar de salida."
        )
    return f"standard_{generic_space}_output_icc"


def write_profiled_tiff(
    out_tiff: Path,
    image_linear_rgb: np.ndarray,
    *,
    recipe: Recipe,
    profile_path: Path | None,
    generic_profile_dir: Path | None = None,
    tiff_compression: str | None = None,
    tiff_maxworkers: int | None = None,
) -> str:
    if profile_path is None:
        if is_generic_output_space(recipe.output_space):
            if recipe.output_linear:
                raise RuntimeError(
                    f"output_space={recipe.output_space} requiere output_linear=false para incrustar "
                    "un perfil ICC estandar de salida."
                )
            output_profile = ensure_generic_output_profile(recipe.output_space, directory=generic_profile_dir)
            space = generic_output_profile(recipe.output_space).key
            write_tiff16(
                out_tiff,
                image_linear_rgb,
                icc_profile=output_profile.read_bytes(),
                compression=tiff_compression,
                maxworkers=tiff_maxworkers,
            )
            return f"standard_{space}_output_icc"
        raise RuntimeError(
            f"output_space={recipe.output_space} requiere un perfil ICC de entrada activo. "
            "No se escribe TIFF RGB de camara sin perfil porque se vera verde/oscuro en visores externos. "
            "Genera o carga un ICC de sesion, o usa un espacio estandar como sRGB, Adobe RGB o ProPhoto "
            "con output_linear=false."
        )

    if not profile_path.exists():
        raise FileNotFoundError(f"No existe perfil ICC: {profile_path}")

    mode = color_management_mode(recipe)
    if mode == "camera_rgb_with_input_icc":
        write_tiff16(
            out_tiff,
            image_linear_rgb,
            icc_profile=profile_path.read_bytes(),
            compression=tiff_compression,
            maxworkers=tiff_maxworkers,
        )
        return mode

    if mode == "converted_srgb":
        _write_converted_output_tiff_with_argyll(
            out_tiff,
            image_linear_rgb,
            input_profile=profile_path,
            output_space="srgb",
            generic_profile_dir=generic_profile_dir,
            tiff_compression=tiff_compression,
            tiff_maxworkers=tiff_maxworkers,
        )
        return mode

    if mode.startswith("converted_"):
        output_space = mode.removeprefix("converted_")
        _write_converted_output_tiff_with_argyll(
            out_tiff,
            image_linear_rgb,
            input_profile=profile_path,
            output_space=output_space,
            generic_profile_dir=generic_profile_dir,
            tiff_compression=tiff_compression,
            tiff_maxworkers=tiff_maxworkers,
        )
        return mode

    raise RuntimeError(f"Modo de gestion de color no soportado: {mode}")


def write_signed_profiled_tiff(
    out_tiff: Path,
    image_linear_rgb: np.ndarray,
    *,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    c2pa_config: C2PASignConfig | None = None,
    proof_config: ProbRawProofConfig | None = None,
    detail_adjustments: dict[str, Any] | None = None,
    render_adjustments: dict[str, Any] | None = None,
    render_context: dict[str, Any] | None = None,
    generic_profile_dir: Path | None = None,
    tiff_compression: str | None = None,
    tiff_maxworkers: int | None = None,
) -> tuple[str, ProbRawProofResult]:
    proof_sign_config = proof_config or proof_config_from_environment()
    out_tiff = Path(out_tiff)
    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_tiff.stem}.probraw_", dir=out_tiff.parent) as tmp:
        staged_tiff = Path(tmp) / out_tiff.name
        mode = write_profiled_tiff(
            staged_tiff,
            image_linear_rgb,
            recipe=recipe,
            profile_path=profile_path,
            generic_profile_dir=generic_profile_dir,
            tiff_compression=tiff_compression,
            tiff_maxworkers=tiff_maxworkers,
        )
        rendered_profile_path = profile_path_for_render_settings(
            recipe,
            input_profile_path=profile_path,
            color_management_mode=mode,
            generic_profile_dir=generic_profile_dir,
        )
        enriched_context = dict(render_context or {})
        enriched_context["tiff_compression"] = tiff_compression_for_metadata(tiff_compression)
        resolved_tiff_maxworkers = resolve_tiff_maxworkers(tiff_maxworkers, compression=tiff_compression)
        if resolved_tiff_maxworkers is not None:
            enriched_context["tiff_maxworkers"] = resolved_tiff_maxworkers
        if _uses_input_profile_for_conversion(mode) and profile_path is not None:
            enriched_context["source_input_icc_path_auxiliary"] = str(profile_path)
            if profile_path.exists():
                enriched_context["source_input_icc_sha256"] = sha256_file(profile_path)
        settings = build_render_settings(
            recipe=recipe,
            profile_path=rendered_profile_path,
            color_management_mode=mode,
            detail_adjustments=detail_adjustments,
            render_adjustments=render_adjustments,
            context=enriched_context,
        )
        c2pa_status: dict[str, Any] = {"embedded": False, "status": "not_configured"}
        if c2pa_config is not None:
            try:
                c2pa_result = sign_tiff_with_c2pa(
                    staged_tiff,
                    source_raw=source_raw,
                    recipe=recipe,
                    profile_path=rendered_profile_path,
                    color_management_mode=mode,
                    config=c2pa_config,
                    render_settings=settings,
                )
                c2pa_status = {
                    "embedded": True,
                    "status": "signed",
                    "output_sha256_after_signing": c2pa_result.output_sha256_after_signing,
                }
                if c2pa_config.local_identity:
                    c2pa_status["identity"] = "local_self_issued"
            except C2PASigningError as exc:
                if c2pa_config.fail_on_error:
                    raise
                c2pa_status = {
                    "embedded": False,
                    "status": "local_c2pa_failed",
                    "identity": "local_self_issued" if c2pa_config.local_identity else "configured",
                    "error": str(exc),
                    "fallback": "probraw_proof",
                }
        shutil.move(str(staged_tiff), str(out_tiff))
        try:
            proof_result = sign_probraw_proof(
                output_tiff=out_tiff,
                source_raw=source_raw,
                recipe=recipe,
                profile_path=rendered_profile_path,
                color_management_mode=mode,
                render_settings=settings,
                config=proof_sign_config,
                c2pa_embedded=bool(c2pa_status.get("embedded")),
                c2pa_status=c2pa_status,
            )
        except Exception:
            out_tiff.unlink(missing_ok=True)
            default_proof = out_tiff.with_suffix(out_tiff.suffix + ".probraw.proof.json")
            default_proof.unlink(missing_ok=True)
            raise
        return mode, proof_result


def profile_path_for_render_settings(
    recipe: Recipe,
    *,
    input_profile_path: Path | None,
    color_management_mode: str,
    generic_profile_dir: Path | None = None,
) -> Path | None:
    if color_management_mode == "camera_rgb_with_input_icc":
        return input_profile_path
    if (
        color_management_mode.startswith("standard_")
        or color_management_mode.startswith("assigned_")
        or color_management_mode.startswith("converted_")
    ):
        if is_generic_output_space(recipe.output_space):
            return ensure_generic_output_profile(recipe.output_space, directory=generic_profile_dir)
    return None


def profile_role_for_color_management(color_management_mode: str, profile_path: Path | None) -> str | None:
    if profile_path is None:
        return None
    if color_management_mode == "camera_rgb_with_input_icc":
        return "session_input_icc"
    if (
        color_management_mode.startswith("standard_")
        or color_management_mode.startswith("assigned_")
        or color_management_mode.startswith("converted_")
    ):
        return "generic_output_icc"
    return "icc_profile"


def _uses_input_profile_for_conversion(color_management_mode: str) -> bool:
    return color_management_mode.startswith("converted_")


def _write_converted_srgb_tiff_with_argyll(out_tiff: Path, image_linear_rgb: np.ndarray, *, input_profile: Path) -> None:
    _write_converted_output_tiff_with_argyll(
        out_tiff,
        image_linear_rgb,
        input_profile=input_profile,
        output_space="srgb",
    )


def _write_converted_output_tiff_with_argyll(
    out_tiff: Path,
    image_linear_rgb: np.ndarray,
    *,
    input_profile: Path,
    output_space: str,
    generic_profile_dir: Path | None = None,
    tiff_compression: str | None = None,
    tiff_maxworkers: int | None = None,
) -> None:
    cctiff = external_tool_path("cctiff")
    if cctiff is None:
        raise RuntimeError(
            "No se puede convertir ICC: 'cctiff' de ArgyllCMS no esta disponible en PATH. "
            "Instala ArgyllCMS completo o configura su directorio bin."
        )
    output_icc = ensure_generic_output_profile(output_space, directory=generic_profile_dir)

    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="probraw_argyll_cctiff_") as tmp:
        tmpdir = Path(tmp)
        source_tiff = tmpdir / "camera_rgb_input.tiff"

        write_tiff16(source_tiff, image_linear_rgb)

        cmd = [
            cctiff,
            "-N",  # uncompressed TIFF, reproducible and readable without optional codecs
            "-p",  # precise correction path
            "-ir",
            str(input_profile),
            str(output_icc),
            "-e",
            str(output_icc),
            str(source_tiff),
            str(out_tiff),
        ]
        proc = run_external(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"cctiff retorno {proc.returncode}: {proc.stdout[-800:]}")
        rewrite_tiff_compression(out_tiff, tiff_compression, maxworkers=tiff_maxworkers)


def _argyll_reference_profile(name: str) -> Path:
    for folder in _argyll_reference_dirs():
        candidate = folder / name
        if candidate.exists():
            return candidate
    raise RuntimeError(f"No se encontro el perfil de referencia de ArgyllCMS: {name}")


def _argyll_reference_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("PROBRAW_ARGYLL_REF_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())

    for command in ("cctiff", "xicclu", "colprof"):
        tool = external_tool_path(command)
        if not tool:
            continue
        bin_dir = Path(tool).resolve().parent
        root_dir = bin_dir.parent
        dirs.extend(
            [
                root_dir / "ref",
                root_dir / "share" / "argyllcms" / "ref",
                root_dir / "share" / "color" / "argyll" / "ref",
                bin_dir / "ref",
            ]
        )

    dirs.extend(
        [
            Path("/usr/share/argyllcms/ref"),
            Path("/usr/share/color/argyll/ref"),
            Path("/usr/local/share/argyllcms/ref"),
            Path("/usr/local/share/color/argyll/ref"),
            Path("/opt/homebrew/share/argyllcms/ref"),
            Path("/opt/homebrew/share/color/argyll/ref"),
        ]
    )

    seen: set[Path] = set()
    out: list[Path] = []
    for folder in dirs:
        try:
            resolved = folder.resolve()
        except Exception:
            resolved = folder
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def apply_profile_matrix(
    image_linear_rgb: np.ndarray,
    matrix_camera_to_xyz: np.ndarray,
    output_space: str,
    output_linear: bool,
) -> np.ndarray:
    h, w, _ = image_linear_rgb.shape
    flat = image_linear_rgb.reshape(-1, 3).astype(np.float64)

    xyz = flat @ matrix_camera_to_xyz

    space = output_space.lower()
    if space in {"srgb", "s_rgb", "s-rgb"}:
        rgb = colour.XYZ_to_sRGB(
            xyz,
            illuminant=D50_XY,
            apply_cctf_encoding=(not output_linear),
        )
        out = np.clip(rgb, 0.0, 1.0)
    elif space in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        # Keep mapped XYZ projected back to linear sRGB primaries for practical TIFF export.
        rgb_linear = colour.XYZ_to_sRGB(xyz, illuminant=D50_XY, apply_cctf_encoding=False)
        out = np.clip(rgb_linear, 0.0, 1.0)
    else:
        rgb_linear = colour.XYZ_to_sRGB(xyz, illuminant=D50_XY, apply_cctf_encoding=(not output_linear))
        out = np.clip(rgb_linear, 0.0, 1.0)

    return out.reshape(h, w, 3).astype(np.float32)


# Backward-compat alias kept to avoid breaking external scripts that imported
# the previous private name before it was promoted to public API.
_apply_profile_matrix = apply_profile_matrix
