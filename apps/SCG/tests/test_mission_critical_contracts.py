"""Actual mission engine: corrupt owned state cannot publish events/readiness."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def _mission_contract_compile(tmp_path_factory: pytest.TempPathFactory, enabled: int) -> Path:
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    build = tmp_path_factory.mktemp("mission-critical")
    (build / "platform_memory.h").write_text("#define PLATFORM_CPU_FAST_BSS\n", encoding="utf-8")
    (build / "project_mission_process.h").write_text(
        '#include "system_mission_process.h"\n'
        "#define PROJECT_MISSION_STAGE_COUNT 2U\n"
        "#define PROJECT_MISSION_MAXIMUM_GAP_US 100000ULL\n"
        "#define PROJECT_MISSION_FUNCTION_DEPENDENCIES 8U\n"
        f"#define PROJECT_MISSION_CONTROL_ENABLED {enabled}U\n", encoding="utf-8")
    compiler = shutil.which("gcc")
    assert compiler, "Actual Host GCC is required for mission contract verification"
    executable = build / "mission-contract.exe"
    source = root / "tests/fixtures/mission_critical_contract_host.c"
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-fanalyzer"]
    for directory in (build, core / "System/Src", core / "System/Inc",
                      core / "Common/Src", core / "Common/Inc", core / "Interfaces/Inc",
                      root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc"):
        command.extend(["-I", str(directory)])
    command.extend([str(source), "-o", str(executable)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    inputs = [source, core / "System/Src/system_mission_process.c",
              core / "System/Inc/system_mission_process.h", core / "Common/Src/silverstar_assert.c"]
    (build / "compiler-receipt.json").write_text(json.dumps({
        "command": command, "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
        "sources": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
        "scope": "Actual owning C and fault record; Host-only terminal trap interception, no MCU recovery",
    }, indent=2), encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.fixture(scope="module")
def mission_contract_executable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _mission_contract_compile(tmp_path_factory, 0)


@pytest.fixture(scope="module")
def control_window_executable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _mission_contract_compile(tmp_path_factory, 1)


@pytest.mark.parametrize("scenario", [
    "normal", "config-error", "event-count", "active-count", "navigation-count",
    "active-terminated", "event-future", "event-order", "ready-mask", "mission-flag",
    "termination-config-error",
])
def test_owned_mission_contracts(mission_contract_executable: Path, scenario: str) -> None:
    result = subprocess.run([str(mission_contract_executable), scenario],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
    print(result.stdout.strip())


@pytest.mark.parametrize("scenario", ["window", "window-count"])
def test_control_window_contract(control_window_executable: Path, scenario: str) -> None:
    result = subprocess.run([str(control_window_executable), scenario],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
