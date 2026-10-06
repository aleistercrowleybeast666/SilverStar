"""Exact F1 target SRAM bounds must reject overflow and admit the final byte."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("part,end", [("ret6", "0x20010000"), ("rft6", "0x20018000")])
def test_f1_dma_range_uses_exact_target_memory(tmp_path, part, end):
    compiler = os.environ.get("HOST_CC") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is unavailable")
    plugins = Path(__file__).resolve().parents[1] / "plugins/builtin"
    core = plugins / "silverstar_platform_api/payload"
    family = plugins / "silverstar_mcu_family_stm32f1_flight/payload"
    target = plugins / f"silverstar_mcu_stm32f103{part}/payload/Targets"
    header = next(target.glob("*/Inc/platform_memory_target.h"))
    source = tmp_path / "memory_range.c"
    source.write_text('''#include "platform_memory.h"
#include <stdint.h>
#include <assert.h>

int main(void)
{
    const uintptr_t first = (uintptr_t)0x20000000UL;
    const uintptr_t end = (uintptr_t)EXPECTED_SRAM_END;
    assert(PlatformMemory_IsDmaAccessible((const void *)first, 1U) == 1U);
    assert(PlatformMemory_IsDmaAccessible((const void *)(end - 1U), 1U) == 1U);
    assert(PlatformMemory_IsDmaAccessible((const void *)first, (size_t)(end - first)) == 1U);
    assert(PlatformMemory_IsDmaAccessible((const void *)(end - 1U), 2U) == 0U);
    assert(PlatformMemory_IsDmaAccessible((const void *)end, 1U) == 0U);
    assert(PlatformMemory_IsDmaAccessible((const void *)(first - 1U), 1U) == 0U);
    assert(PlatformMemory_IsDmaAccessible((const void *)first, SIZE_MAX) == 0U);
    assert(PlatformMemory_IsDmaAccessible((const void *)first, 0U) == 0U);
    assert(PlatformMemory_IsDmaAccessible((const void *)0, 1U) == 0U);
    return 0;
}
''', encoding="utf-8")
    executable = tmp_path / "memory_range.exe"
    argv = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
            "-I" + str(core / "Platform/Inc"), "-I" + str(header.parent), "-include", str(header),
            "-DEXPECTED_SRAM_END=" + end, str(source),
            str(family / "Platform/STM32F1Flight/Src/platform_memory_stm32f1flight.c"),
            "-o", str(executable)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
