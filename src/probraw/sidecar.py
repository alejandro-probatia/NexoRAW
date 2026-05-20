from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core.models import Recipe, read_json, write_json
from .core.utils import sha256_file
from .version import __version__


RAW_SIDECAR_SCHEMA = "org.probatia.probraw.raw-sidecar.v1"
LEGACY_RAW_SIDECAR_SCHEMAS = {
    "org.probatia.nexoraw.raw-sidecar.v1",
    "org.probatia.iccraw.raw-sidecar.v1",
}
RAW_SIDECAR_SUFFIX = ".probraw.json"
LEGACY_RAW_SIDECAR_SUFFIXES = (".nexoraw.json", ".iccraw.json")
RAW_SIDECAR_OUTPUT_LIMIT = 50


def raw_sidecar_path(source_path: Path) -> Path:
    source_path = Path(source_path)
    return source_path.with_name(source_path.name + RAW_SIDECAR_SUFFIX)


def load_raw_sidecar(source_path: Path) -> dict[str, Any]:
    path = _existing_raw_sidecar_path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe sidecar ProbRAW: {path}")
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def write_raw_sidecar(
    source_path: Path,
    *,
    recipe: Recipe,
    development_profile: dict[str, Any] | None = None,
    adjustment_profiles: dict[str, Any] | None = None,
    detail_adjustments: dict[str, Any] | None = None,
    render_adjustments: dict[str, Any] | None = None,
    icc_profile_path: Path | None = None,
    color_management_mode: str | None = None,
    session_root: Path | None = None,
    session_name: str | None = None,
    output_tiff: Path | None = None,
    proof_path: Path | None = None,
    source_sha256: str | None = None,
    raw_processing: dict[str, Any] | None = None,
    status: str = "configured",
) -> Path:
    source_path = Path(source_path).expanduser()
    sidecar_path = raw_sidecar_path(source_path)
    existing = _load_existing_payload(_existing_raw_sidecar_path(source_path))
    now = _utc_now_iso()

    outputs = list(existing.get("outputs") or []) if isinstance(existing.get("outputs"), list) else []
    mtf_analysis = existing.get("mtf_analysis") if isinstance(existing.get("mtf_analysis"), dict) else None
    existing_raw_processing = existing.get("raw_processing") if isinstance(existing.get("raw_processing"), dict) else None
    stored_adjustment_profiles = (
        adjustment_profiles
        if isinstance(adjustment_profiles, dict)
        else existing.get("adjustment_profiles") if isinstance(existing.get("adjustment_profiles"), dict) else {}
    )
    if output_tiff is not None:
        outputs.append(
            {
                "rendered_at": now,
                "tiff_path": _stored_path(output_tiff, session_root),
                "proof_path": _stored_path(proof_path, session_root) if proof_path is not None else "",
                "color_management_mode": color_management_mode or "",
            }
        )
        outputs = outputs[-RAW_SIDECAR_OUTPUT_LIMIT:]

    payload: dict[str, Any] = {
        "schema": RAW_SIDECAR_SCHEMA,
        "schema_version": 1,
        "software": {
            "name": "ProbRAW",
            "version": __version__,
        },
        "status": status,
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
        "session": {
            "name": session_name or "",
            "root_path": str(Path(session_root).expanduser()) if session_root is not None else "",
        },
        "source": _source_payload(
            source_path,
            session_root,
            existing_source=existing.get("source") if isinstance(existing.get("source"), dict) else None,
            source_sha256=source_sha256,
        ),
        "development_profile": _development_profile_payload(development_profile),
        "adjustment_profiles": _adjustment_profiles_payload(stored_adjustment_profiles),
        "recipe": asdict(recipe),
        "detail_adjustments": detail_adjustments or {},
        "render_adjustments": render_adjustments or {},
        "color_management": _color_management_payload(
            icc_profile_path=icc_profile_path,
            color_management_mode=color_management_mode,
            session_root=session_root,
        ),
        "outputs": outputs,
    }
    if isinstance(raw_processing, dict):
        payload["raw_processing"] = raw_processing
    elif existing_raw_processing is not None:
        payload["raw_processing"] = existing_raw_processing
    if mtf_analysis is not None:
        payload["mtf_analysis"] = mtf_analysis
    write_json(sidecar_path, payload)
    return sidecar_path


def write_raw_mtf_analysis(
    source_path: Path,
    mtf_payload: dict[str, Any],
    *,
    session_root: Path | None = None,
    session_name: str | None = None,
) -> Path:
    source_path = Path(source_path).expanduser()
    sidecar_path = raw_sidecar_path(source_path)
    existing = _load_existing_payload(_existing_raw_sidecar_path(source_path))
    now = _utc_now_iso()

    payload = dict(existing) if existing else {}
    payload["schema"] = RAW_SIDECAR_SCHEMA
    payload["schema_version"] = 1
    payload["software"] = {
        "name": "ProbRAW",
        "version": __version__,
    }
    payload["status"] = str(payload.get("status") or "configured")
    payload["created_at"] = str(payload.get("created_at") or now)
    payload["updated_at"] = now

    session_payload = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    if session_name is not None:
        session_payload["name"] = session_name
    session_payload.setdefault("name", "")
    if session_root is not None:
        session_payload["root_path"] = str(Path(session_root).expanduser())
    session_payload.setdefault("root_path", "")
    payload["session"] = session_payload

    source_payload = _source_payload(source_path, session_root, hash_file=False)
    existing_source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if existing_source.get("sha256"):
        source_payload["sha256"] = existing_source.get("sha256")
    payload["source"] = source_payload

    if not isinstance(payload.get("outputs"), list):
        payload["outputs"] = []
    payload["mtf_analysis"] = mtf_payload

    write_json(sidecar_path, payload)
    return sidecar_path


def _existing_raw_sidecar_path(source_path: Path) -> Path:
    path = raw_sidecar_path(source_path)
    if path.exists():
        return path
    source_path = Path(source_path)
    for suffix in LEGACY_RAW_SIDECAR_SUFFIXES:
        legacy = source_path.with_name(source_path.name + suffix)
        if legacy.exists():
            return legacy
    return path


def _load_existing_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = read_json(path)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _source_payload(
    source_path: Path,
    session_root: Path | None,
    *,
    hash_file: bool = True,
    existing_source: dict[str, Any] | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "basename": source_path.name,
        "path": _stored_path(source_path, session_root),
        "relative_path": _relative_path(source_path, session_root),
        "sha256": None,
        "size_bytes": None,
        "mtime_ns": None,
    }
    if source_path.exists() and source_path.is_file():
        stat = source_path.stat()
        payload["size_bytes"] = int(stat.st_size)
        payload["mtime_ns"] = int(stat.st_mtime_ns)
        if source_sha256:
            payload["sha256"] = str(source_sha256)
        elif hash_file:
            payload["sha256"] = _reusable_source_sha256(existing_source, stat) or sha256_file(source_path)
    return payload


def _reusable_source_sha256(existing_source: dict[str, Any] | None, stat: Any) -> str | None:
    if not isinstance(existing_source, dict):
        return None
    digest = existing_source.get("sha256")
    if not digest:
        return None
    try:
        if int(existing_source.get("size_bytes")) != int(stat.st_size):
            return None
        if int(existing_source.get("mtime_ns")) != int(stat.st_mtime_ns):
            return None
    except Exception:
        return None
    return str(digest)


def _development_profile_payload(profile: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(profile, dict):
        return {"id": "", "name": "", "kind": "", "profile_type": ""}
    profile_type = str(profile.get("profile_type") or "").strip().lower()
    if profile_type not in {"advanced", "basic"}:
        kind = str(profile.get("kind") or "").strip().lower()
        profile_type = "advanced" if kind in {"chart", "advanced"} else "basic"
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or ""),
        "kind": str(profile.get("kind") or ""),
        "profile_type": profile_type,
    }


def _adjustment_profiles_payload(profiles: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ("icc", "color_contrast", "detail", "raw_export"):
        value = profiles.get(key) if isinstance(profiles, dict) else None
        if isinstance(value, dict):
            payload[key] = {
                "id": str(value.get("id") or ""),
                "name": str(value.get("name") or ""),
                "kind": str(value.get("kind") or key),
            }
        else:
            payload[key] = {"id": "", "name": "", "kind": key}
    return payload


def _color_management_payload(
    *,
    icc_profile_path: Path | None,
    color_management_mode: str | None,
    session_root: Path | None,
) -> dict[str, Any]:
    mode = color_management_mode or "no_profile"
    payload: dict[str, Any] = {
        "mode": mode,
        "icc_profile_role": _icc_profile_role(mode, icc_profile_path) or "",
        "icc_profile_path": _stored_path(icc_profile_path, session_root) if icc_profile_path is not None else "",
        "icc_profile_sha256": None,
    }
    if icc_profile_path is not None and Path(icc_profile_path).exists():
        payload["icc_profile_sha256"] = sha256_file(Path(icc_profile_path))
    return payload


def _icc_profile_role(color_management_mode: str, icc_profile_path: Path | None) -> str | None:
    if icc_profile_path is None:
        return None
    mode = str(color_management_mode or "")
    if mode == "camera_rgb_with_input_icc":
        return "session_input_icc"
    if mode.startswith("standard_") or mode.startswith("assigned_") or mode.startswith("converted_"):
        return "generic_output_icc"
    return "icc_profile"


def _stored_path(path: Path | None, session_root: Path | None) -> str:
    if path is None:
        return ""
    relative = _relative_path(path, session_root)
    return relative or str(Path(path).expanduser())


def _relative_path(path: Path | None, session_root: Path | None) -> str:
    if path is None or session_root is None:
        return ""
    try:
        root = Path(session_root).expanduser().resolve(strict=False)
        resolved = Path(path).expanduser().resolve(strict=False)
        return resolved.relative_to(root).as_posix()
    except Exception:
        return ""
