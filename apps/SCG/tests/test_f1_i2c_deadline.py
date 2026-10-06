import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_f1_i2c_actual_hal_whole_transaction_deadline(tmp_path):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    app = Path(__file__).resolve().parents[1]
    family = app / "plugins/builtin/silverstar_mcu_family_stm32f1_flight/payload"
    core = app / "plugins/builtin/silverstar_core_0_1_0/payload"
    includes = [app / "tests/fixtures/f1_hal_mmio", app / "tests/fixtures",
                family / "Drivers/STM32F1xx_HAL_Driver/Inc",
                family / "Drivers/CMSIS/Device/ST/STM32F1xx/Include",
                family / "Drivers/CMSIS/Include", family / "Platform/STM32F1Flight/Inc",
                core / "Common/Inc"]
    executable = tmp_path / "i2c_deadline_mmio.exe"
    # Intercept the volatile DR reads, just as the header intercepts flag
    # reads. The owning transaction and control flow remain unchanged.
    source = Path(os.environ.get("SILVERSTAR_I2C_HAL_SOURCE", str(
        family / "Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_i2c.c")))
    instrumented = tmp_path / "stm32f1xx_hal_i2c_mmio.c"
    instrumented.write_text(source.read_text(encoding="utf-8").replace(
        "(uint8_t)hi2c->Instance->DR", "HostI2c_DataRead(hi2c)"), encoding="utf-8")
    command = [compiler, "-std=c11", "-O2", "-DSTM32F103xE", "-Wall", "-Wextra",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               *("-I" + str(path) for path in includes),
               "-include", str(app / "tests/fixtures/f1_i2c_mmio_model.h"),
               str(app / "tests/fixtures/f1_i2c_deadline_mmio.c"),
               str(family / "Platform/STM32F1Flight/Src/platform_i2c_deadline.c"),
               str(instrumented),
               "-o", str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    print("COMMAND", command)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable), "--tick-tail"], capture_output=True, text=True, timeout=10)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TICK_TAIL PASS" in result.stdout
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "I2C_DEADLINE_MMIO PASS" in result.stdout
    for mode in ("--corrupt-active", "--corrupt-budget", "--double-start",
                 "--lost-active", "--lost-owner", "--lost-lock"):
        result = subprocess.run([str(executable), mode], capture_output=True, text=True, timeout=10)
        print(mode, "exit", result.returncode, result.stdout + result.stderr)
        assert result.returncode == 1
        assert "ASSERT_TRAP" in result.stderr
