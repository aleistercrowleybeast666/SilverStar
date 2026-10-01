"""Actual F4 backend with fallible HAL operations, not a substitute backend."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def uart_recovery_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    builtin = root / "plugins/builtin"
    core = builtin / "silverstar_core_0_1_0/payload"
    f4 = builtin / "silverstar_mcu_family_stm32f4/payload/Platform/STM32F4"
    source = Path(os.environ.get("SILVERSTAR_UART_TEST_SOURCE", str(f4 / "Src")))
    exe = tmp_path_factory.mktemp("uart-recovery") / "recovery.exe"
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    for path in [root / "tests/fixtures/uart_recovery", source, f4 / "Inc",
                 builtin / "silverstar_platform_api/payload/Platform/Inc", core / "Common/Inc"]:
        command += ["-I", str(path)]
    command += [str(root / "tests/fixtures/uart_recovery_host.c"),
                str(core / "Common/Src/common_ringbuf.c"),
                str(core / "Common/Src/silverstar_assert.c"), "-o", str(exe)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


@pytest.mark.parametrize("scenario", ["normal", "abort_fail", "deinit_fail", "init_fail",
    "init_fail_deinit_fail", "init_fail_restore_fail", "init_fail_receive_fail",
    "restart_abort_fail", "second_abort_fail", "all_deinit_fail", "receive_fail", "callback_abort_fail"])
def test_uart_recovery(uart_recovery_executable, scenario):
    result = subprocess.run([str(uart_recovery_executable), scenario],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
