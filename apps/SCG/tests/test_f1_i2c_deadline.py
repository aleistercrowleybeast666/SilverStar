import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mutation", [None, "arlo_stop", "nonmaster_stop", "stuck_stop_restore"])
def test_f1_i2c_actual_hal_whole_transaction_deadline(tmp_path, mutation):
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
    source_text = source.read_text(encoding="utf-8")
    if mutation == "arlo_stop":
        source_text, count = re.subn(
            r"\(\(\(hi2c->ErrorCode & HAL_I2C_ERROR_ARLO\) == 0U\) &&\s*",
            "(", source_text)
        assert count == 1
    elif mutation == "nonmaster_stop":
        source_text, count = re.subn(
            r"\(\(hi2c->Instance->SR2 & I2C_SR2_MSL\) != 0U\)",
            "(1U != 0U)", source_text)
        assert count == 1
    elif mutation == "stuck_stop_restore":
        source_text, count = re.subn(
            r"if \(\(hi2c->Instance->CR1 & I2C_CR1_STOP\) == 0U\)\s*"
            r"(?=\{ MODIFY_REG\(hi2c->Instance->CR1, I2C_CR1_ACK \| I2C_CR1_POS, original_ack_pos\);)",
            "", source_text)
        assert count == 1
    instrumented_text = source_text.replace(
        "(uint8_t)hi2c->Instance->DR", "HostI2c_DataRead(hi2c)")
    instrumented_text, stop_hooks = re.subn(
        r"SET_BIT\(hi2c->Instance->CR1,\s*I2C_CR1_STOP\)",
        "HostI2c_StopRequest(hi2c)", instrumented_text)
    assert stop_hooks > 0, "Missing STOP request instrumentation"
    instrumented.write_text(instrumented_text, encoding="utf-8")
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
    if mutation is not None:
        print("EXPECTED_MUTATION_FAILURE", mutation, "exit", result.returncode)
        assert result.returncode == 1, "Unsafe mutation escaped the Host fixture"
        assert "FAIL line=" in result.stderr
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert "I2C_DEADLINE_MMIO PASS" in result.stdout
    for mode in ("--corrupt-active", "--corrupt-budget", "--double-start",
                 "--lost-active", "--lost-owner", "--lost-lock"):
        result = subprocess.run([str(executable), mode], capture_output=True, text=True, timeout=10)
        print(mode, "exit", result.returncode, result.stdout + result.stderr)
        assert result.returncode == 1
        assert "ASSERT_TRAP" in result.stderr
