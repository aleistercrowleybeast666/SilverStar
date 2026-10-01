from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def source_selector_contract_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    includes = [root / "tests/fixtures/source_selector", core / "Tests/Host",
                core / "Common/Inc", core / "Common/Src", core / "Interfaces/Inc",
                core / "System/Inc", core / "System/Src",
                core / "System/Calibration/Inc",
                root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc"]
    executable = tmp_path_factory.mktemp("selector-contract") / "contract.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               "-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U", "-ffunction-sections",
               "-fdata-sections", "-Wl,--gc-sections"]
    for p in includes:
        command.extend(["-I", str(p)])
    command.extend([str(root / "tests/fixtures/source_selector_contract_host.c"), "-o", str(executable)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize("kind", ["1", "2", "3"])
@pytest.mark.parametrize("scenario", ["init_order", "init_result", "start_order", "start_count",
                                      "start_result", "failed_restart", "init_capacity", "normal"])
def test_source_selector_contract(source_selector_contract_executable, kind, scenario):
    result = subprocess.run([str(source_selector_contract_executable), kind, scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("scenario", ["gnss_count", "gnss_active", "gnss_position", "gnss_order",
                                      "next_count", "next_position", "next_order", "next_result",
                                      "health_count", "health_active", "health_timeout"])
def test_source_selector_switch_contract(source_selector_contract_executable, scenario):
    result = subprocess.run([str(source_selector_contract_executable), "0", scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_selector_failed_candidate_restart(source_selector_contract_executable):
    result = subprocess.run([str(source_selector_contract_executable), "3", "next_failed_restart"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("scenario", ["start_active", "start_position"])
def test_source_selector_gnss_start_contract(source_selector_contract_executable, scenario):
    result = subprocess.run([str(source_selector_contract_executable), "2", scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
