import shutil
import subprocess
from pathlib import Path

import pytest


def test_f1_sd_clock_actual_hal_mmio(tmp_path):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    app = Path(__file__).resolve().parents[1]
    family = app / "plugins/builtin/silverstar_mcu_family_stm32f1_flight/payload"
    core = app / "plugins/builtin/silverstar_core_0_1_0/payload"
    includes = [app / "tests/fixtures/f1_hal_mmio", family / "Drivers/STM32F1xx_HAL_Driver/Inc",
                family / "Drivers/CMSIS/Device/ST/STM32F1xx/Include",
                family / "Drivers/CMSIS/Include", family / "Platform/STM32F1Flight/Inc",
                core / "Common/Inc"]
    executable = tmp_path / "sd_clock_mmio.exe"
    command = [compiler, "-std=c11", "-O2", "-DSTM32F103xE", "-Wall", "-Wextra",
               "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
               *("-I" + str(path) for path in includes),
               str(app / "tests/fixtures/f1_sd_clock_mmio.c"),
               str(family / "Platform/STM32F1Flight/Src/platform_sd_clock.c"),
               str(family / "Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_sd.c"),
               str(family / "Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_ll_sdmmc.c"),
               "-o", str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    print("COMMAND", command)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SD_CLOCK_MMIO PASS" in result.stdout
    print(result.stdout)
