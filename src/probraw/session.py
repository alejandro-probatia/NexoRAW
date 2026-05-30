from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SESSION_VERSION = 1
SESSION_FILE_RELATIVE_PATH = Path("00_configuraciones") / "session.json"
LEGACY_SESSION_FILE_RELATIVE_PATH = Path("config") / "session.json"

DEFAULT_SUBDIRECTORIES: dict[str, str] = {
    "config": "00_configuraciones",
    "raw": "01_ORG",
    "exports": "02_DRV",
    "charts": "01_ORG",
    "profiles": "00_configuraciones/profiles",
    "references": "00_configuraciones/references",
    "work": "00_configuraciones/work",
    "cache": "00_configuraciones/cache",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def session_file_path(root_dir: str | Path) -> Path:
    root = _as_path(root_dir)
    current = root / SESSION_FILE_RELATIVE_PATH
    legacy = root / LEGACY_SESSION_FILE_RELATIVE_PATH
    if not current.exists() and legacy.exists():
        return legacy
    return current


def ensure_session_structure(root_dir: str | Path) -> dict[str, Path]:
    root = _as_path(root_dir)
    root.mkdir(parents=True, exist_ok=True)

    directories: dict[str, Path] = {"root": root}
    for key, rel in DEFAULT_SUBDIRECTORIES.items():
        path = root / rel
        path.mkdir(parents=True, exist_ok=True)
        directories[key] = path
    return directories


def cache_dir(root_dir: str | Path, kind: str | None = None) -> Path:
    root = _as_path(root_dir)
    base = root / DEFAULT_SUBDIRECTORIES["cache"]
    path = base / str(kind).strip() if kind else base
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_session_name(root: Path) -> str:
    return root.name or "session"


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
        return True
    except Exception:
        return False


def _normalize_directories(payload: dict[str, Any], root: Path) -> dict[str, str]:
    normalized: dict[str, str] = {"root": str(root)}
    raw_dirs = payload if isinstance(payload, dict) else {}

    for key, rel in DEFAULT_SUBDIRECTORIES.items():
        raw_value = raw_dirs.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            if _foreign_absolute_path(raw_value):
                candidate = root / rel
            else:
                candidate = Path(raw_value).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
        else:
            candidate = root / rel

        if not _path_is_inside(candidate, root):
            candidate = root / rel

        candidate = candidate.resolve(strict=False)
        candidate.mkdir(parents=True, exist_ok=True)
        normalized[key] = str(candidate)

    return normalized


def _foreign_absolute_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if os.name != "nt":
        candidate = PureWindowsPath(text)
        return bool(candidate.drive)
    candidate = PurePosixPath(text)
    return candidate.is_absolute() and not Path(text).is_absolute()


def _normalize_metadata(payload: dict[str, Any], root: Path) -> dict[str, str]:
    now = _utc_now_iso()
    raw = payload if isinstance(payload, dict) else {}

    created_at = str(raw.get("created_at") or now)
    updated_at = str(raw.get("updated_at") or now)

    return {
        "name": str(raw.get("name") or _default_session_name(root)),
        "illumination_notes": str(raw.get("illumination_notes") or ""),
        "capture_notes": str(raw.get("capture_notes") or ""),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _normalize_queue(payload: Any) -> list[dict[str, str]]:
    queue: list[dict[str, str]] = []
    if not isinstance(payload, list):
        return queue

    for item in payload:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        queue.append(
            {
                "source": source,
                "development_profile_id": str(item.get("development_profile_id") or ""),
                "status": str(item.get("status") or "pending"),
                "output_tiff": str(item.get("output_tiff") or ""),
                "message": str(item.get("message") or ""),
            }
        )
    return queue


def _normalize_state(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def normalize_session_payload(payload: dict[str, Any], root_dir: str | Path) -> dict[str, Any]:
    root = _as_path(root_dir)
    ensure_session_structure(root)

    directories = _normalize_directories(payload.get("directories", {}), root)
    metadata = _normalize_metadata(payload.get("metadata", {}), root)
    state = _normalize_state(payload.get("state", {}))
    queue = _normalize_queue(payload.get("queue", []))

    return {
        "version": int(payload.get("version") or SESSION_VERSION),
        "metadata": metadata,
        "directories": directories,
        "state": state,
        "queue": queue,
    }


def save_session(root_dir: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_session_payload(payload, root_dir)
    normalized["metadata"]["updated_at"] = _utc_now_iso()

    path = session_file_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def load_session(root_dir: str | Path) -> dict[str, Any]:
    path = session_file_path(root_dir)
    if not path.exists():
        raise FileNotFoundError(f"No existe sesión en: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_session_payload(payload, root_dir)


def create_session(
    root_dir: str | Path,
    *,
    name: str | None = None,
    illumination_notes: str = "",
    capture_notes: str = "",
    state: dict[str, Any] | None = None,
    queue: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = _as_path(root_dir)
    now = _utc_now_iso()

    payload: dict[str, Any] = {
        "version": SESSION_VERSION,
        "metadata": {
            "name": name or _default_session_name(root),
            "illumination_notes": illumination_notes,
            "capture_notes": capture_notes,
            "created_at": now,
            "updated_at": now,
        },
        "directories": {},
        "state": state or {},
        "queue": queue or [],
    }
    return save_session(root, payload)
