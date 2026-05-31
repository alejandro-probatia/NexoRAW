from __future__ import annotations

import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import subprocess
import sys
from collections.abc import Sequence
from typing import Any


def bundled_tool_dirs() -> list[Path | PurePosixPath]:
    dirs: list[Path | PurePosixPath] = []

    env_dir = os.environ.get("PROBRAW_TOOL_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())

    exe_dir = Path(sys.executable).resolve().parent
    dirs.extend(
        [
            exe_dir / "tools" / "bin",
            exe_dir / "tools" / "argyll" / "bin",
            exe_dir / "tools" / "exiftool",
        ]
    )

    base_dir = Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()
    dirs.extend(
        [
            base_dir / "tools" / "bin",
            base_dir / "tools" / "argyll" / "bin",
            base_dir / "tools" / "exiftool",
        ]
    )

    if sys.platform == "darwin":
        dirs.extend(
            [
                PurePosixPath("/opt/homebrew/bin"),
                PurePosixPath("/opt/homebrew/opt/argyll-cms/bin"),
                PurePosixPath("/usr/local/bin"),
                PurePosixPath("/usr/local/opt/argyll-cms/bin"),
                PurePosixPath("/opt/local/bin"),
            ]
        )
    elif sys.platform.startswith("linux"):
        dirs.append(PurePosixPath("/usr/bin/vendor_perl"))

    seen: set[str] = set()
    out: list[Path | PurePosixPath] = []
    for folder in dirs:
        key = folder.as_posix() if isinstance(folder, PurePosixPath) else str(folder.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            out.append(folder)
    return out


def external_tool_path(name: str) -> str | None:
    for folder in bundled_tool_dirs():
        folder_path = Path(str(folder))
        for candidate in _candidate_names(name):
            path = folder_path / candidate
            if path.exists() and path.is_file():
                return str(path)
    return shutil.which(name)


def external_tool_search_path() -> str:
    parts = [str(folder) for folder in bundled_tool_dirs() if Path(str(folder)).exists()]
    current = os.environ.get("PATH", "")
    return os.pathsep.join([*parts, current]) if parts else current


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return kwargs that keep external tools from flashing a console on Windows."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def run_external(command: Sequence[str] | str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(command, **_merge_hidden_subprocess_kwargs(kwargs))


def check_output_external(command: Sequence[str] | str, **kwargs: Any) -> str | bytes:
    return subprocess.check_output(command, **_merge_hidden_subprocess_kwargs(kwargs))


def _merge_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(kwargs)
    if os.name != "nt":
        return merged

    hidden = hidden_subprocess_kwargs()
    hidden_flags = int(hidden.get("creationflags", 0) or 0)
    current_flags = int(merged.get("creationflags", 0) or 0)
    merged["creationflags"] = current_flags | hidden_flags
    merged.setdefault("startupinfo", hidden.get("startupinfo"))
    return merged


def _candidate_names(name: str) -> list[str]:
    raw = str(name)
    names = [raw]
    if os.name == "nt" and Path(raw).suffix == "":
        names.append(f"{raw}.exe")
    return names
