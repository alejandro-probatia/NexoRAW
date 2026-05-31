import subprocess

from probraw.core import external


class FakeStartupInfo:
    def __init__(self) -> None:
        self.dwFlags = 0
        self.wShowWindow = None


def test_run_external_hides_console_on_windows(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(external.os, "name", "nt", raising=False)
    monkeypatch.setattr(external.subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(external.subprocess, "STARTF_USESHOWWINDOW", 4, raising=False)
    monkeypatch.setattr(external.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(external.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(external.subprocess, "run", fake_run)

    result = external.run_external(["tool"], creationflags=0x10, text=True)

    assert result.returncode == 0
    assert captured["command"] == ["tool"]
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["creationflags"] & 0x08000000
    assert captured["kwargs"]["creationflags"] & 0x10
    assert isinstance(captured["kwargs"]["startupinfo"], FakeStartupInfo)
    assert captured["kwargs"]["startupinfo"].dwFlags & 4


def test_run_external_leaves_non_windows_kwargs_unchanged(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(external.os, "name", "posix", raising=False)
    monkeypatch.setattr(external.subprocess, "run", fake_run)

    external.run_external(["tool"], text=True)

    assert captured["kwargs"] == {"text": True}


def test_bundled_tool_dirs_includes_macos_package_manager_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(external.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(external.sys, "executable", str(tmp_path / "venv" / "bin" / "python"), raising=False)
    monkeypatch.delenv("PROBRAW_TOOL_DIR", raising=False)

    paths = {str(path) for path in external.bundled_tool_dirs()}

    assert "/opt/homebrew/bin" in paths
    assert "/usr/local/bin" in paths
    assert "/opt/local/bin" in paths


def test_bundled_tool_dirs_includes_arch_vendor_perl_path(monkeypatch, tmp_path):
    monkeypatch.setattr(external.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(external.sys, "executable", str(tmp_path / "venv" / "bin" / "python"), raising=False)
    monkeypatch.delenv("PROBRAW_TOOL_DIR", raising=False)

    paths = {str(path) for path in external.bundled_tool_dirs()}

    assert "/usr/bin/vendor_perl" in paths
