from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def navigation_queue_contract_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    includes = [
        core / "Common/Inc", core / "Common/Src", core / "Interfaces/Inc",
        core / "System/Inc", core / "System/Src",
        root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
    ]
    executable = tmp_path_factory.mktemp("nav-queue-contract") / "contract.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    for directory in includes:
        command.extend(["-I", str(directory)])
    command.extend([str(root / "tests/fixtures/navigation_queue_contract_host.c"), "-o", str(executable)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize("scenario", [
    "nav_get_atomic", "nav_before_epoch", "nav_time_regression",
    "nav_physical_bool", "nav_attempt_bool", "nav_effective_bool", "nav_soft_bool",
    "nav_state", "nav_quality", "nav_success_flag", "nav_receive_flag",
    "nav_model_flag", "nav_fault_mask", "nav_normal",
    "queue_head_index", "queue_tail_index", "queue_capacity",
    "queue_push_distance", "queue_pop_distance", "queue_normal",
])
def test_navigation_queue_contract(navigation_queue_contract_executable, scenario):
    result = subprocess.run([str(navigation_queue_contract_executable), scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
