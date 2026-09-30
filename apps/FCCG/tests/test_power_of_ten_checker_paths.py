"""Regression tests for the source Power of Ten checker, independent of firmware."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def checker_fixture(tmp_path: Path) -> Path:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell is unavailable")
    source = Path(__file__).resolve().parents[1] / (
        "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1"
    )
    tools = tmp_path / "Tools"
    tools.mkdir()
    shutil.copy2(source, tools / source.name)
    (tmp_path / "Makefile").write_text(
        "FIRST_PARTY_C_SOURCES := APP/fixture.c\n"
        "FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror "
        "-Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 "
        "-Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes "
        "-Wmissing-prototypes -Wswitch-enum -Wvla\n"
        "power10-check:\n\t@echo check\n",
        encoding="utf-8",
    )
    (tmp_path / "STM32F407XX_FLASH.ld").write_text(
        "_Min_Heap_Size = 0x0;\n", encoding="utf-8"
    )
    return tmp_path


def _PowerShell_Run(root: Path, expression: str) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    assert shell is not None
    probe = root / "probe.ps1"
    probe.write_text(
        '. "$PSScriptRoot/Tools/check_power_of_ten.ps1"\n'
        f"if (-not ({expression})) {{ throw 'checker regression' }}\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )


@pytest.mark.parametrize("separator", ("/", "\\"))
def test_authorized_paths_match_both_separators(
    checker_fixture: Path, separator: str,
) -> None:
    estimator = f"APP{separator}Src{separator}estimator_task.c"
    hooks = f"OS{separator}FreeRTOS{separator}freertos_hooks.c"
    expression = (
        f"(Test-PowerTenApprovedConditional '{estimator}' "
        "'#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)') -and "
        f"(Test-PowerTenApprovedDoublePointer '{hooks}' "
        "'    StaticTask_t **task_control,')"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "expression",
    (
        "Test-PowerTenApprovedConditional 'APP/Src/other_estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)'",
        "Test-PowerTenApprovedConditional 'Other/APP/Src/estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)'",
        "Test-PowerTenApprovedConditional 'APP/Src/estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED == 1U)'",
        "Test-PowerTenApprovedDoublePointer 'OS/FreeRTOS/other_freertos_hooks.c' 'StaticTask_t **task_control,'",
        "Test-PowerTenApprovedDoublePointer 'Other/OS/FreeRTOS/freertos_hooks.c' 'StaticTask_t **task_control,'",
        "Test-PowerTenApprovedDoublePointer 'OS/FreeRTOS/freertos_hooks.c' 'uint8_t **user_buffer,'",
    ),
)
def test_similar_paths_and_unauthorized_code_get_no_exception(
    checker_fixture: Path, expression: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, f"-not ({expression})")
    assert result.returncode == 0, result.stdout + result.stderr


def test_known_constant_object_assertions_do_not_count(
    checker_fixture: Path,
) -> None:
    expression = (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT_OBJECT(&sample, Sample, MODULE); "
        "SILVERSTAR_ASSERT_OBJECT(s_seq, uint32_t, MODULE); "
        "SILVERSTAR_ASSERT(1U, MODULE, REASON);' @('s_seq')) -eq 0"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr


def test_runtime_pointer_and_state_assertions_still_count(
    checker_fixture: Path,
) -> None:
    expression = (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT_OBJECT(report, Report, MODULE); "
        "SILVERSTAR_ASSERT(report->completed <= 1U, MODULE, REASON);' @()) -eq 3"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr
