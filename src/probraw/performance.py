from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
from typing import Any


POLICY_VERSION = 1
SYSTEM_CONFIG_PATH = Path("/etc/probraw/performance.json")
CONFIG_PATH_ENV = "PROBRAW_PERFORMANCE_CONFIG"
MODE_ENV = "PROBRAW_PERFORMANCE_MODE"
FORCE_ENV = "PROBRAW_PERFORMANCE_FORCE"
DISABLE_ENV = "PROBRAW_DISABLE_PERFORMANCE_CONFIG"
NATIVE_THREADS_ENV = "PROBRAW_NATIVE_THREADS"
OPENCV_THREADS_ENV = "PROBRAW_OPENCV_THREADS"
BATCH_NATIVE_THREADS_ENV = "PROBRAW_BATCH_NATIVE_THREADS"
BLAS_THREADS_ENV = "PROBRAW_BLAS_THREADS"
CONFIGURED_ENV_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    NATIVE_THREADS_ENV,
    OPENCV_THREADS_ENV,
    BATCH_NATIVE_THREADS_ENV,
    BLAS_THREADS_ENV,
)
_RUNTIME_POLICY: PerformancePolicy | None = None
_OPENCV_CONFIGURED = False


@dataclass(frozen=True)
class HardwareInfo:
    cpu_count: int
    affinity_count: int
    architecture: str
    machine: str
    processor: str
    cpu_model: str
    total_memory_bytes: int | None
    available_memory_bytes: int | None
    platform: str

    @property
    def usable_cpus(self) -> int:
        return max(1, int(self.affinity_count or self.cpu_count or 1))

    @property
    def signature(self) -> str:
        rounded_memory_gib = 0
        if self.total_memory_bytes:
            rounded_memory_gib = int(round(self.total_memory_bytes / (1024 ** 3)))
        payload = {
            "architecture": self.architecture,
            "machine": self.machine,
            "processor": self.processor,
            "cpu_model": self.cpu_model,
            "usable_cpus": self.usable_cpus,
            "memory_gib": rounded_memory_gib,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class PerformancePolicy:
    policy_version: int
    mode: str
    usable_cpus: int
    native_threads: int
    opencv_threads: int
    blas_threads: int
    batch_native_threads: int
    interactive_worker_cap: int
    batch_worker_cap: int
    memory_gib: float | None
    hardware_signature: str

    def environment(self) -> dict[str, str]:
        return {
            "OMP_NUM_THREADS": str(self.native_threads),
            "OPENBLAS_NUM_THREADS": str(self.blas_threads),
            "MKL_NUM_THREADS": str(self.blas_threads),
            "NUMEXPR_NUM_THREADS": str(self.blas_threads),
            NATIVE_THREADS_ENV: str(self.native_threads),
            OPENCV_THREADS_ENV: str(self.opencv_threads),
            BATCH_NATIVE_THREADS_ENV: str(self.batch_native_threads),
            BLAS_THREADS_ENV: str(self.blas_threads),
        }


def detect_hardware() -> HardwareInfo:
    cpu_count = max(1, int(os.cpu_count() or 1))
    affinity_count = cpu_count
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity_count = max(1, len(os.sched_getaffinity(0)))
        except Exception:
            affinity_count = cpu_count
    total, available = _linux_memory_bytes()
    return HardwareInfo(
        cpu_count=cpu_count,
        affinity_count=affinity_count,
        architecture=platform.architecture()[0] or "",
        machine=platform.machine() or "",
        processor=platform.processor() or "",
        cpu_model=_linux_cpu_model(),
        total_memory_bytes=total,
        available_memory_bytes=available,
        platform=platform.platform(),
    )


def recommend_policy(
    hardware: HardwareInfo | None = None,
    *,
    mode: str | None = None,
) -> PerformancePolicy:
    hw = hardware or detect_hardware()
    normalized_mode = _normalize_mode(mode or os.environ.get(MODE_ENV) or "balanced")
    cpus = hw.usable_cpus
    memory_gib = None if hw.total_memory_bytes is None else hw.total_memory_bytes / float(1024 ** 3)
    factor = {"conservative": 0.50, "balanced": 0.65, "aggressive": 0.85}.get(normalized_mode, 0.65)
    max_cap = {"conservative": 6, "balanced": 12, "aggressive": 16}.get(normalized_mode, 12)
    memory_cap = _thread_memory_cap(memory_gib, mode=normalized_mode)
    cpu_target = max(1, int(round(cpus * factor)))
    reserve_cap = max(1, cpus - 1) if cpus > 2 else 1
    native_threads = max(1, min(cpu_target, memory_cap, reserve_cap, max_cap))
    if normalized_mode == "aggressive" and cpus <= 4:
        native_threads = max(1, min(cpus, memory_cap, max_cap))

    native_threads = _env_positive_int(NATIVE_THREADS_ENV, native_threads)
    opencv_threads = _env_positive_int(OPENCV_THREADS_ENV, min(native_threads, max(1, cpus)))
    blas_threads = _env_positive_int(BLAS_THREADS_ENV, max(1, min(4, native_threads)))
    batch_native_threads = _env_positive_int(
        BATCH_NATIVE_THREADS_ENV,
        max(1, min(native_threads, max(1, int(round(cpus / 3.0))) if cpus >= 8 else native_threads)),
    )
    batch_worker_cap = max(1, min(cpus, cpus // max(1, batch_native_threads)))
    interactive_worker_cap = max(1, min(16, max(1, cpus - 1), memory_cap))
    return PerformancePolicy(
        policy_version=POLICY_VERSION,
        mode=normalized_mode,
        usable_cpus=cpus,
        native_threads=max(1, native_threads),
        opencv_threads=max(1, opencv_threads),
        blas_threads=max(1, blas_threads),
        batch_native_threads=max(1, batch_native_threads),
        interactive_worker_cap=max(1, interactive_worker_cap),
        batch_worker_cap=max(1, batch_worker_cap),
        memory_gib=memory_gib,
        hardware_signature=hw.signature,
    )


def configure_runtime(*, configure_opencv: bool = True) -> PerformancePolicy:
    global _OPENCV_CONFIGURED, _RUNTIME_POLICY
    if _RUNTIME_POLICY is not None:
        if configure_opencv and not _OPENCV_CONFIGURED:
            _configure_opencv_threads(_env_positive_int(OPENCV_THREADS_ENV, _RUNTIME_POLICY.opencv_threads))
            _OPENCV_CONFIGURED = True
        return _RUNTIME_POLICY
    if _env_flag(DISABLE_ENV, default=False):
        _RUNTIME_POLICY = recommend_policy()
        return _RUNTIME_POLICY

    policy = load_configured_policy() or recommend_policy()
    force = _env_flag(FORCE_ENV, default=False)
    for key, value in policy.environment().items():
        if force or not str(os.environ.get(key, "")).strip():
            os.environ[key] = value
    if configure_opencv:
        _configure_opencv_threads(_env_positive_int(OPENCV_THREADS_ENV, policy.opencv_threads))
        _OPENCV_CONFIGURED = True
    _RUNTIME_POLICY = policy
    return policy


def load_configured_policy() -> PerformancePolicy | None:
    if str(os.environ.get(MODE_ENV, "")).strip():
        return None
    path = configured_policy_path()
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if int(payload.get("policy_version", 0) or 0) != POLICY_VERSION:
        return None
    hardware = detect_hardware()
    if str(payload.get("hardware_signature") or "") != hardware.signature:
        return None
    policy_payload = payload.get("policy")
    if not isinstance(policy_payload, dict):
        return None
    try:
        return PerformancePolicy(
            policy_version=POLICY_VERSION,
            mode=str(policy_payload.get("mode") or "balanced"),
            usable_cpus=max(1, int(policy_payload.get("usable_cpus") or hardware.usable_cpus)),
            native_threads=max(1, int(policy_payload.get("native_threads") or 1)),
            opencv_threads=max(1, int(policy_payload.get("opencv_threads") or 1)),
            blas_threads=max(1, int(policy_payload.get("blas_threads") or 1)),
            batch_native_threads=max(1, int(policy_payload.get("batch_native_threads") or 1)),
            interactive_worker_cap=max(1, int(policy_payload.get("interactive_worker_cap") or 1)),
            batch_worker_cap=max(1, int(policy_payload.get("batch_worker_cap") or 1)),
            memory_gib=policy_payload.get("memory_gib"),
            hardware_signature=hardware.signature,
        )
    except Exception:
        return None


def configured_policy_path() -> Path | None:
    raw = os.environ.get(CONFIG_PATH_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    return SYSTEM_CONFIG_PATH


def write_performance_config(
    path: Path,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    hardware = detect_hardware()
    policy = recommend_policy(hardware, mode=mode)
    payload = {
        "schema": "probraw-performance-policy",
        "policy_version": POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "managed_by": "probraw",
        "hardware_signature": hardware.signature,
        "hardware": asdict(hardware),
        "policy": asdict(policy),
        "environment": policy.environment(),
    }
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def performance_report(*, mode: str | None = None) -> dict[str, Any]:
    hardware = detect_hardware()
    configured = load_configured_policy()
    recommended = recommend_policy(hardware, mode=mode)
    active = configured or recommended
    return {
        "hardware": asdict(hardware),
        "hardware_signature": hardware.signature,
        "configured_policy_path": str(configured_policy_path() or ""),
        "configured_policy_loaded": configured is not None,
        "recommended_policy": asdict(recommended),
        "active_policy": asdict(active),
        "environment": {
            key: os.environ.get(key)
            for key in CONFIGURED_ENV_KEYS
            if os.environ.get(key) is not None
        },
    }


def available_cpu_count() -> int:
    return detect_hardware().usable_cpus


def interactive_worker_cap() -> int:
    return configure_runtime(configure_opencv=False).interactive_worker_cap


def batch_worker_cap(available_cpus: int | None = None) -> int:
    policy = configure_runtime(configure_opencv=False)
    cpus = max(1, int(available_cpus or policy.usable_cpus))
    return max(1, min(cpus, policy.batch_worker_cap))


def _thread_memory_cap(memory_gib: float | None, *, mode: str) -> int:
    if memory_gib is None:
        return 12 if mode != "conservative" else 6
    if memory_gib < 6:
        return 1
    if memory_gib < 10:
        return 2
    if memory_gib < 16:
        return 4 if mode == "conservative" else 6
    if memory_gib < 32:
        return 8 if mode != "conservative" else 6
    if memory_gib < 64:
        return 10 if mode == "balanced" else (8 if mode == "conservative" else 14)
    return 12 if mode != "aggressive" else 16


def _linux_memory_bytes() -> tuple[int | None, int | None]:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None, None
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            key, _, rest = line.partition(":")
            parts = rest.strip().split()
            if not parts:
                continue
            values[key] = int(parts[0]) * 1024
    except Exception:
        return None, None
    return values.get("MemTotal"), values.get("MemAvailable")


def _linux_cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if not path.exists():
        return ""
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() in {"model name", "hardware"} and value.strip():
                return value.strip()
    except Exception:
        return ""
    return ""


def _configure_opencv_threads(threads: int) -> None:
    try:
        import cv2

        cv2.setNumThreads(max(1, int(threads)))
    except Exception:
        return


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return max(1, int(default))
    try:
        value = int(raw)
    except Exception:
        return max(1, int(default))
    return max(1, value)


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _normalize_mode(mode: str) -> str:
    value = str(mode or "balanced").strip().lower()
    if value in {"safe", "low", "conservative"}:
        return "conservative"
    if value in {"fast", "high", "aggressive"}:
        return "aggressive"
    return "balanced"
