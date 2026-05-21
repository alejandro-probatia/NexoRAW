from __future__ import annotations

from dataclasses import asdict
import hashlib
import io
import json

import probraw.update as update_mod


def test_compare_versions_with_revision_suffix() -> None:
    assert update_mod.compare_versions("0.2.0-r1", "0.2.0") > 0
    assert update_mod.compare_versions("v0.2.1", "0.2.0-r9") > 0
    assert update_mod.compare_versions("0.2.0", "0.2.0") == 0


def test_check_latest_release_network_error(monkeypatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(update_mod.request, "urlopen", raise_error)
    result = update_mod.check_latest_release()
    assert result.error is not None
    assert result.update_available is False
    assert result.is_latest is None


def test_check_latest_release_payload(monkeypatch) -> None:
    installer = b"fake installer"
    digest = hashlib.sha256(installer).hexdigest()
    payload = {
        "tag_name": "v0.2.9",
        "html_url": "https://example.com/release",
        "published_at": "2026-04-27T10:00:00Z",
        "assets": [
            {
                "name": "ProbRAW-0.2.9-Setup.exe",
                "browser_download_url": "https://example.com/ProbRAW-0.2.9-Setup.exe",
                "size": len(installer),
                "digest": f"sha256:{digest}",
            },
            {
                "name": "ProbRAW-0.2.9-Setup.exe.sha256",
                "browser_download_url": "https://example.com/ProbRAW-0.2.9-Setup.exe.sha256",
            }
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()
    serialized = asdict(result)
    assert serialized["latest_version"] == "0.2.9"
    assert serialized["release_url"] == "https://example.com/release"
    assert serialized["asset_name"] == "ProbRAW-0.2.9-Setup.exe"
    assert serialized["asset_url"] == "https://example.com/ProbRAW-0.2.9-Setup.exe"
    assert serialized["asset_size"] == len(installer)
    assert serialized["asset_digest"] == f"sha256:{digest}"
    assert serialized["checksum_asset_name"] == "ProbRAW-0.2.9-Setup.exe.sha256"
    assert serialized["checksum_asset_url"] == "https://example.com/ProbRAW-0.2.9-Setup.exe.sha256"
    assert serialized["error"] is None


def test_download_update_asset_verifies_checksum_asset(monkeypatch, tmp_path) -> None:
    installer = b"fake installer"
    digest = hashlib.sha256(installer).hexdigest()
    check = update_mod.UpdateCheckResult(
        current_version="0.2.8",
        latest_version="0.2.9",
        update_available=True,
        is_latest=False,
        repository="example/repo",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe",
        asset_name="ProbRAW-0.2.9-Setup.exe",
        asset_size=len(installer),
        asset_digest=None,
        checksum_asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe.sha256",
        checksum_asset_name="ProbRAW-0.2.9-Setup.exe.sha256",
        published_at="2026-04-27T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(req, **_kwargs):
        url = req.full_url
        if url.endswith(".sha256"):
            return _FakeResponse(f"{digest}  ProbRAW-0.2.9-Setup.exe\n".encode("utf-8"))
        return _FakeResponse(installer)

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)

    path = update_mod.download_update_asset(check, target_dir=tmp_path)

    assert path.name == "ProbRAW-0.2.9-Setup.exe"
    assert path.read_bytes() == installer
    assert (tmp_path / "ProbRAW-0.2.9-Setup.exe.sha256").is_file()


def test_download_update_asset_rejects_checksum_mismatch(monkeypatch, tmp_path) -> None:
    installer = b"fake installer"
    check = update_mod.UpdateCheckResult(
        current_version="0.2.8",
        latest_version="0.2.9",
        update_available=True,
        is_latest=False,
        repository="example/repo",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe",
        asset_name="ProbRAW-0.2.9-Setup.exe",
        asset_size=len(installer),
        asset_digest="sha256:" + ("0" * 64),
        checksum_asset_url=None,
        checksum_asset_name=None,
        published_at="2026-04-27T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(update_mod.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(installer))

    try:
        update_mod.download_update_asset(check, target_dir=tmp_path)
    except RuntimeError as exc:
        assert "SHA-256" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("checksum mismatch should fail")


def test_download_update_asset_requires_valid_checksum_when_enabled(monkeypatch, tmp_path) -> None:
    installer = b"fake installer"
    check = update_mod.UpdateCheckResult(
        current_version="0.2.8",
        latest_version="0.2.9",
        update_available=True,
        is_latest=False,
        repository="example/repo",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe",
        asset_name="ProbRAW-0.2.9-Setup.exe",
        asset_size=len(installer),
        asset_digest=None,
        checksum_asset_url=None,
        checksum_asset_name=None,
        published_at="2026-04-27T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(update_mod.request, "urlopen", lambda *_args, **_kwargs: _FakeResponse(installer))

    try:
        update_mod.download_update_asset(check, target_dir=tmp_path)
    except RuntimeError as exc:
        assert "SHA-256" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing checksum should fail closed")


def test_download_update_asset_rejects_invalid_checksum_body(monkeypatch, tmp_path) -> None:
    installer = b"fake installer"
    check = update_mod.UpdateCheckResult(
        current_version="0.2.8",
        latest_version="0.2.9",
        update_available=True,
        is_latest=False,
        repository="example/repo",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe",
        asset_name="ProbRAW-0.2.9-Setup.exe",
        asset_size=len(installer),
        asset_digest=None,
        checksum_asset_url="https://example.com/ProbRAW-0.2.9-Setup.exe.sha256",
        checksum_asset_name="ProbRAW-0.2.9-Setup.exe.sha256",
        published_at="2026-04-27T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(req, **_kwargs):
        if req.full_url.endswith(".sha256"):
            return _FakeResponse(b"<html>not a checksum</html>")
        return _FakeResponse(installer)

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)

    try:
        update_mod.download_update_asset(check, target_dir=tmp_path)
    except RuntimeError as exc:
        assert "SHA-256" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid checksum body should fail closed")


def test_pick_asset_fallback_skips_metadata_assets(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "win32")
    assets = [
        {
            "name": "release.json",
            "browser_download_url": "https://example.com/release.json",
            "size": 12,
        },
        {
            "name": "notes.txt",
            "browser_download_url": "https://example.com/notes.txt",
            "size": 12,
        },
        {
            "name": "ProbRAW-portable.zip",
            "browser_download_url": "https://example.com/ProbRAW-portable.zip",
            "size": 123,
        },
    ]

    name, url, size, _digest, _checksum_name, _checksum_url = update_mod._pick_asset(assets)

    assert name == "ProbRAW-portable.zip"
    assert url == "https://example.com/ProbRAW-portable.zip"
    assert size == 123


def test_pick_asset_prefers_macos_zip_over_source_tarball(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "darwin")
    assets = [
        {
            "name": "probraw-0.3.18.tar.gz",
            "browser_download_url": "https://example.com/probraw-0.3.18.tar.gz",
            "size": 10,
        },
        {
            "name": "ProbRAW-0.3.18-macos-arm64.zip",
            "browser_download_url": "https://example.com/ProbRAW-0.3.18-macos-arm64.zip",
            "size": 123,
        },
        {
            "name": "ProbRAW-0.3.18-macos-arm64.zip.sha256",
            "browser_download_url": "https://example.com/ProbRAW-0.3.18-macos-arm64.zip.sha256",
        },
    ]

    name, url, size, _digest, checksum_name, checksum_url = update_mod._pick_asset(assets)

    assert name == "ProbRAW-0.3.18-macos-arm64.zip"
    assert url == "https://example.com/ProbRAW-0.3.18-macos-arm64.zip"
    assert size == 123
    assert checksum_name == "ProbRAW-0.3.18-macos-arm64.zip.sha256"
    assert checksum_url == "https://example.com/ProbRAW-0.3.18-macos-arm64.zip.sha256"


def test_pick_asset_prefers_arch_package_over_python_source_tarball(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    assets = [
        {
            "name": "probraw-0.4.0-py3-none-any.whl",
            "browser_download_url": "https://example.com/probraw-0.4.0-py3-none-any.whl",
            "size": 10,
        },
        {
            "name": "ProbRAW-0.4.0-Setup.exe",
            "browser_download_url": "https://example.com/ProbRAW-0.4.0-Setup.exe",
            "size": 20,
        },
        {
            "name": "probraw-0.4.0.tar.gz",
            "browser_download_url": "https://example.com/probraw-0.4.0.tar.gz",
            "size": 30,
        },
        {
            "name": "probraw-0.4.0-1-x86_64.pkg.tar.zst",
            "browser_download_url": "https://example.com/probraw-0.4.0-1-x86_64.pkg.tar.zst",
            "size": 123,
        },
        {
            "name": "probraw-0.4.0-1-x86_64.pkg.tar.zst.sha256",
            "browser_download_url": "https://example.com/probraw-0.4.0-1-x86_64.pkg.tar.zst.sha256",
        },
    ]

    name, url, size, _digest, checksum_name, checksum_url = update_mod._pick_asset(assets)

    assert name == "probraw-0.4.0-1-x86_64.pkg.tar.zst"
    assert url == "https://example.com/probraw-0.4.0-1-x86_64.pkg.tar.zst"
    assert size == 123
    assert checksum_name == "probraw-0.4.0-1-x86_64.pkg.tar.zst.sha256"
    assert checksum_url == "https://example.com/probraw-0.4.0-1-x86_64.pkg.tar.zst.sha256"


def test_launch_installer_uses_pkexec_pacman_for_arch_package(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"pacman", "pkexec"} else None)
    monkeypatch.setattr(update_mod.os, "geteuid", lambda: 1000, raising=False)
    calls = []
    monkeypatch.setattr(update_mod.subprocess, "Popen", lambda args: calls.append(args))
    package = tmp_path / "probraw-0.4.0-1-x86_64.pkg.tar.zst"
    package.write_bytes(b"pkg")

    update_mod.launch_installer(package, silent=True)

    assert calls == [["/usr/bin/pkexec", "pacman", "-U", "--noconfirm", str(package.resolve())]]


def test_launch_installer_runs_appimage_directly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(update_mod.subprocess, "Popen", lambda args: calls.append(args))
    appimage = tmp_path / "ProbRAW.AppImage"
    appimage.write_bytes(b"app")

    update_mod.launch_installer(appimage)

    assert calls == [[str(appimage.resolve())]]
    assert appimage.stat().st_mode & 0o111
