from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from probraw.session import (
    DEFAULT_SUBDIRECTORIES,
    cache_dir,
    create_session,
    load_session,
    save_session,
    session_file_path,
)


def test_create_session_builds_required_structure(tmp_path: Path):
    root = tmp_path / "session_a"
    payload = create_session(
        root,
        name="Sesion A",
        illumination_notes="LED lateral",
        capture_notes="Trípode fijo",
    )

    assert payload["metadata"]["name"] == "Sesion A"
    assert payload["metadata"]["illumination_notes"] == "LED lateral"
    assert payload["metadata"]["capture_notes"] == "Trípode fijo"

    for key, rel in DEFAULT_SUBDIRECTORIES.items():
        folder = root / rel
        assert payload["directories"][key] == str(folder.resolve())
        assert folder.exists()
        assert folder.is_dir()

    assert session_file_path(root).exists()


def test_load_session_restores_queue_and_state(tmp_path: Path):
    root = tmp_path / "session_b"
    create_session(root, name="Sesion B")

    saved = save_session(
        root,
        {
            "metadata": {"name": "Sesion B"},
            "directories": {},
            "state": {"profile_active_path": "/tmp/profile.icc", "profile_min_confidence": 0.45},
            "queue": [
                {"source": "/tmp/a.raw", "status": "pending"},
                {"source": "/tmp/b.raw", "status": "done", "output_tiff": "/tmp/b.tiff", "development_profile_id": "manual-1"},
            ],
        },
    )

    loaded = load_session(root)
    assert loaded["state"]["profile_active_path"] == "/tmp/profile.icc"
    assert loaded["state"]["profile_min_confidence"] == 0.45
    assert len(loaded["queue"]) == 2
    assert loaded["queue"][1]["status"] == "done"
    assert loaded["queue"][1]["output_tiff"] == "/tmp/b.tiff"
    assert loaded["queue"][1]["development_profile_id"] == "manual-1"
    assert loaded["metadata"]["name"] == saved["metadata"]["name"]


def test_load_session_accepts_legacy_config_location(tmp_path: Path):
    root = tmp_path / "legacy_session"
    legacy_config = root / "config"
    legacy_config.mkdir(parents=True)
    legacy_session = legacy_config / "session.json"
    legacy_session.write_text(
        """
        {
          "version": 1,
          "metadata": {"name": "Legacy"},
          "directories": {"raw": "raw", "exports": "exports", "config": "config"},
          "state": {},
          "queue": []
        }
        """,
        encoding="utf-8",
    )

    assert session_file_path(root) == legacy_session.resolve()
    loaded = load_session(root)

    assert loaded["metadata"]["name"] == "Legacy"
    assert loaded["directories"]["raw"] == str((root / "raw").resolve())


def test_save_session_normalizes_invalid_queue_entries(tmp_path: Path):
    root = tmp_path / "session_c"
    create_session(root, name="Sesion C")

    payload = save_session(
        root,
        {
            "metadata": {"name": "Sesion C"},
            "directories": {},
            "state": {},
            "queue": [
                {"source": "", "status": "pending"},
                {"source": "/tmp/ok.raw"},
                "invalid",
            ],
        },
    )

    assert len(payload["queue"]) == 1
    assert payload["queue"][0]["source"] == "/tmp/ok.raw"
    assert payload["queue"][0]["status"] == "pending"


def test_cache_dir_creates_project_cache_subdirectory(tmp_path: Path):
    root = tmp_path / "session_cache"

    path = cache_dir(root, "demosaic")

    assert path == (root / "00_configuraciones" / "cache" / "demosaic").resolve()
    assert path.exists()
    assert path.is_dir()


def test_load_session_confines_same_platform_absolute_directories(tmp_path: Path):
    root = tmp_path / "session_external_path"
    create_session(root, name="External path")
    outside = tmp_path / "outside_profiles"
    session_file_path(root).write_text(
        f"""
        {{
          "version": 1,
          "metadata": {{"name": "External path"}},
          "directories": {{"profiles": {json.dumps(str(outside))}}},
          "state": {{}},
          "queue": []
        }}
        """,
        encoding="utf-8",
    )

    loaded = load_session(root)

    expected = (root / DEFAULT_SUBDIRECTORIES["profiles"]).resolve()
    assert loaded["directories"]["profiles"] == str(expected)
    assert not outside.exists()


@pytest.mark.skipif(os.name == "nt", reason="solo valida rutas absolutas Windows en hosts POSIX")
def test_load_session_does_not_create_foreign_windows_directories_on_posix(tmp_path: Path):
    root = tmp_path / "session_foreign_windows_path"
    create_session(root, name="Foreign Windows path")

    save_session(
        root,
        {
            "metadata": {"name": "Foreign Windows path"},
            "directories": {"profiles": r"C:\Users\Example\ProbRAW\profiles"},
            "state": {},
            "queue": [],
        },
    )

    loaded = load_session(root)

    expected = (root / DEFAULT_SUBDIRECTORIES["profiles"]).resolve()
    assert loaded["directories"]["profiles"] == str(expected)
    assert not (root / r"C:\Users\Example\ProbRAW\profiles").exists()


@pytest.mark.skipif(os.name != "nt", reason="solo valida rutas absolutas POSIX en hosts Windows")
def test_load_session_does_not_create_foreign_posix_directories_on_windows(tmp_path: Path):
    root = tmp_path / "session_foreign_posix_path"
    create_session(root, name="Foreign POSIX path")

    save_session(
        root,
        {
            "metadata": {"name": "Foreign POSIX path"},
            "directories": {"profiles": "/var/tmp/probraw/profiles"},
            "state": {},
            "queue": [],
        },
    )

    loaded = load_session(root)

    expected = (root / DEFAULT_SUBDIRECTORIES["profiles"]).resolve()
    assert loaded["directories"]["profiles"] == str(expected)
