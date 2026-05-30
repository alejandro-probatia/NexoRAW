from __future__ import annotations

import json

import pytest

import probraw.performance as performance_module
from probraw.performance import (
    CONFIG_PATH_ENV,
    MODE_ENV,
    NATIVE_THREADS_ENV,
    HardwareInfo,
    POLICY_VERSION,
    load_configured_policy,
    performance_report,
    recommend_policy,
    write_performance_config,
)


@pytest.fixture(autouse=True)
def _isolated_performance_environment(monkeypatch):
    for key in (
        *performance_module.CONFIGURED_ENV_KEYS,
        CONFIG_PATH_ENV,
        MODE_ENV,
        performance_module.FORCE_ENV,
        performance_module.DISABLE_ENV,
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(performance_module, "_RUNTIME_POLICY", None)
    monkeypatch.setattr(performance_module, "_OPENCV_CONFIGURED", False)


def _hardware(*, cpus: int, memory_gib: int) -> HardwareInfo:
    return HardwareInfo(
        cpu_count=cpus,
        affinity_count=cpus,
        architecture="64bit",
        machine="x86_64",
        processor="test",
        cpu_model="Synthetic CPU",
        total_memory_bytes=memory_gib * 1024 * 1024 * 1024,
        available_memory_bytes=(memory_gib // 2) * 1024 * 1024 * 1024,
        platform="test",
    )


def test_balanced_policy_uses_cpu_without_saturating_every_thread():
    policy = recommend_policy(_hardware(cpus=12, memory_gib=32), mode="balanced")

    assert policy.native_threads == 8
    assert policy.opencv_threads == 8
    assert policy.batch_native_threads == 4
    assert policy.batch_worker_cap == 3
    assert policy.interactive_worker_cap >= 8


def test_conservative_policy_keeps_small_machine_responsive():
    policy = recommend_policy(_hardware(cpus=4, memory_gib=8), mode="conservative")

    assert policy.native_threads <= 2
    assert policy.batch_worker_cap >= 1


def test_write_performance_config_records_matching_hardware(tmp_path):
    output = tmp_path / "performance.json"

    payload = write_performance_config(output, mode="balanced")
    stored = json.loads(output.read_text(encoding="utf-8"))

    assert payload["policy_version"] == POLICY_VERSION
    assert stored["schema"] == "probraw-performance-policy"
    assert stored["hardware_signature"] == stored["policy"]["hardware_signature"]
    assert "OMP_NUM_THREADS" in stored["environment"]


def test_configured_policy_is_ignored_when_hardware_signature_changes(tmp_path, monkeypatch):
    config = tmp_path / "performance.json"
    first_hardware = _hardware(cpus=12, memory_gib=32)
    second_hardware = _hardware(cpus=4, memory_gib=8)

    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))
    monkeypatch.setattr(performance_module, "detect_hardware", lambda: first_hardware)
    write_performance_config(config, mode="balanced")

    monkeypatch.setattr(performance_module, "detect_hardware", lambda: second_hardware)

    assert load_configured_policy() is None
    report = performance_report()
    assert report["configured_policy_loaded"] is False
    assert report["active_policy"]["hardware_signature"] == second_hardware.signature


def test_mode_override_ignores_installed_policy(tmp_path, monkeypatch):
    config = tmp_path / "performance.json"
    hardware = _hardware(cpus=16, memory_gib=64)

    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))
    monkeypatch.setattr(performance_module, "detect_hardware", lambda: hardware)
    write_performance_config(config, mode="conservative")
    monkeypatch.setenv(MODE_ENV, "aggressive")

    report = performance_report()

    assert report["configured_policy_loaded"] is False
    assert report["active_policy"]["mode"] == "aggressive"


def test_user_thread_override_has_priority(monkeypatch):
    hardware = _hardware(cpus=16, memory_gib=64)
    monkeypatch.setenv(NATIVE_THREADS_ENV, "3")

    policy = recommend_policy(hardware, mode="aggressive")

    assert policy.native_threads == 3
    assert policy.environment()["OMP_NUM_THREADS"] == "3"


def test_cross_platform_unknown_memory_still_returns_bounded_policy():
    hardware = HardwareInfo(
        cpu_count=24,
        affinity_count=20,
        architecture="64bit",
        machine="arm64",
        processor="",
        cpu_model="",
        total_memory_bytes=None,
        available_memory_bytes=None,
        platform="Darwin-test",
    )

    policy = recommend_policy(hardware, mode="balanced")

    assert 1 <= policy.native_threads <= 12
    assert 1 <= policy.interactive_worker_cap <= 16
    assert policy.usable_cpus == 20
