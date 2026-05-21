from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib import request

from .version import __version__

DEFAULT_RELEASE_REPOSITORY = os.environ.get(
    "PROBRAW_RELEASE_REPOSITORY",
    "alejandro-probatia/ProbRAW",
).strip()
DEFAULT_RELEASE_API_URL = os.environ.get(
    "PROBRAW_RELEASE_API_URL",
    f"https://api.github.com/repos/{DEFAULT_RELEASE_REPOSITORY}/releases/latest",
).strip()


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str | None
    update_available: bool
    is_latest: bool | None
    repository: str
    release_url: str | None
    api_url: str
    asset_url: str | None
    asset_name: str | None
    asset_size: int | None
    asset_digest: str | None
    checksum_asset_url: str | None
    checksum_asset_name: str | None
    published_at: str | None
    error: str | None = None
    raw_payload: dict[str, Any] | None = None


def _normalize_version_text(value: str | None) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text


def _version_key(value: str | None) -> tuple[int, ...]:
    text = _normalize_version_text(value)
    parts = [int(p) for p in re.findall(r"\d+", text)]
    return tuple(parts)


def compare_versions(left: str | None, right: str | None) -> int:
    a = _version_key(left)
    b = _version_key(right)
    n = max(len(a), len(b))
    a_full = list(a) + [0] * (n - len(a))
    b_full = list(b) + [0] * (n - len(b))
    for av, bv in zip(a_full, b_full):
        if av < bv:
            return -1
        if av > bv:
            return 1
    return 0


def _asset_url(asset: dict[str, Any]) -> str:
    return str(asset.get("browser_download_url") or "")


def _asset_name(asset: dict[str, Any]) -> str:
    return str(asset.get("name") or "")


def _asset_size(asset: dict[str, Any]) -> int | None:
    try:
        size = int(asset.get("size"))
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _find_checksum_asset(assets: list[dict[str, Any]], asset_name: str) -> tuple[str | None, str | None]:
    expected = f"{asset_name}.sha256".lower()
    for asset in assets:
        name = _asset_name(asset)
        if name.lower() == expected:
            return name, _asset_url(asset)
    for asset in assets:
        name = _asset_name(asset)
        if name.lower().endswith(".sha256") and asset_name.lower() in name.lower():
            return name, _asset_url(asset)
    return None, None


def _is_checksum_or_metadata_asset(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return lowered.endswith((".sha256", ".sha256sum", ".asc", ".sig", ".txt", ".json"))


def _pick_asset(
    assets: list[dict[str, Any]],
) -> tuple[str | None, str | None, int | None, str | None, str | None, str | None]:
    if not assets:
        return None, None, None, None, None, None

    wanted_ext = _wanted_asset_extensions()
    candidates = [a for a in assets if _asset_url(a)]

    for ext in wanted_ext:
        for asset in candidates:
            name = _asset_name(asset)
            url = _asset_url(asset)
            if name.lower().endswith(ext):
                checksum_name, checksum_url = _find_checksum_asset(assets, name)
                return name, url, _asset_size(asset), str(asset.get("digest") or "") or None, checksum_name, checksum_url

    for asset in candidates:
        name = _asset_name(asset)
        if _is_checksum_or_metadata_asset(name):
            continue
        url = _asset_url(asset)
        checksum_name, checksum_url = _find_checksum_asset(assets, name)
        return name, url, _asset_size(asset), str(asset.get("digest") or "") or None, checksum_name, checksum_url
    return None, None, None, None, None, None


def _wanted_asset_extensions() -> list[str]:
    if sys.platform == "win32":
        return [".exe", ".msi"]
    if sys.platform == "darwin":
        return [".dmg", ".pkg", ".zip", ".tar.gz"]
    return [".deb", ".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar", ".rpm", ".appimage", ".tar.gz"]


def check_latest_release(*, api_url: str | None = None, repository: str | None = None, timeout: float = 8.0) -> UpdateCheckResult:
    api = str(api_url or DEFAULT_RELEASE_API_URL).strip()
    repo = str(repository or DEFAULT_RELEASE_REPOSITORY).strip()
    current = _normalize_version_text(__version__)
    req = request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ProbRAW/{current}",
        },
    )
    try:
        with request.urlopen(req, timeout=float(timeout)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return UpdateCheckResult(
            current_version=current,
            latest_version=None,
            update_available=False,
            is_latest=None,
            repository=repo,
            release_url=f"https://github.com/{repo}/releases",
            api_url=api,
            asset_url=None,
            asset_name=None,
            asset_size=None,
            asset_digest=None,
            checksum_asset_url=None,
            checksum_asset_name=None,
            published_at=None,
            error=str(exc),
        )

    tag = _normalize_version_text(str(payload.get("tag_name") or ""))
    release_url = str(payload.get("html_url") or f"https://github.com/{repo}/releases")
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    asset_name, asset_url, asset_size, asset_digest, checksum_name, checksum_url = _pick_asset(
        [a for a in assets if isinstance(a, dict)]
    )
    cmp = compare_versions(current, tag)
    update_available = bool(cmp < 0)
    is_latest = bool(cmp >= 0)
    return UpdateCheckResult(
        current_version=current,
        latest_version=tag or None,
        update_available=update_available,
        is_latest=is_latest,
        repository=repo,
        release_url=release_url,
        api_url=api,
        asset_url=asset_url,
        asset_name=asset_name,
        asset_size=asset_size,
        asset_digest=asset_digest,
        checksum_asset_url=checksum_url,
        checksum_asset_name=checksum_name,
        published_at=str(payload.get("published_at") or "") or None,
        error=None,
        raw_payload=payload,
    )


def default_update_download_dir() -> Path:
    home = Path.home().expanduser()
    downloads = home / "Downloads"
    base = downloads if downloads.exists() else home
    return base / "ProbRAW updates"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_sha256_digest(value: str | None) -> str | None:
    text = str(value or "").strip()
    if text.lower().startswith("sha256:"):
        text = text.split(":", 1)[1]
    match = re.search(r"\b[a-fA-F0-9]{64}\b", text)
    return match.group(0).lower() if match else None


def _download_url(url: str, out_path: Path, *, user_agent: str, timeout: float) -> None:
    req = request.Request(url, headers={"User-Agent": user_agent})
    with request.urlopen(req, timeout=float(timeout)) as response, out_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _read_checksum_url(url: str, *, user_agent: str, timeout: float) -> str:
    req = request.Request(url, headers={"User-Agent": user_agent})
    with request.urlopen(req, timeout=float(timeout)) as response:
        return response.read(4096).decode("utf-8", errors="replace")


def download_update_asset(
    result: UpdateCheckResult,
    *,
    target_dir: Path | None = None,
    timeout: float = 60.0,
    verify_checksum: bool = True,
) -> Path:
    if not result.asset_url:
        raise RuntimeError("La release no expone un asset descargable para esta plataforma.")
    dest_dir = Path(target_dir) if target_dir is not None else Path(tempfile.mkdtemp(prefix="probraw-update-"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = result.asset_name or Path(result.asset_url).name or "probraw-update.bin"
    out_path = dest_dir / name
    user_agent = f"ProbRAW/{result.current_version}"
    _download_url(result.asset_url, out_path, user_agent=user_agent, timeout=timeout)
    if verify_checksum:
        expected = _normalize_sha256_digest(result.asset_digest)
        checksum_text = ""
        if not expected and result.checksum_asset_url:
            checksum_text = _read_checksum_url(result.checksum_asset_url, user_agent=user_agent, timeout=timeout)
            expected = _normalize_sha256_digest(checksum_text)
            if result.checksum_asset_name:
                (dest_dir / result.checksum_asset_name).write_text(checksum_text, encoding="utf-8")
        if not expected:
            raise RuntimeError(
                "No se pudo verificar SHA-256 del instalador: "
                "la release no proporciona un digest valido."
            )
        actual = _sha256_file(out_path)
        if actual.lower() != expected.lower():
            raise RuntimeError(
                "La verificacion SHA-256 del instalador fallo: "
                f"esperado {expected}, obtenido {actual}."
            )
    return out_path


def launch_installer(path: Path, *, silent: bool = True) -> None:
    installer = Path(path).expanduser().resolve()
    suffix = installer.suffix.lower()
    name = installer.name.lower()
    if sys.platform == "win32":
        if suffix == ".msi":
            args = ["msiexec", "/i", str(installer)]
            if silent:
                args.extend(["/qn", "/norestart"])
            subprocess.Popen(args)
            return
        if suffix == ".exe":
            args = [str(installer)]
            if silent:
                args.extend(["/SP-", "/VERYSILENT", "/NORESTART"])
            subprocess.Popen(args)
            return
        os.startfile(str(installer))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(installer)])
        return
    if name.endswith((".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar")) and shutil.which("pacman"):
        args = ["pacman", "-U"]
        if silent:
            args.append("--noconfirm")
        args.append(str(installer))
        pkexec = shutil.which("pkexec")
        if pkexec and hasattr(os, "geteuid") and os.geteuid() != 0:
            args.insert(0, pkexec)
        subprocess.Popen(args)
        return
    if suffix == ".appimage":
        installer.chmod(installer.stat().st_mode | 0o111)
        subprocess.Popen([str(installer)])
        return
    subprocess.Popen(["xdg-open", str(installer)])


def auto_update(*, check: UpdateCheckResult, silent: bool = True, target_dir: Path | None = None) -> Path:
    installer = download_update_asset(check, target_dir=target_dir)
    launch_installer(installer, silent=silent)
    return installer
